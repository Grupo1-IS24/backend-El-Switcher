from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict

from app.schemas.game import GameCreateSchema, GameListSchema, ListSchema, StartResponseSchema
from app.schemas.player import PlayerResponseSchema
from app.schemas.board import PieceResponseSchema
from app.db.db import Game, Player, GameStatus, Turn, Board, SquarePiece, Color
import random
from app.services import lobby_events, game_events


def create_game(data: GameCreateSchema, db: Session):
    owner_name = data.ownerName
    game_name = data.gameName
    max_players = data.maxPlayers
    min_players = data.minPlayers

    if not owner_name or not game_name or not max_players or not min_players:
        raise HTTPException(status_code=400, detail="All fields required")
    if max_players < min_players:
        raise HTTPException(status_code=400, detail="maxPlayers must be greater than or equal to minPlayers")
    if min_players < 2 or min_players > 4:
        raise HTTPException(status_code=400, detail="minPlayers must be at least 2 and at most 4")
    if max_players < 2 or max_players > 4:
        raise HTTPException(status_code=400, detail="maxPlayers must be at least 2 and at most 4")

    db_game = Game(
        name=game_name,
        max_players=max_players,
        min_players=min_players,
        status=GameStatus.LOBBY,
        turn=Turn.P2  # default turn is the next player to the host
    )
    db.add(db_game)
    db.commit()
    db.refresh(db_game)

    db_player = Player(name=owner_name, game_id=db_game.id, turn=Turn.P1)
    db.add(db_player)
    db.commit()
    db.refresh(db_player)

    return {
        "gameId": db_game.id,
        "ownerId": db_player.id 
    }


def get_game(game_id: int, db: Session) -> Game:
    game = db.query(Game).filter(Game.id == game_id).first()
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Game with id {game_id} does not exist.")
    return game

def get_player(player_id: int, db: Session) -> Player:
    player = db.query(Player).filter(Player.id == player_id).first()
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Player with id {player_id} does not exist.")
    return player


def add_player_to_game(player_name: str, game_id: int, db: Session) -> PlayerResponseSchema:
    game = get_game(game_id, db)
    
    if game.status != GameStatus.LOBBY: 
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Game {game_id} is already in progress.")
    
    if len(game.players) >= game.max_players:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Game {game_id} is full.")

    # Determine the turn for the new player
    turn_order = len(game.players) + 1
    turn = Turn(turn_order)

    player = Player(name=player_name, game_id=game.id, turn=turn)
    db.add(player)
    db.commit()
    db.refresh(player)

    return PlayerResponseSchema(
        playerId=player.id,
        playerName=player.name
    )

async def start_game(game_id: int, db: Session) -> StartResponseSchema:
    game = get_game(game_id, db)
    if game.status != GameStatus.LOBBY:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Game {game_id} is already in progress.")
    if game.min_players > len(game.players):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not enough players to start the game.")

    game.status = GameStatus.INGAME
    db.commit()

    # Notify all players that the game has started
    await lobby_events.emit_game_started(game_id)

    return StartResponseSchema(gameId=game.id, status=game.status)

async def end_turn(game_id: int, player_id: int, db: Session):
    game = get_game(game_id, db)
    player = get_player(player_id, db)

    if game.status != GameStatus.INGAME:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Game {game.id} is not in progress.")
    if game.turn != player.turn:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"It's not {player.id} turn.")
    
    current_turn_index = [index for index, player in enumerate(game.players) if player.turn == game.turn][0]

    next_turn_index = (current_turn_index + 1) % len(game.players)

    game.turn = game.players[next_turn_index].turn

    print(f"Player {player.name} has ended their turn")
    db.commit()

    # Notify all players the new turn info
    await game_events.emit_turn_info(game_id, db)

    return {'message' : f"Player {player.name} has ended their turn."}

async def remove_player_from_game(game_id: int, player_id: int, db: Session):
    game = get_game(game_id, db)
    player = get_player(player_id, db)
    
    # Disconnect the player's socket from the game room
    await game_events.disconnect_player_socket(player_id, game_id)
    
    if game.status == GameStatus.LOBBY and player.turn == Turn.P1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Host does not have permission to leave the lobby.")
    
    if game.status == GameStatus.INGAME and player.turn == game.turn:
        # if the player leaving is the current player, end their turn
        await end_turn(game_id, player_id, db)

    db.delete(player)
    db.commit()
        
    if game.status == GameStatus.INGAME and len(game.players) == 1:
        # if there is only one player left in the game, the game is over and that player wins
        game.status = GameStatus.FINISHED
        db.commit()

        await game_events.emit_winner(game_id,game.players[0].id, db)

    if game.status == GameStatus.LOBBY:
        await lobby_events.emit_players_lobby(game_id, db)
        await lobby_events.emit_can_start_game(game_id, db)

    if game.status == GameStatus.INGAME:
        await game_events.emit_players_game(game_id, db)

    return {"message": f"Player {player.name} has left the game."}
