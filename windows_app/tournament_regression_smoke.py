from pathlib import Path
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APPDATA = tempfile.mkdtemp(prefix="c5r-regression-")
os.environ["APPDATA"] = APPDATA
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
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

    # Pro tools: player profile statistics, common opening recognition and health validation.
    window.results = {"R1-M1": "1-0"}
    window.moves = {"R1-M1": ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"]}
    window.boards.clear()
    window.move_reviews = {}
    window.move_annotations = {"R1-M1": {"5": {"note": "Idea tattica", "variation": "Nf6"}}}
    window.round_closures = {}
    window.clocks = {}
    window.playoff_results = {}
    window.playoff_winners = {}
    profile = window.player_profile_data("jacopo")
    assert profile["played"] == 1 and profile["wins"] == 1
    assert profile["history"][0]["opening"] == "Italiana"
    assert window.opening_name("R1-M1") == "Italiana"

    # Per-move comments and SAN continuations are exported into the PGN.
    annotated_pgn = window.build_pgn_game("R1-M1")
    annotated_moves = list(annotated_pgn.mainline())
    assert "Idea tattica" in annotated_moves[4].comment
    assert len(annotated_moves[4].variations) == 1
    exported = annotated_pgn.accept(chess.pgn.StringExporter(headers=True, variations=True, comments=True))
    assert "Nota C5R" in exported and "Nf6" in exported

    # Health Check detects closed rounds with missing results and clears the warning once resolved.
    window.round_closures = {"1": "02/11/2026 10:00"}
    assert any(severity == "ERRORE" and title == "Turno chiuso ma incompleto"
               for severity, title, _ in window.health_check())
    window.round_closures = {}
    assert not any(severity == "ERRORE" for severity, _, _ in window.health_check())

    # Snapshot persistence and restore retain both tournament state and move annotations.
    snapshot = window.create_snapshot("Test manuale regression")
    assert snapshot is not None and snapshot.is_file()
    entries = window.snapshot_entries()
    selected_entry = next(entry for entry in entries if entry[0] == snapshot)
    labels = [f"{created.replace('T', ' ')} · {reason} · {path.name}" for path, created, reason in entries]
    selected_label = labels[entries.index(selected_entry)]
    old_get_item = QInputDialog.getItem
    QInputDialog.getItem = lambda *args, **kwargs: (selected_label, True)
    try:
        window.results["R1-M1"] = "0-1"
        assert window.restore_snapshot() is True
        assert window.results["R1-M1"] == "1-0"
        assert window.move_annotations["R1-M1"]["5"]["note"] == "Idea tattica"
    finally:
        QInputDialog.getItem = old_get_item

    # The new pages and global tools are all wired in the live desktop window.
    window.refresh_all()
    assert len(window._page_keys) == 16
    assert len(window.profile_tiles) == 4
    assert len(window.compare_tiles) == 2
    assert window.opening_table.rowCount() == len(GAMES)
    assert hasattr(window, "notification_button")
    assert isinstance(window.collect_notifications(), list)
    window.run_health_check()
    assert window.health_list.count() >= 1

    print("C5R Windows regression OK: tournament rules, PGN, recovery, profiles, opening explorer, health check, move annotations, snapshots and UI tools.")
finally:
    QMessageBox.question = old_question
    window.close()
