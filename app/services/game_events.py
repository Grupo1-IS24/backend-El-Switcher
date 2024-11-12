from app.db.db import GameStatus, Player, Game, LogMessage
from sqlalchemy.orm import Session

from app.models.broadcast import Broadcast

from app.routers import sio_game as sio

from app.schemas.player import PlayerResponseSchema, WinnerSchema
from app.schemas.chat import (
    SingleChatMessageSchema,
    MultipleChatMessagesSchema,
    ChatMessageSchema,
)
from app.schemas.logs import (
    SingleLogMessageSchema,
    MultipleLogMessagesSchema,
    LogMessageSchema,
)

from app.services.cards import fetch_figure_cards, fetch_movement_cards
from app.services.board import get_board, get_blocked_color
from app.services.figures import figures_event
from app.services.timer import restart_timer, stop_all_timers
from app.services.chat import get_chat_history
from app.services.logs import get_log_history


async def disconnect_player_socket(player_id, game_id):
    broadcast = Broadcast()
    await broadcast.unregister_player_socket(sio.sio_game, player_id, game_id)


async def emit_players_game(game_id, db):
    players = db.query(Player).filter(Player.game_id == game_id).all()

    # convert every player in player response schema
    PlayerResponseSchemaList = []

    for player in players:
        PlayerResponseSchemaList.append(
            PlayerResponseSchema(
                playerId=player.id, playerName=player.name
            ).model_dump()
        )

    broadcast = Broadcast()

    # send the player list to all players in the lobby
    await broadcast.broadcast(
        sio.sio_game, game_id, "player_list", PlayerResponseSchemaList
    )


async def emit_turn_info(game_id, db, reset):
    game = db.query(Game).filter(Game.id == game_id).first()

    player = (
        db.query(Player)
        .filter(Player.game_id == game_id, Player.turn == game.turn)
        .first()
    )

    broadcast = Broadcast()

    turn_info = {
        "playerTurnId": player.id,
    }

    # send the turn info to all players in the lobby
    await broadcast.broadcast(sio.sio_game, game_id, "turn", turn_info)

    if reset:
        # start the timer for the current player
        await restart_timer(game_id, player.id, db)


async def win_by_figures(game_id: int, player_id: int, db):
    """
    Comprueba si un jugador ha descartado todas sus figuras.
    En caso afirmativo, termina el juego y se le declara ganador.
    """
    game = db.query(Game).filter(Game.id == game_id).first()

    player = (
        db.query(Player)
        .filter(Player.id == player_id, Player.game_id == game_id)
        .first()
    )

    if len(player.card_figs) == 0:
        game.status = GameStatus.FINISHED
        await emit_winner(game_id, player_id, db)


async def emit_winner(game_id, player_id, db):
    winner = db.query(Player).filter(Player.id == player_id).first()

    broadcast = Broadcast()

    await broadcast.broadcast(
        sio.sio_game,
        game_id,
        "winner",
        WinnerSchema(idWinner=winner.id, nameWinner=winner.name).model_dump(),
    )

    stop_all_timers(game_id, db)


async def emit_cards(game_id, player_id, db):
    """
    Emits to specified player their own movement cards and all other player's figure cards.
    """
    channel = Broadcast()

    total_figure_cards = fetch_figure_cards(game_id, db)
    player_move_cards = fetch_movement_cards(player_id, db)

    await channel.broadcast(
        sio=sio.sio_game,
        game_id=game_id,
        event="figure_cards",
        data=total_figure_cards,
    )
    await channel.send_to_player(
        sio=sio.sio_game,
        player_id=player_id,
        event="movement_cards",
        data=player_move_cards,
    )


async def emit_board(game_id, db):
    """
    Emits the current board.
    """
    channel = Broadcast()
    board = get_board(game_id, db)

    await channel.broadcast(sio.sio_game, game_id, "board", board)


async def emit_opponents_total_mov_cards(game_id, db):
    """
    Emits the number of each user's movement cards that have not been played
    """
    channel = Broadcast()

    players = db.query(Player).filter(Player.game_id == game_id).all()

    result = []

    for player in players:
        visible_mov_cards = sum(
            1 for card in player.card_moves if not card.played
        )
        result.append(
            {"playerId": player.id, "totalMovCards": visible_mov_cards}
        )

    await channel.broadcast(
        sio.sio_game, game_id, "opponents_total_mov_cards", result
    )


async def emit_found_figures(game_id, db):
    """
    Emits the figures found in the board
    """
    channel = Broadcast()

    response = figures_event(game_id, db)

    await channel.broadcast(sio.sio_game, game_id, "found_figures", response)


async def emit_single_chat_message(
    message: SingleChatMessageSchema, game_id: int
):
    """
    Given the message and the name of the sender, emits the message to
    every other player in the room
    """
    channel = Broadcast()

    await channel.broadcast(sio.sio_game, game_id, "chat_messages", message)


async def emit_chat_history(game_id: int, player_id: int, db: Session):
    """
    Emit all the chat messages previously sent to the newly connected or
    re-connected player.
    """
    data_to_emit = MultipleChatMessagesSchema(data=[])

    # First fetch all the chat messages from the game
    chat_history = await get_chat_history(game_id, db)
    for message in chat_history:
        message_schema = ChatMessageSchema(
            writtenBy=message.sender.name, message=message.message
        )  # esto se ve horrible perdon

        # Append every message to the corresponding schema list
        data_to_emit.data.append(message_schema)

    channel = Broadcast()

    await channel.send_to_player(
        sio.sio_game, player_id, "chat_messages", data_to_emit.model_dump()
    )


async def emit_log(game_id: int, message: str, db: Session):
    # Save log to db
    db.add(LogMessage(message=message, game_id=game_id))
    db.commit()

    # Format log for emission
    log_message = LogMessageSchema(message=message)
    data_to_emit = SingleLogMessageSchema(data=log_message).model_dump()

    # Emit log
    channel = Broadcast()
    await channel.broadcast(sio.sio_game, game_id, "game_logs", data_to_emit)


async def emit_log_history(game_id: int, player_id: int, db: Session):
    """
    Emit all the log messages previously sent to the newly connected or
    re-connected player.
    """
    data_to_emit = MultipleLogMessagesSchema(data=[])

    # First fetch all the chat messages from the game
    log_history = await get_log_history(game_id, db)
    for message in log_history:
        message_schema = LogMessageSchema(message=message.message)

        # Append every message to the corresponding schema list
        data_to_emit.data.append(message_schema)

    channel = Broadcast()

    await channel.send_to_player(
        sio.sio_game, player_id, "game_logs", data_to_emit.model_dump()
    )


async def emit_block_color(game_id, db):
    """
    Emits the blocked color
    """
    channel = Broadcast()

    response = get_blocked_color(game_id, db)

    await channel.broadcast(sio.sio_game, game_id, "blocked_color", response)
