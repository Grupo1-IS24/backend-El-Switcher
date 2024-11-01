import asyncio
from app.models.broadcast import Broadcast
from app.routers import sio_game as sio
from app.services import game

TURN_TIME_LIMIT = 120

# Global dictionary to keep track of timer tasks and remaining time
timer_tasks = {}
time_left_dict = {}


async def handle_timer(game_id, player_id, db, reset=False):
    # Cancel the previous timer task if it exists
    if game_id in timer_tasks:
        timer_tasks[game_id].cancel()
        del timer_tasks[game_id]

    # Reset the timer if specified
    if reset or game_id not in time_left_dict:
        time_left_dict[game_id] = TURN_TIME_LIMIT

    # Start the timer for the new turn
    timer_tasks[game_id] = asyncio.create_task(
        emit_timer(game_id, player_id, db)
    )


async def emit_timer(game_id, player_id, db):
    broadcast = Broadcast()
    time_left = time_left_dict[game_id]

    while time_left > 0:
        time_left_dict[game_id] = time_left
        await broadcast.broadcast(
            sio.sio_game, game_id, "timer", {"time": time_left}
        )
        await asyncio.sleep(1)
        time_left -= 1

    del time_left_dict[game_id]
    await game.end_turn(game_id, player_id, db)
