import bcrypt
from sqlalchemy.orm import Session

from app.db.db import Game, Player, GameStatus, Turn
from app.errors.handlers import ForbiddenError, NotFoundError
from app.schemas.game import GameCreateSchema, StartResponseSchema
from app.schemas.player import PlayerResponseSchema
from app.services import lobby_events, game_events, game_list_events
from app.services.board import delete_partial_cache, undo_played_moves
from app.services.cards import assign_figure_cards, assign_movement_cards
from app.services.game_player_service import get_game, get_player
from app.services.timer import handle_timer
from app.models.playerlock import PlayerAction, PlayerLock, lock_player


async def create_game(data: GameCreateSchema, db: Session):
    owner_name = data.ownerName
    game_name = data.gameName
    max_players = data.maxPlayers
    min_players = data.minPlayers

    if data.password is None or data.password == "":
        password = None
    else:
        password = bcrypt.hashpw(
            data.password.encode("utf-8"), bcrypt.gensalt()
        )

    if not owner_name or not game_name or not max_players or not min_players:
        raise ValueError("All fields required")
    if max_players < min_players:
        raise ValueError(
            "maxPlayers must be greater than or equal to minPlayers"
        )
    if min_players < 2 or min_players > 4:
        raise ValueError("minPlayers must be at least 2 and at most 4")
    if max_players < 2 or max_players > 4:
        raise ValueError("maxPlayers must be at least 2 and at most 4")

    db_game = Game(
        name=game_name,
        password=password,
        max_players=max_players,
        min_players=min_players,
        status=GameStatus.LOBBY,
        turn=Turn.P2,  # default turn is the next player to the host
    )
    db.add(db_game)
    db.commit()
    db.refresh(db_game)

    db_player = Player(name=owner_name, game_id=db_game.id, turn=Turn.P1)
    db.add(db_player)
    db.commit()
    db.refresh(db_player)

    await game_list_events.emit_game_list(db)

    return {"gameId": db_game.id, "ownerId": db_player.id}


async def add_player_to_game(
    player_name: str, game_id: int, db: Session, password: str = None
) -> PlayerResponseSchema:
    game = get_game(game_id, db)

    if game.status != GameStatus.LOBBY:
        raise ValueError(f"Game {game_id} is already in progress.")

    if len(game.players) >= game.max_players:
        raise ValueError(f"Game {game_id} is full.")

    if not game.password and password:
        raise ValueError("Game does not have a password.")
    if game.password and not password:
        raise ValueError("Password required to join game.")
    if game.password and not bcrypt.checkpw(
        password.encode("utf-8"), game.password
    ):
        raise ValueError("Incorrect password.")

    # Determine the turn for the new player
    turn_order = len(game.players) + 1
    turn = Turn(turn_order)

    player = Player(name=player_name, game_id=game.id, turn=turn)
    db.add(player)
    db.commit()
    db.refresh(player)

    await game_list_events.emit_game_list(db)

    return PlayerResponseSchema(playerId=player.id, playerName=player.name)


async def start_game(game_id: int, db: Session) -> StartResponseSchema:
    game = get_game(game_id, db)
    if game.status != GameStatus.LOBBY:
        raise ValueError(f"Game {game_id} is already in progress.")
    if game.min_players > len(game.players):
        raise ValueError("Not enough players to start the game.")

    game.status = GameStatus.INGAME
    db.commit()

    # Notify all players that the game has started
    await lobby_events.emit_game_started(game_id)

    await game_list_events.emit_game_list(db)

    return StartResponseSchema(gameId=game.id, status=game.status)


async def pass_turn(game_id: int, player_id: int, db: Session):
    game = get_game(game_id, db)
    player = get_player(player_id, db)

    current_turn_index = [
        index
        for index, player in enumerate(game.players)
        if player.turn == game.turn
    ][0]

    next_turn_index = (current_turn_index + 1) % len(game.players)

    next_player = game.players[next_turn_index]

    game.turn = next_player.turn

    print(f"Player {player.name} has ended their turn")
    db.commit()

    # Undo played moves. This must be done after the turn is passed.
    await undo_played_moves(game_id, player_id, db)
    delete_partial_cache(game_id, db)

    # Deal new cards if needed
    assign_figure_cards(game_id, next_player.id, db)
    assign_movement_cards(game_id, next_player.id, db)
    await game_events.emit_cards(game_id, next_player.id, db)
    await game_events.emit_opponents_total_mov_cards(game_id, db)

    # Notify all players the new turn info
    await game_events.emit_turn_info(game_id, db)

    # Reset the timer for the new turn
    await handle_timer(game_id, next_player.id, db, reset=True)


async def end_turn(game_id: int, player_id: int, db: Session):
    game = get_game(game_id, db)
    player = get_player(player_id, db)

    if game.status != GameStatus.INGAME:
        raise ValueError(f"Game {game.id} is not in progress.")
    if game.turn != player.turn:
        raise ValueError(f"It's not {player.id} turn.")

    with lock_player(player_id, PlayerAction.END_TURN):
        await pass_turn(game_id, player_id, db)

    return {"message": f"Player {player.name} has ended their turn."}


async def remove_player_from_game(game_id: int, player_id: int, db: Session):
    game = get_game(game_id, db)
    player = get_player(player_id, db)

    if PlayerLock().is_locked(player_id, PlayerAction.END_TURN):
        raise ForbiddenError(
            "Player is currently ending their turn and cannot leave the game."
        )

    with lock_player(player_id, PlayerAction.REMOVE_PLAYER):
        # Disconnect the player's socket from the game room
        await game_events.disconnect_player_socket(player_id, game_id)

        if game.status == GameStatus.LOBBY and player.turn == Turn.P1:
            raise ForbiddenError(
                "Host does not have permission to leave the lobby."
            )

        if game.status == GameStatus.INGAME and player.turn == game.turn:
            # if the player leaving is the current player, end their turn
            await end_turn(game_id, player_id, db)

        db.delete(player)
        db.commit()

        if game.status == GameStatus.INGAME and len(game.players) == 1:
            # if there is only one player left in the game, the game is over and that player wins
            game.status = GameStatus.FINISHED
            db.commit()

            await game_events.emit_winner(game_id, game.players[0].id, db)

        if game.status == GameStatus.LOBBY:
            await lobby_events.emit_players_lobby(game_id, db)
            await lobby_events.emit_can_start_game(game_id, db)
            await game_list_events.emit_game_list(db)

        if game.status == GameStatus.INGAME:
            await game_events.emit_players_game(game_id, db)

    return {"message": f"Player {player.name} has left the game."}
