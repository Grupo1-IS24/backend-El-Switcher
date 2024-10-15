from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.schemas.board import PieceResponseSchema
from app.schemas.move import MakeMoveSchema
from app.db.db import Board, Color, SquarePiece, ParallelBoard, CardMove, Player, MoveType
from typing import List
import random
import json

def create_board(game_id: int, db: Session) -> List[PieceResponseSchema]:
    board = Board(game_id=game_id)
    db.add(board)
    db.commit()
    db.refresh(board)


    #debe ser una lista con los colores posibles, siendo 9 de cada uno 
    possible_colors = [Color.RED, Color.GREEN, Color.BLUE, Color.YELLOW] * 9


    # 6x6 board
    for row in range(6):
        for column in range(6):
            # Elegir un color aleatorio para cada pieza
            random_color = random.choice(possible_colors)
            possible_colors.remove(random_color)

            # Crear una instancia de SquarePiece
            square_piece = SquarePiece(
                color=random_color,
                row=row,
                column=column,
                board_id=board.game_id  
            )

            db.add(square_piece)
    db.commit()


def get_pieces(game_id: int, db: Session):
    return db.query(SquarePiece).filter(SquarePiece.board_id == game_id).all()

def get_board(game_id: int, db: Session) -> List[PieceResponseSchema]:
    square_pieces = get_pieces(game_id, db)
    return [PieceResponseSchema(
                squarePieceId=piece.id,
                color=piece.color.name,  # Enum to string
                row=piece.row,
                column=piece.column
            ).model_dump() for piece in square_pieces]

async def make_move(game_id: int, player_id: int, move_data: MakeMoveSchema, db: Session):
    try:
        card_move = db.query(CardMove).filter(CardMove.id == move_data.movementCardId).first()
        if not card_move:
            raise ValueError("Invalid movementCardId")
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise ValueError("Player not found")

        save_board(game_id, player_id, db)
        switch_pieces(move_data.squarePieceId1, move_data.squarePieceId2, card_move.move, db)  
        
        from app.services.game_events import emit_board
        await emit_board(game_id, db)
        
    except SQLAlchemyError as e:
        db.rollback()
        raise RuntimeError(f"Error making move: {e}")
    except ValueError as e:
        raise RuntimeError(f"Validation error: {e}")

def save_board(game_id: int, player_id: int, db: Session):
    try:
        state_data = json.dumps(get_board(game_id, db))

        existing_states = db.query(ParallelBoard).filter_by(board_id=game_id).order_by(ParallelBoard.state_id).all()
        if existing_states:
            latest_state_id = (existing_states[-1].state_id % 3) + 1
        else:
            latest_state_id = 1

        parallel_board = ParallelBoard(
            board_id=game_id,
            player_id=player_id,
            state_id=latest_state_id,
            state_data=state_data
        )
        db.add(parallel_board)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        raise RuntimeError(f"Error saving board state: {e}")

def switch_pieces(piece_id1: int, piece_id2: int, move_type:MoveType, db: Session):
    try:
        piece1 = db.query(SquarePiece).filter(SquarePiece.id == piece_id1).first()
        piece2 = db.query(SquarePiece).filter(SquarePiece.id == piece_id2).first()
        
        if not piece1:
            raise ValueError("Piece 1 not found")
        if not piece2:
            raise ValueError("Piece 2 not found")
        
        if validate_move(piece1, piece2, move_type):
            piece1.row, piece2.row = piece2.row, piece1.row
            piece1.column, piece2.column = piece2.column, piece1.column
            db.commit()
        else:
            raise ValueError("Invalid move")
    except SQLAlchemyError as e:
        db.rollback()
        raise RuntimeError(f"Error switching pieces: {e}")
    except ValueError as e:
        raise RuntimeError(f"Validation error: {e}")

def validate_move(piece1, piece2, move_type: MoveType):
    row_diff = abs(piece1.row - piece2.row)
    col_diff = abs(piece1.column - piece2.column)

    row_rdiff = piece1.row - piece2.row

    if move_type == MoveType.MOV_1:
        return row_diff == 2 and col_diff == 2
    elif move_type == MoveType.MOV_2:
        return (row_diff == 2 and col_diff == 0) or (row_diff == 0 and col_diff == 2)
    elif move_type == MoveType.MOV_3:
        return (row_diff == 1 and col_diff == 0) or (row_diff == 0 and col_diff == 1)
    elif move_type == MoveType.MOV_4:
        return row_diff == 1 and col_diff == 1
    elif move_type == MoveType.MOV_5:
        return ((row_rdiff == 2 and col_diff == 1) or (row_rdiff == 1 and col_diff == 2))
    elif move_type == MoveType.MOV_6:
        return ((row_rdiff == -2 and col_diff == 1) or (row_rdiff == -1 and col_diff == 2))
    elif move_type == MoveType.MOV_7:
        return row_diff == 4 or col_diff == 4
    return False