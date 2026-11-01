from pathlib import Path
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
import chess

from windows_app.main import StockfishService

app = QCoreApplication([])
engine_path = Path("windows_app/stockfish/stockfish.exe").resolve()
assert engine_path.is_file(), f"Stockfish not found: {engine_path}"

service = StockfishService(str(engine_path))
service.start()

def wait_for_position(game_id, board):
    loop = QEventLoop()
    received = []
    errors = []

    def on_position(gid, score):
        if gid == game_id:
            received.append(score)
            loop.quit()

    def on_error(gid, message):
        errors.append(f"{gid}: {message}")
        loop.quit()

    service.positionReady.connect(on_position)
    service.analysisFailed.connect(on_error)
    service.request_position(game_id, board)
    QTimer.singleShot(20000, loop.quit)
    loop.exec()
    service.positionReady.disconnect(on_position)
    service.analysisFailed.disconnect(on_error)
    assert not errors, "; ".join(errors)
    assert received, f"No Stockfish response for {game_id}"
    assert service.isRunning(), "Persistent Stockfish service unexpectedly stopped"
    return received[0]

try:
    score1 = wait_for_position("SMOKE-1", chess.Board())
    board = chess.Board()
    board.push_uci("e2e4")
    score2 = wait_for_position("SMOKE-2", board)
    assert isinstance(score1, int) and isinstance(score2, int)
finally:
    service.stop()
    assert service.wait(6000), "Stockfish service did not shut down cleanly"

print("Persistent Stockfish service OK: two positions, one worker process, clean shutdown")
