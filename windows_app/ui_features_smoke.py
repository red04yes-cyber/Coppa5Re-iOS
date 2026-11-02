"""Focused smoke tests for the Windows-only filters, empty states and appearance preferences."""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

with tempfile.TemporaryDirectory(prefix="c5r-ui-smoke-") as appdata:
    os.environ["APPDATA"] = appdata

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    import windows_app.main as ui

    app = QApplication([])
    window = ui.MainWindow()
    try:
        # Empty archive gets its explanatory CTA before the first result exists.
        assert window.archive_table.rowCount() == 0
        assert not window.archive_empty.isHidden()

        # Instant search + round filter combine with AND semantics.
        window.calendar_search.setText("jacopo")
        window.filter_round.setCurrentText("Round 1")
        visible = [card for card in window.calendar_cards.values() if not card.isHidden()]
        assert len(visible) == 1, f"Expected one Round 1 Jacopo match, got {len(visible)}"
        window.reset_calendar_filters()
        assert all(not card.isHidden() for card in window.calendar_cards.values())

        # Archive search + result filters combine and can be reset.
        window.results["R1-M1"] = "1-0"
        window.results["R2-M2"] = "0-1"
        window.refresh_archive()
        assert window.archive_table.rowCount() == 2
        window.archive_search.setText("jacopo")
        window.archive_filter_result.setCurrentIndex(window.archive_filter_result.findData("1-0"))
        assert sum(not window.archive_table.isRowHidden(r) for r in range(2)) == 1
        window.reset_archive_filters()
        assert sum(not window.archive_table.isRowHidden(r) for r in range(2)) == 2

        # Sorted archive rows retain their game identity for row actions.
        window.archive_table.sortItems(1, Qt.SortOrder.DescendingOrder)
        window.archive_table.selectRow(0)
        selected = window.selected_archive_entry()
        assert selected and selected[1] in {"R1-M1", "R2-M2"}

        # Appearance changes apply immediately and persist across application restart.
        window.theme_combo.setCurrentText("Light")
        window.accent_combo.setCurrentText("Blue")
        window.density_combo.setCurrentText("Compatta")
        window.reduced_motion_check.setChecked(True)
        assert ui.BG == ui.THEMES["Light"]["bg"]
        assert all(card.board.reduced_motion for card in window.live_cards)
        window.close()

        reopened = ui.MainWindow()
        try:
            assert reopened.ui_preferences["theme"] == "Light"
            assert reopened.ui_preferences["accent"] == "Blue"
            assert reopened.ui_preferences["density"] == "Compatta"
            assert reopened.ui_preferences["reduced_motion"] is True
            assert all(card.board.reduced_motion for card in reopened.live_cards)
        finally:
            reopened.close()
    finally:
        if window.isVisible():
            window.close()

print("Windows UI filters, empty states, sorting and preferences OK")
