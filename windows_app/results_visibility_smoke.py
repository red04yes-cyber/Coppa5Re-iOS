"""Windows smoke test: visible results, local persistence, filters and accent preferences."""
from pathlib import Path
import os, sys, tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ["APPDATA"]=tempfile.mkdtemp(prefix="c5r-results-ui-")
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QMessageBox
from windows_app.main import MainWindow,storage_path
from windows_app.c5r_storage import atomic_write_json,read_document
app=QApplication([])
old_warning,old_critical=QMessageBox.warning,QMessageBox.critical
QMessageBox.warning=lambda *a,**k: QMessageBox.StandardButton.Ok
QMessageBox.critical=lambda *a,**k: QMessageBox.StandardButton.Ok
atomic_write_json(storage_path(),{"engine_enabled":False})
window=MainWindow()
try:
    assert window.dashboard_results_table.rowCount()==0
    assert not window.dashboard_results_empty.isHidden()
    window.set_result("R1-M1","1-0",confirm=False)
    window.set_result("R2-M2","0-1",confirm=False)
    assert window.dashboard_results_table.rowCount()==2
    shown=[window.dashboard_results_table.item(r,4).text() for r in range(2)]
    assert "1  –  0" in shown and "0  –  1" in shown
    assert window.archive_table.rowCount()==2
    stored,fallback=read_document(storage_path())
    assert fallback is None
    assert stored["results"]["R1-M1"]=="1-0" and stored["results"]["R2-M2"]=="0-1"

    window.archive_search.setText("jacopo")
    window.archive_filter_result.setCurrentIndex(window.archive_filter_result.findData("1-0"))
    assert sum(not window.archive_table.isRowHidden(r) for r in range(2))==1
    window.reset_archive_filters()
    assert sum(not window.archive_table.isRowHidden(r) for r in range(2))==2
    window.archive_table.sortItems(1,Qt.SortOrder.DescendingOrder)
    window.archive_table.selectRow(0)
    assert window.selected_archive_entry() is not None

    window.calendar_search.setText("jacopo")
    window.filter_round.setCurrentText("Round 1")
    assert sum(not card.isHidden() for card in window.calendar_cards.values())==1
    window.reset_calendar_filters()
    assert sum(not card.isHidden() for card in window.calendar_cards.values())==10

    window.ui_theme_combo.setCurrentIndex(window.ui_theme_combo.findData("light"))
    window.ui_accent_combo.setCurrentIndex(window.ui_accent_combo.findData("Blue"))
    window.ui_density_combo.setCurrentIndex(window.ui_density_combo.findData("compact"))
    window.save_ui_preferences()
finally:
    window.close()

reopened=MainWindow()
try:
    assert reopened.results["R1-M1"]=="1-0" and reopened.results["R2-M2"]=="0-1"
    assert reopened.dashboard_results_table.rowCount()==2
    assert reopened.ui_preferences["theme"]=="light"
    assert reopened.ui_preferences["accent"]=="Blue"
    assert reopened.ui_preferences["density"]=="compact"
finally:
    reopened.close()
    QMessageBox.warning,QMessageBox.critical=old_warning,old_critical
print("Windows EXE results visibility, data persistence, filters, sorting and accent preferences OK")
