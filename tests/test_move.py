import pytest

from app.db.db import SquarePiece, MoveType, GameStatus
from .db_setup import (
    client,
    TestingSessionLocal,
    create_game,
    add_example_board,
    create_player,
    create_card_move
)

@pytest.fixture(scope="module")
def test_client():
    yield client

def test_make_move(test_client):
    db = TestingSessionLocal()
    try:
        game = create_game(db, GameStatus.INGAME)
        add_example_board(db, game.id)
        player = create_player(db, game.id)
        card_move = create_card_move(db, player.id, MoveType.MOV_3)
        piece1 = db.query(SquarePiece).filter(SquarePiece.board_id == game.id).first()
        piece2 = db.query(SquarePiece).filter(SquarePiece.board_id == game.id, SquarePiece.id != piece1.id).first()

        movementCardId = card_move.id
        squarePieceId1 = piece1.id
        squarePieceId2 = piece2.id
        
        response = test_client.post(f"/game/{game.id}/move/{player.id}", json={
            "movementCardId": movementCardId,
            "squarePieceId1": squarePieceId1,
            "squarePieceId2": squarePieceId2
        })
        assert response.status_code == 200
    finally:
        db.close()

def generate_square_piece(row, column):
    return SquarePiece(row=row, column=column)

# Generate test cases for each MoveType
test_cases = {
    MoveType.MOV_1: { #CRUCE DIAGONAL CON UN ESPACIO
        "pass": (generate_square_piece(0, 0), generate_square_piece(2, 2)),
        "fail": (generate_square_piece(0, 0), generate_square_piece(1, 1))
    },
    MoveType.MOV_2: { #CRUCE EN LINEA CON UN ESPACIO
        "pass": (generate_square_piece(0, 0), generate_square_piece(2, 0)),
        "fail": (generate_square_piece(0, 0), generate_square_piece(1, 1))
    },
    MoveType.MOV_3: { #CRUCE EN LINEA CONTIGUO
        "pass": (generate_square_piece(0, 0), generate_square_piece(1, 0)),
        "fail": (generate_square_piece(0, 0), generate_square_piece(2, 2))
    },
    MoveType.MOV_4: { #CRUCE DIAGONAL CONTIGUO
        "pass": (generate_square_piece(0, 0), generate_square_piece(1, 1)),
        "fail": (generate_square_piece(0, 0), generate_square_piece(2, 2))
    },
    MoveType.MOV_5: { #CRUCE EN L A LA IZQUIERDA CON DOS ESPACIOS
        "pass": (generate_square_piece(2, 1), generate_square_piece(4, 0)),
        "fail": (generate_square_piece(0, 0), generate_square_piece(1, 1))
    },
    MoveType.MOV_6: { #CRUCE EN L A LA DERECHA CON DOS ESPACIOS
        "pass": (generate_square_piece(0, 0), generate_square_piece(2, 1)),
        "fail": (generate_square_piece(0, 0), generate_square_piece(1, 1))
    },
    MoveType.MOV_7: { #CRUCE EN LINEA AL LATERAL
        "pass": (generate_square_piece(0, 2), generate_square_piece(0, 5)),
        "fail": (generate_square_piece(0, 0), generate_square_piece(1, 1))
    }
}


@pytest.mark.parametrize("move_type, pieces, expected", [
    (MoveType.MOV_1, test_cases[MoveType.MOV_1]["pass"], True),
    (MoveType.MOV_2, test_cases[MoveType.MOV_2]["pass"], True),
    (MoveType.MOV_3, test_cases[MoveType.MOV_3]["pass"], True),
    (MoveType.MOV_4, test_cases[MoveType.MOV_4]["pass"], True),
    (MoveType.MOV_5, test_cases[MoveType.MOV_5]["pass"], True),
    (MoveType.MOV_6, test_cases[MoveType.MOV_6]["pass"], True),
    (MoveType.MOV_7, test_cases[MoveType.MOV_7]["pass"], True)
])
def test_move_types(test_client, move_type, pieces, expected):
    db = TestingSessionLocal()
    try:
        game = create_game(db, GameStatus.INGAME)
        add_example_board(db, game.id)
        player = create_player(db, game.id)
        card_move = create_card_move(db, player.id, move_type)
        
        piece1_coords, piece2_coords = pieces
        piece1 = db.query(SquarePiece).filter(SquarePiece.board_id == game.id, SquarePiece.row == piece1_coords.row, SquarePiece.column == piece1_coords.column).first()
        piece2 = db.query(SquarePiece).filter(SquarePiece.board_id == game.id, SquarePiece.row == piece2_coords.row, SquarePiece.column == piece2_coords.column).first()

        movementCardId = card_move.id
        squarePieceId1 = piece1.id
        squarePieceId2 = piece2.id
        
        response = test_client.post(f"/game/{game.id}/move/{player.id}", json={
            "movementCardId": movementCardId,
            "squarePieceId1": squarePieceId1,
            "squarePieceId2": squarePieceId2
        })
        assert response.status_code == 200
    finally:
        db.close()

