"""Regression test for the QR spectator page's live chessboard and move feed."""
from pathlib import Path
import json
import os
import sys
import tempfile
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="c5r-qr-live-board-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import chess
from PySide6.QtWidgets import QApplication
from windows_app.main import MainWindow

app = QApplication([])
window = MainWindow()
server = None
try:
    game_id = "R1-M1"
    board = chess.Board()
    sequence = ["e2e4", "e7e5", "g1f3"]
    for uci in sequence:
        board.push_uci(uci)
    window.moves[game_id] = list(sequence)
    window.boards[game_id] = board

    state = window.match_web_state(game_id)
    assert state is not None
    assert state["fen"] == board.fen()
    assert state["last_move"] == "g1f3"
    assert state["move_text"] == "1. e4 e5 2. Nf3"
    assert state["turn"] == "Nero"
    assert state["ply"] == 3

    page = window.match_web_html(game_id)
    assert page is not None
    assert "SCACCHIERA LIVE" in page
    assert "CRONOLOGIA MOSSE" in page
    assert "id='board'" in page
    assert "function renderBoard(state)" in page
    assert "window.setInterval(poll,1000)" in page
    assert "api/match/R1-M1" in page
    assert "http-equiv='refresh'" not in page

    # A new legal move must change both the FEN and last-move marker in the feed.
    board.push_uci("b8c6")
    window.moves[game_id] = [move.uci() for move in board.move_stack]
    next_state = window.match_web_state(game_id)
    assert next_state["fen"] == board.fen()
    assert next_state["last_move"] == "b8c6"
    assert next_state["move_text"] == "1. e4 e5 2. Nf3 Nc6"

    # Verify that the live JSON endpoint returns the same current position as the page model.
    _, port = window.start_match_web_server("127.0.0.1")
    server = window.match_http_server
    # Spectator endpoints require the per-tournament bearer token.
    endpoint = f"http://127.0.0.1:{port}/api/match/{game_id}"
    try:
        urllib.request.urlopen(endpoint, timeout=5)
        raise AssertionError("QR API unexpectedly accepted a request without a token")
    except urllib.error.HTTPError as exc:
        assert exc.code == 403
    with urllib.request.urlopen(
        endpoint + "?token=" + urllib.parse.quote(window.spectator_token, safe=""),
        timeout=5
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    assert payload["fen"] == next_state["fen"]
    assert payload["last_move"] == "b8c6"
    assert payload["move_text"] == next_state["move_text"]
finally:
    if server is not None:
        server.shutdown()
        server.server_close()
    window.close()

print("QR spectator page, chessboard FEN, live move feed and JSON endpoint OK")
