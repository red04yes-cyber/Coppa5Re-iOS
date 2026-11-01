from pathlib import Path
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APPDATA = tempfile.mkdtemp(prefix="c5r-regression-")
os.environ["APPDATA"] = APPDATA
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox
import chess

from windows_app.main import MainWindow, PLAYERS, GAMES

app = QApplication([])
window = MainWindow()
old_question = QMessageBox.question
QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Yes

try:
    # Article 5: phase-specific time controls.
    assert window.time_control_for_game("R1-M1") == "15+3"
    assert window.time_control_for_game("sf1") == "30+10"
    assert window.clock_data("sf1")["white"] == 30 * 60

    # Article 8: two-player head-to-head applies only to a two-way tie.
    window.results = {"R1-M1": "1-0"}
    h2h_win = window.tie_break_value("jacopo", ["jacopo", "roberto"])
    h2h_loss = window.tie_break_value("roberto", ["jacopo", "roberto"])
    multi_tie = window.tie_break_value("jacopo", ["jacopo", "roberto", "matteo"])
    assert h2h_win[0] == 1.0 and h2h_loss[0] == 0.0
    assert multi_tie[0] == 0.0

    # A mutually accepted draw and a resignation keep their formal PGN result.
    window.results = {}
    window.moves = {}
    window.boards.clear()
    window.offer_draw("R1-M1")
    assert window.results["R1-M1"] == "1/2-1/2"
    draw_pgn = window.build_pgn_game("R1-M1")
    assert draw_pgn.headers["Result"] == "1/2-1/2"
    window.set_result("R1-M1", None, confirm=False)
    window.resign_game("R1-M1")
    assert window.results["R1-M1"] == "0-1"
    resign_pgn = window.build_pgn_game("R1-M1")
    assert resign_pgn.headers["Result"] == "0-1"
    assert resign_pgn.headers["Termination"] == "abandoned"

    # Article 5: the 15+3 clock awards +3 to the player who just moved.
    window.engine_enabled = False
    window.results = {}
    window.moves = {}
    window.boards.clear()
    window.clocks.clear()
    window.start_clock("R1-M1")
    initial_white = window.clock_data("R1-M1")["white"]
    window.record_move("R1-M1", "e2e4")
    assert window.clock_data("R1-M1")["white"] == initial_white + 3

    # Checkmate and stalemate are detected automatically after the terminal move.
    window.moves = {}
    window.boards.clear()
    window.clocks.clear()
    window.results = {}
    for uci in ("f2f3", "e7e5", "g2g4", "d8h4"):
        window.record_move("R1-M1", uci)
    assert window.results["R1-M1"] == "0-1"
    assert window.game_terminations["R1-M1"]["detail"] == "checkmate"
    window.results = {}
    window.moves = {}
    window.boards.clear()
    window.boards["R1-M1"] = chess.Board("7k/5K2/8/6Q1/8/8/8/8 w - - 0 1")
    window.record_move("R1-M1", "g5g6")
    assert window.results["R1-M1"] == "1/2-1/2"
    assert window.game_terminations["R1-M1"]["detail"] == "stalemate"

    # Move annotations and the local C5R precision calculation are preserved in PGN.
    window.results = {"R1-M1": "1/2-1/2"}
    window.moves = {"R1-M1": ["e2e4"]}
    window.boards.clear()
    window.move_reviews = {"R1-M1": [{
        "ply": 1, "player": "jacopo", "uci": "e2e4", "label": "OTTIMA",
        "expected_points_loss": 0.004, "before_cp": 0, "after_cp": 0, "best_uci": "e2e4"
    }]}
    reviewed = window.build_pgn_game("R1-M1")
    first_move = next(iter(reviewed.mainline()))
    assert "OTTIMA" in first_move.comment
    assert chess.pgn.NAG_GOOD_MOVE in first_move.nags
    assert window.accuracy_for_player("R1-M1", "jacopo") > 99.0

    # Article 11: below two completed matches all qualification results are annulled.
    window.results = {"R1-M1": "1-0"}
    window.moves = {}
    window.withdrawn_players = {}
    window.withdraw_player("jacopo")
    jacopo_games = [g[0] for g in GAMES if "jacopo" in (g[2], g[3])]
    assert all(window.results.get(gid) == "VOID" for gid in jacopo_games)
    raw, played, *_ = window.raw_stats()
    assert played["jacopo"] == 0

    # Article 11: with at least two completed matches, keep them and award remaining byes.
    window.results = {"R1-M1": "1-0", "R2-M2": "1-0"}
    window.withdrawn_players = {}
    window.withdraw_player("jacopo")
    assert window.results["R1-M1"] == "1-0"
    assert window.results["R2-M2"] == "1-0"
    assert window.results["R4-M2"] == "1-0"  # Matteo is White against withdrawn Jacopo.
    assert window.results["R5-M1"] == "0-1"  # Simone is Black against withdrawn Jacopo.

    # Playoff draw / Armageddon record and 30+10 clock with +10 per completed move.
    window.playoff_results = {}
    window.playoff_winners = {}
    window.refresh_playoffs()
    pair = window.playoff_pairs["sf1"]
    window.set_playoff_result("sf1", "1/2-1/2", detail="Patta · Armageddon da disputare")
    window.set_playoff_winner("sf1", pair[0])
    playoff_pgn = window.build_playoff_pgn("sf1")
    assert playoff_pgn.headers["Result"] == "1/2-1/2"
    assert playoff_pgn.headers["TimeControl"] == "1800+10"
    assert playoff_pgn.headers["C5R_ArmageddonWinner"] == PLAYERS[pair[0]][0]

    window.playoff_results.pop("sf2", None)
    clock = window.clock_data("sf2")
    window.start_playoff_clock("sf2")
    before_white = clock["white"]
    window.switch_playoff_clock("sf2")
    assert clock["white"] == before_white + 10
    assert clock["side_to_move"] == "black"
    assert window.recovery_path.is_file()
    clock["black"] = 1
    window.tick_clocks()
    assert window.playoff_results["sf2"] == "1-0"
    assert not clock["started"]

    print("C5R Windows regression OK: Art.5 clocks, Art.8 tiebreak, draw/resignation PGNs, move review, Art.11 withdrawals, Armageddon and flag fall.")
finally:
    QMessageBox.question = old_question
    window.close()
