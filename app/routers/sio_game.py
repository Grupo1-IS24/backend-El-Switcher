import socketio, asyncio

from app.db.db import db_context, Game, Player, GameStatus
from app.models.broadcast import Broadcast
from app.services import game_events
from app.utils.parse_query_string import parse_query_string
from app.services.timer import start_timer

# Create a new Socket.IO server
sio_game = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=[])


@sio_game.on("connect")
async def connect(sid, environ, auth):
    player_id, game_id = parse_query_string(environ)

    print(f"Player {player_id} connected to game {game_id}")

    with db_context() as db:
        game = db.query(Game).filter(Game.id == game_id).first()

        if game is None:
            print(f"Game {game_id} does not exist")
            return  # Game does not exist, then disconnect the player

        if game.status != GameStatus.INGAME:
            print(f"Game {game_id} is not started")
            return  # Game is not started, then disconnect the player

        # check if the player is part of the game
        player = (
            db.query(Player).filter_by(id=player_id, game_id=game.id).first()
        )

        if player is None:
            print(f"Player {player_id} is not part of game {game_id}")
            return  # Player is not part of the game, then disconnect the player

        # Register the player's socket
        channel = Broadcast()

        await channel.register_player_socket(sio_game, player_id, game_id, sid)

        # Broadcast Board
        await game_events.emit_board(game_id, db)

        await game_events.emit_found_figures(game_id, db)

        await game_events.emit_block_color(game_id, db)

        # Broadcast cards

        await game_events.emit_cards(game_id, player_id, db)

        await game_events.emit_players_game(game_id, db)

        # Broadcast turn info

        await game_events.emit_turn_info(game_id, db, reset=False)

        start_timer(game_id, player_id, db)

        await game_events.emit_opponents_total_mov_cards(game_id, db)

        # Broadcast chat

        await game_events.emit_chat_history(game_id, player_id, db)

        await game_events.emit_log_history(game_id, player_id, db)
