from pathlib import Path
import os
import sys
import tempfile
import json
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APPDATA = tempfile.mkdtemp(prefix="c5r-regression-")
os.environ["APPDATA"] = APPDATA
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QFileDialog
import chess

from windows_app.main import MainWindow, PLAYERS, GAMES, storage_path
from windows_app.c5r_storage import atomic_write_json, read_document, decode_document, StorageIntegrityError

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
    assert abs(window.clock_data("R1-M1")["white"] - (initial_white + 3)) < 0.5

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

    # Storage: schema migration, checksum verification and fallback to the last valid copy.
    storage_test = Path(APPDATA) / "integrity-test.json"
    atomic_write_json(storage_test, {"results": {}, "schedule": []})
    atomic_write_json(storage_test, {"results": {"R1-M1": "1-0"}, "schedule": []})
    raw = json.loads(storage_test.read_text(encoding="utf-8"))
    raw["results"]["R1-M1"] = "0-1"  # Deliberate corruption without updating SHA-256.
    storage_test.write_text(json.dumps(raw), encoding="utf-8")
    recovered, backup_used = read_document(storage_test)
    assert backup_used is not None and recovered["results"] == {}
    try:
        decode_document(raw)
        raise AssertionError("The checksum validator accepted a corrupted file.")
    except StorageIntegrityError:
        pass

    # Elapsed-time clock accounting survives a stalled UI/suspended Windows session.
    window.results = {}
    window.clocks = {}
    window._clock_runtime = {}
    window.start_clock("R1-M1")
    clock = window.clock_data("R1-M1")
    before = float(clock["white"])
    clock["last_wall"] = time.time() - 1.4
    window._clock_runtime["R1-M1"] = time.monotonic() - 1.4
    _, after, elapsed = window._advance_clock("R1-M1")
    assert elapsed >= 1.2 and before - after >= 1.2

    # Global undo/redo restores tournament actions while leaving active clock runtime alone.
    window._undo_stack.clear()
    window._redo_stack.clear()
    window.results = {}
    window._last_history_state = window._history_snapshot(window.state_payload())
    window.results["R1-M1"] = "1-0"
    window.save(automatic_snapshot=False)
    assert window._undo_stack
    window.undo_history()
    assert window.results.get("R1-M1") is None
    window.redo_history()
    assert window.results.get("R1-M1") == "1-0"

    # Advanced forecasts expose three sensitivity scenarios and calibration diagnostics.
    forecast, brier, sample, current, form = window.advanced_forecast(500)
    assert set(forecast) == {"Prudente", "Base", "Sensibilità alta"}
    assert all(0.0 <= value[0] <= 1.0 for scenario in forecast.values() for value in scenario.values())
    assert sample >= 0 and (brier is None or 0.0 <= brier <= 1.0)

    # Theme, type scale, table density and named UI profiles persist through tournament saves.
    window.ui_preferences = {"theme": "light", "font_scale": 1.1, "density": "compact"}
    window.apply_ui_preferences()
    assert window.ui_theme_combo.currentData() == "light"
    assert window.ui_density_combo.currentData() == "compact"
    window.ui_preferences = {"theme": "dark", "font_scale": 1.0, "density": "comfortable"}
    window.ui_profiles["Test arbitro"] = dict(window.ui_preferences)
    window.apply_ui_preferences()
    assert window.ui_profile_combo.findData("Test arbitro") >= 0

    # The official PDF report is a real multi-page-capable PDF export, not only a standings sheet.
    report_path = str(Path(APPDATA) / "official-report.pdf")
    old_save_dialog = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = lambda *args, **kwargs: (report_path, "PDF (*.pdf)")
    try:
        window.export_tournament_report_pdf()
        assert Path(report_path).is_file() and Path(report_path).stat().st_size > 500
    finally:
        QFileDialog.getSaveFileName = old_save_dialog

    # Incident reports: structured minutes, local attachments, immutable match context and exports.
    evidence_one = Path(APPDATA) / "referto-arbitrale.txt"
    evidence_one.write_text("Dichiarazione scritta acquisita dal direttore di gara.", encoding="utf-8")
    evidence_two = Path(APPDATA) / "foto-tavolo.txt"
    evidence_two.write_text("Descrizione del documento allegato.", encoding="utf-8")
    incident = window.save_incident_report({
        "category": "Contestazione",
        "game_id": "R1-M1",
        "participants": "Jacopo, Roberto",
        "summary": "Contestazione su una decisione durante la partita",
        "description": "Alle 15:42 viene presentata una contestazione. Il direttore di gara ascolta entrambi i giocatori.",
        "decision": "La decisione viene confermata dopo verifica del regolamento.",
        "status": "In esame",
        "referee": "Arbitro test",
    }, [{"source": str(evidence_one)}])
    assert incident["id"].startswith("INC-")
    assert incident["game_label"].startswith("Round 1 · R1-M1")
    first_attachment = incident["attachments"][0]
    first_attachment_path = window.incident_attachment_path(first_attachment["path"])
    assert first_attachment_path.is_file()
    # Replacing the attachment removes the old file only after the new copy succeeds.
    updated_incident = window.save_incident_report({
        **incident,
        "status": "Risolto",
        "decision": "Contestazione respinta; risultato confermato.",
    }, [{"source": str(evidence_two)}])
    assert updated_incident["id"] == incident["id"]
    assert updated_incident["status"] == "Risolto"
    assert not first_attachment_path.exists()
    second_attachment_path = window.incident_attachment_path(updated_incident["attachments"][0]["path"])
    assert second_attachment_path.is_file()
    persisted, _ = read_document(storage_path())
    assert persisted["incident_reports"][0]["summary"] == incident["summary"]
    assert persisted["incident_reports"][0]["attachments"][0]["name"] == "foto-tavolo.txt"
    # UI registration and CSV/PDF export are reachable from the incident register.
    window.refresh_all()
    assert len(window._page_keys) == 17
    assert window.incident_table.rowCount() == 1
    window.incident_table.selectRow(0)
    incident_pdf = str(Path(APPDATA) / "verbale-incidente.pdf")
    old_save_dialog = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = lambda *args, **kwargs: (incident_pdf, "PDF (*.pdf)")
    try:
        window.export_selected_incident_pdf()
        assert Path(incident_pdf).is_file() and Path(incident_pdf).stat().st_size > 500
    finally:
        QFileDialog.getSaveFileName = old_save_dialog
    incident_csv = str(Path(APPDATA) / "verbali.csv")
    QFileDialog.getSaveFileName = lambda *args, **kwargs: (incident_csv, "CSV (*.csv)")
    try:
        window.export_incidents_csv()
        assert Path(incident_csv).is_file()
        assert "Contestazione" in Path(incident_csv).read_text(encoding="utf-8-sig")
    finally:
        QFileDialog.getSaveFileName = old_save_dialog
    # Reject path traversal outside the local incident evidence folder.
    try:
        window.incident_attachment_path("../tournament.json")
        raise AssertionError("An attachment path outside the incidents folder was accepted.")
    except ValueError:
        pass

    print("C5R Windows regression OK: tournament rules, PGN, recovery, precision clocks, undo/redo, predictive scenarios, UI profiles, PDF exports and incident reports.")
finally:
    QMessageBox.question = old_question
    window.close()