@pytest.mark.parametrize("move_type, pieces, expected", [
    (MoveType.MOV_1, test_cases[MoveType.MOV_1]["fail"], False),
    (MoveType.MOV_2, test_cases[MoveType.MOV_2]["fail"], False),
    (MoveType.MOV_3, test_cases[MoveType.MOV_3]["fail"], False),
    (MoveType.MOV_4, test_cases[MoveType.MOV_4]["fail"], False),
    (MoveType.MOV_5, test_cases[MoveType.MOV_5]["fail"], False),
    (MoveType.MOV_6, test_cases[MoveType.MOV_6]["fail"], False),
    (MoveType.MOV_7, test_cases[MoveType.MOV_7]["fail"], False),
])
def test_move_types_fail(test_client, move_type, pieces, expected):
    db = TestingSessionLocal()
    try:
        game = create_game(db, GameStatus.INGAME)
        add_example_board(db, game.id)
        player = create_player(db, game.id)
        card_move = create_card_move(db, player.id, move_type)
        
        piece1_coords, piece2_coords = pieces
        piece1 = db.query(SquarePiece).filter(SquarePiece.board_id == game.id, SquarePiece.row == piece1_coords.row, SquarePiece.column == piece1_coords.column).first()
        piece2 = db.query(SquarePiece).filter(SquarePiece.board_id == game.id, SquarePiece.row == piece2_coords.row, SquarePiece.column == piece2_coords.column).first()

        movementCardId = card_move.id
        squarePieceId1 = piece1.id
        squarePieceId2 = piece2.id
        
        try:
            response = test_client.post(f"/game/{game.id}/move/{player.id}", json={
                "movementCardId": movementCardId,
                "squarePieceId1": squarePieceId1,
                "squarePieceId2": squarePieceId2
            })
            assert expected == True
        except Exception as e:
            assert expected == False
                
    finally:
        db.close()


def test_invalid_movement_card_id(test_client):
    db = TestingSessionLocal()
    game = create_game(db, GameStatus.INGAME)
    response = test_client.post(f"/game/{game.id}/move/1", json={
        "movementCardId": 999,  # Invalid ID
        "squarePieceId1": 1,
        "squarePieceId2": 2
    })
    assert response.status_code == 400
    assert "Invalid movementCardId" in response.json()["detail"]

def test_player_not_found(test_client):
    db = TestingSessionLocal()
    game = create_game(db, GameStatus.INGAME)
    card_move = create_card_move(db, 999, MoveType.MOV_3)
    response = test_client.post(f"/game/{game.id}/move/999", json={  # Invalid player ID
        "movementCardId": 1,
        "squarePieceId1": 1,
        "squarePieceId2": 2
    })
    assert response.status_code == 404
    assert "Player not found" in response.json()["detail"]

def test_invalid_move(test_client):
    db = TestingSessionLocal()
    game = create_game(db, GameStatus.INGAME)
    add_example_board(db, game.id)
    player = create_player(db, game.id)
    card_move = create_card_move(db, player.id, MoveType.MOV_3)
    try:
        response = test_client.post(f"/game/{game.id}/move/{player.id}", json={
            "movementCardId": card_move.id,
            "squarePieceId1": 1,
            "squarePieceId2": 1  # Invalid move (same piece)
        })
        assert response.status_code == 400
        assert "Pieces are the same" in response.json()["detail"]
    finally:
        db.close()

def test_invalid_piece1(test_client):
    db = TestingSessionLocal()
    game = create_game(db, GameStatus.INGAME)
    add_example_board(db, game.id)
    player = create_player(db, game.id)
    card_move = create_card_move(db, player.id, MoveType.MOV_3)
    try:
        response = test_client.post(f"/game/{game.id}/move/{player.id}", json={
            "movementCardId": card_move.id,
            "squarePieceId1": 999,
            "squarePieceId2": 1  # Invalid move (Piece 1 not found)
        })
        assert response.status_code == 400
        assert "Piece 1 not found" in response.json()["detail"]
    finally:
        db.close()

def test_invalid_piece2(test_client):
    db = TestingSessionLocal()
    game = create_game(db, GameStatus.INGAME)
    add_example_board(db, game.id)
    player = create_player(db, game.id)
    card_move = create_card_move(db, player.id, MoveType.MOV_3)
    try:
        response = test_client.post(f"/game/{game.id}/move/{player.id}", json={
            "movementCardId": card_move.id,
            "squarePieceId1": 1,
            "squarePieceId2": 999  # Invalid move (Piece 2 not found)
        })
        assert response.status_code == 400
        assert "Piece 2 not found" in response.json()["detail"]
    finally:
        db.close()