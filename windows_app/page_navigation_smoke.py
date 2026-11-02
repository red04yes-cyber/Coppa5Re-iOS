"""Regression test for Windows sidebar-to-page navigation mapping."""
import os
import sys
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="c5r-page-navigation-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel
from windows_app.main import MainWindow

app = QApplication([])
window = MainWindow()

def page_labels(key: str) -> list[str]:
    index = window._page_keys.index(key)
    scroll = window.tabs.widget(index)
    page = scroll.widget()
    return [label.text() for label in page.findChildren(QLabel)]

try:
    expected_headings = {
        "history": "Storico delle edizioni",
        "archive": "ARCHIVIO PARTITE",
        "h2h": "STATISTICHE TESTA A TESTA",
        "incidents": "Verbali degli incidenti",
    }
    for key, heading in expected_headings.items():
        labels = page_labels(key)
        assert any(heading.casefold() in value.casefold() for value in labels), (
            f"Sidebar key '{key}' is mapped to the wrong page; expected heading '{heading}', got {labels[:8]}"
        )
        window._navigate_to(key)
        assert window.tabs.currentIndex() == window._page_keys.index(key), (
            f"Navigation key '{key}' selected the wrong stacked page"
        )
finally:
    window.close()

print("Windows sidebar mapping OK: history, archive, head-to-head and incident reports")
