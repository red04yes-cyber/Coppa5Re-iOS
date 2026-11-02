"""Smoke test for the reusable premium Windows player and match widgets."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget

from windows_app.c5r_theme import C, fmt_clock
from windows_app.c5r_widgets import FormStrip, MatchLine, PlayerStrip, Swatch


def main() -> None:
    app = QApplication.instance() or QApplication([])

    swatch = Swatch(True)
    swatch.set_white(False)
    assert swatch._white is False

    player = PlayerStrip()
    photo = QPixmap(32, 32)
    photo.fill(QColor(C.info))
    player.set_photo(photo)
    player.set_data(
        "Jacopo",
        "Chess.com · BL 1500",
        C.info,
        True,
        899,
        True,
        True,
    )
    assert player.name.text() == "Jacopo"
    assert player.sub.text().endswith("Bianco")
    assert player.clock._text == fmt_clock(899)
    assert player.avatar._pixmap is not None

    form = FormStrip()
    form.set_items(["V", "X", "P", "V", "V"])
    assert form._items == ["X", "P", "V", "V"]

    match = MatchLine()
    match.set_players("Jacopo", "Roberto")
    assert match.n1.text() == "Jacopo"
    assert match.n2.text() == "Roberto"

    host = QWidget()
    layout = QHBoxLayout(host)
    layout.addWidget(player)
    layout.addWidget(match)
    host.show()
    app.processEvents()
    assert player.sizeHint().width() > 0
    host.close()
    print("Windows player strips, avatars, clocks, match lines and form indicators OK")


if __name__ == "__main__":
    main()
