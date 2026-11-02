"""Windows regression: dashboard result visibility and safe local recovery."""
from pathlib import Path
import os
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="c5r-results-visible-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox
from windows_app.main import MainWindow, storage_path
from windows_app.c5r_storage import read_document

app = QApplication([])
old_warning = QMessageBox.warning
old_critical = QMessageBox.critical
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QMessageBox.critical = lambda *args, **kwargs: QMessageBox.StandardButton.Ok

window = MainWindow()
try:
    assert window.dashboard_results_table.rowCount() == 0
    assert window.dashboard_results_table.isHidden()
    assert not window.dashboard_results_empty.isHidden()

    # Enter two real results through the same application callback used by the UI.
    window.set_result("R1-M1", "1-0", confirm=False, detail="Smoke test risultati")
    window.set_result("R2-M2", "0-1", confirm=False, detail="Smoke test risultati")

    table = window.dashboard_results_table
    assert table.rowCount() == 2
    visible = {
        table.item(row, 1).text(): table.item(row, 4).text()
        for row in range(table.rowCount())
    }
    assert visible["R1-M1"] == "1  –  0"
    assert visible["R2-M2"] == "0  –  1"
    assert not table.isHidden()
    assert window.dashboard_results_empty.isHidden()

    # The existing views and counters receive the same result update.
    assert window.calendar_combos["R1-M1"].currentData() == "1-0"
    assert window.calendar_combos["R2-M2"].currentData() == "0-1"
    assert window.archive_table.rowCount() == 2
    assert "2/10" in window.dashboard_tiles["done"].hint.text()
    assert sum(row["points"] for row in window.standings()) == 2.0

    # Persist and restart: the dashboard must show the same scores in the EXE session.
    assert window.save(automatic_snapshot=False) is True
    path = storage_path()
    saved, fallback = read_document(path)
    assert fallback is None
    assert saved["results"]["R1-M1"] == "1-0"
    assert saved["results"]["R2-M2"] == "0-1"
finally:
    window.close()

reopened = MainWindow()
try:
    assert reopened.results["R1-M1"] == "1-0"
    assert reopened.results["R2-M2"] == "0-1"
    assert reopened.dashboard_results_table.rowCount() == 2
    assert {
        reopened.dashboard_results_table.item(row, 1).text():
        reopened.dashboard_results_table.item(row, 4).text()
        for row in range(reopened.dashboard_results_table.rowCount())
    } == {"R1-M1": "1  –  0", "R2-M2": "0  –  1"}
finally:
    reopened.close()

# Damage the main file: the app should recover both results from the rotated backup.
path = storage_path()
backup = path.with_suffix(path.suffix + ".bak")
shutil.copy2(path, backup)
path.write_text("{ damaged json", encoding="utf-8")
recovered = MainWindow()
try:
    assert recovered.results["R1-M1"] == "1-0"
    assert recovered.results["R2-M2"] == "0-1"
    assert recovered.dashboard_results_table.rowCount() == 2
    assert recovered.state_load_blocked is False
finally:
    recovered.close()

# If there is no valid backup, never replace the damaged file with empty results.
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="c5r-results-blocked-")
blocked_path = storage_path()
blocked_path.write_text("{ damaged json", encoding="utf-8")
damaged_before = blocked_path.read_text(encoding="utf-8")
blocked = MainWindow()
try:
    assert blocked.state_load_blocked is True
    blocked.set_result("R1-M1", "1-0", confirm=False)
    assert blocked.results == {}
    assert blocked.save() is False
    assert blocked_path.read_text(encoding="utf-8") == damaged_before
finally:
    blocked.close()
    QMessageBox.warning = old_warning
    QMessageBox.critical = old_critical

assert blocked_path.read_text(encoding="utf-8") == damaged_before
print("Windows dashboard result visibility, restart persistence, backup recovery and write protection OK")
