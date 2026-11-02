"""Design system C5R: palette, tipografia, icone SVG e QSS globale."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QLocale, QTranslator, QLibraryInfo, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


class C:
    bg = "#0A0F15"
    sidebar = "#0D131A"
    surface = "#121A23"
    surface2 = "#18222D"
    surface3 = "#202D3B"
    well = "#0C1219"
    line = "#263444"
    line_soft = "#1A2530"
    text = "#EDE7DA"
    text2 = "#AAB2BD"
    text3 = "#7C8899"
    brass = "#C9A15B"
    brass_hi = "#E3C07F"
    brass_lo = "#8F7240"
    on_brass = "#1A1307"
    success = "#58B394"
    danger = "#E0707A"
    warning = "#E0A64B"
    info = "#7FAEDD"
    check = "#C2454F"


class S:
    xs, sm, md, lg, xl, xxl = 4, 8, 12, 16, 24, 32


class R:
    sm, md, lg = 6, 10, 14


SANS = "IBM Plex Sans"
SERIF = "Spectral"
MONO = "IBM Plex Mono"
SYMBOLS = "Noto Sans Symbols 2"
PLAYER_TINTS = ["#6F8FB8", "#7FA58A", "#B58A6A", "#9A82B5", "#C3A25E"]


def player_tint(index: int) -> str:
    return PLAYER_TINTS[index % len(PLAYER_TINTS)]


def mix(a: str, b: str, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red()-ca.red())*t),
                  round(ca.green() + (cb.green()-ca.green())*t),
                  round(ca.blue() + (cb.blue()-ca.blue())*t))


def with_alpha(color: str | QColor, alpha: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def fmt_clock(seconds) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def assets_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    folder = base / "assets"
    return folder if folder.exists() else Path(__file__).resolve().parent / "assets"


_FONTS_LOADED = False


def load_fonts() -> None:
    global _FONTS_LOADED
    if _FONTS_LOADED:
        return
    folder = assets_dir() / "fonts"
    if folder.is_dir():
        for path in sorted(folder.glob("*.ttf")):
            QFontDatabase.addApplicationFont(str(path))
    _FONTS_LOADED = True


def font(family: str = SANS, px: int = 14, weight: int = 400, italic: bool = False) -> QFont:
    f = QFont(family)
    f.setPixelSize(px)
    f.setWeight(QFont.Weight(weight))
    f.setItalic(italic)
    return f


_ICONS = {
    "dashboard": '<rect x="3.5" y="3.5" width="7" height="8" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="5" rx="1.5"/><rect x="13.5" y="11.5" width="7" height="9" rx="1.5"/><rect x="3.5" y="14.5" width="7" height="6" rx="1.5"/>',
    "board": '<rect x="3.5" y="3.5" width="17" height="17" rx="2.2"/><path d="M12 3.5h6.3a2.2 2.2 0 0 1 2.2 2.2V12H12z"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15.5" rx="2.2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    "standings": '<path d="M3.5 20.5h17"/><rect x="9" y="7.5" width="6" height="13"/><rect x="3.5" y="12.5" width="5.5" height="8"/><rect x="15" y="15" width="5.5" height="5.5"/>',
    "trophy": '<path d="M8 4h8v5a4 4 0 0 1-8 0zM8 6H5a2.5 2.5 0 0 0 3 3.5M16 6h3a2.5 2.5 0 0 1-3 3.5M12 13v4M8.5 20.5h7M10 17h4"/>',
    "chart": '<path d="M4 4v16h16M8 15.5l3.5-4.5 3 2.5L19 8"/>',
    "versus": '<path d="M4 8h13l-3.5-3.5M20 16H7l3.5 3.5"/>',
    "archive": '<rect x="3.5" y="4" width="17" height="5" rx="1.4"/><path d="M5 9v9.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V9M10 13h4"/>',
    "log": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.8" cy="6" r=".7"/><circle cx="4.8" cy="12" r=".7"/><circle cx="4.8" cy="18" r=".7"/>',
    "settings": '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
    "shuffle": '<path d="M4 7h3c4.5 0 5 10 9.5 10H20M4 17h3c1.7 0 2.8-.9 3.8-2.2M13 9c1-1.3 2.2-2 4-2h3M17.5 4.5L20 7l-2.5 2.5M17.5 14.5L20 17l-2.5 2.5"/>',
    "flag": '<path d="M5.5 21V4M5.5 5h12l-3 4 3 4h-12"/>',
    "alert": '<path d="M12 3.8l9 16H3zM12 10v4.5M12 17.3v.1"/>',
    "eye": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    "flip": '<path d="M4 12a8 8 0 0 1 13.7-5.6L20 8.5M20 4v4.5h-4.5M20 12a8 8 0 0 1-13.7 5.6L4 15.5M4 20v-4.5h4.5"/>',
    "undo": '<path d="M9 14L4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3"/>',
    "reset": '<path d="M4.5 12a7.5 7.5 0 1 0 2.4-5.5L4 9.5M4 5v4.5h4.5"/>',
    "prev": '<path d="M14.5 5.5L8 12l6.5 6.5"/>',
    "next": '<path d="M9.5 5.5L16 12l-6.5 6.5"/>',
    "download": '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M4.5 19.5h15"/>',
    "upload": '<path d="M12 15V4M7.5 8.5L12 4l4.5 4.5M4.5 19.5h15"/>',
    "file": '<path d="M7 3.5h7L18.5 8v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1zM14 3.5V8h4.5M9 13h6M9 16.5h6"/>',
    "note": '<path d="M5 4.5h14v11L14.5 20H5zM14.5 20v-4.5H19M8.5 9h7M8.5 12.5h4"/>',
    "equal": '<path d="M5 9h14M5 15h14"/>',
    "gavel": '<path d="M12 3l8 3v6c0 4.5-3.2 8-8 9.5C7.2 20 4 16.5 4 12V6zM8.5 12l2.5 2.5 4.5-4.5"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "play": '<path d="M8 5.5v13L18.5 12z"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "pencil": '<path d="M4 20l1-4.5L16.5 4a2 2 0 0 1 3 3L8 18.5zM14.5 6L18 9.5"/>',
    "trash": '<path d="M5 7h14M10 7V4.5h4V7M7 7l.8 12.5h8.4L17 7M10.5 11v5M13.5 11v5"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.8v.1"/>',
    "save": '<path d="M5 4.5h11L19.5 8v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5.5a1 1 0 0 1 1-1zM8 4.5v5h7v-5M8 19.5v-6h8v6"/>',
    "palette": '<path d="M12 3.5a8.5 8.5 0 1 0 0 17c1.5 0 2-1 1.5-2.2-.6-1.4.2-2.8 1.8-2.8H17a3.5 3.5 0 0 0 3.5-3.5C20.5 7 16.8 3.5 12 3.5z"/>',
    "cpu": '<rect x="6.5" y="6.5" width="11" height="11" rx="2"/><rect x="9.5" y="9.5" width="5" height="5"/><path d="M9.5 3.5v3M14.5 3.5v3M9.5 17.5v3M14.5 17.5v3M3.5 9.5h3M3.5 14.5h3M17.5 9.5h3M17.5 14.5h3"/>',
    "crown": '<path d="M4 18.5h16M4.5 8l4 4L12 5.5 15.5 12l4-4L18 18.5H6z"/>',
    "user": '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c.5-3.8 3.3-6 7-6s6.5 2.2 7 6"/>',
    "more": '<circle cx="5.5" cy="12" r="1.1"/><circle cx="12" cy="12" r="1.1"/><circle cx="18.5" cy="12" r="1.1"/>',
    "expand": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "sidebar": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.2"/><path d="M9.5 4.5v15"/>',
    "book": '<path d="M5 4.5h10a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h10"/>',
    "database": '<ellipse cx="12" cy="6" rx="7.5" ry="2.8"/><path d="M4.5 6v6c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8V6M4.5 12v6c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8v-6"/>',
    "keyboard": '<rect x="2.5" y="6" width="19" height="12" rx="2.2"/><path d="M6 10h.1M9.5 10h.1M13 10h.1M16.5 10h.1M7 14h10"/>',
    "chevron-down": '<path d="M6 9.5l6 6 6-6"/>',
    "chevron-up": '<path d="M6 14.5l6-6 6 6"/>',
}


_ICON_CACHE = {}


def _svg(name: str, color: str) -> bytes:
    body = _ICONS.get(name, _ICONS["info"])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>').encode("utf-8")


def pixmap(name: str, color: str = C.text2, size: int = 20) -> QPixmap:
    key = ("pm", name, color, size)
    if key not in _ICON_CACHE:
        scale = 2
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.GlobalColor.transparent)
        renderer = QSvgRenderer(QByteArray(_svg(name, color)))
        painter = QPainter(pm)
        renderer.render(painter)
        painter.end()
        pm.setDevicePixelRatio(scale)
        _ICON_CACHE[key] = pm
    return _ICON_CACHE[key]


def icon(name: str, color: str = C.text2, size: int = 20, active: str | None = None,
         checked: str | None = None, disabled: str = C.text3) -> QIcon:
    key = ("ic", name, color, size, active, checked, disabled)
    if key not in _ICON_CACHE:
        ic = QIcon()
        ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal)
        ic.addPixmap(pixmap(name, active or color, size), QIcon.Mode.Active)
        ic.addPixmap(pixmap(name, disabled, size), QIcon.Mode.Disabled)
        on = checked or color
        ic.addPixmap(pixmap(name, on, size), QIcon.Mode.Normal, QIcon.State.On)
        _ICON_CACHE[key] = ic
    return _ICON_CACHE[key]


_QSS = """
* { outline: none; }
QWidget { background: transparent; color: @text@; font-family: @sans@; font-size: 14px; }
QMainWindow, QDialog { background: @bg@; }
QToolTip { background: @surface3@; color: @text@; border: 1px solid @line@; border-radius: 6px; padding: 6px 8px; }
QLabel[role="display"] { font-family: @serif@; font-size: 40px; font-weight: 600; color: @text@; }
QLabel[role="h1"] { font-family: @serif@; font-size: 30px; font-weight: 600; color: @text@; }
QLabel[role="h2"] { font-family: @serif@; font-size: 22px; font-weight: 600; color: @text@; }
QLabel[role="h3"] { font-size: 15px; font-weight: 600; color: @text@; }
QLabel[role="lead"] { font-size: 15px; color: @text2@; }
QLabel[role="body"] { font-size: 14px; color: @text@; }
QLabel[role="muted"] { font-size: 13px; color: @text2@; }
QLabel[role="caption"] { font-size: 12px; color: @text3@; }
QLabel[role="field"] { font-size: 12px; font-weight: 600; color: @text2@; }
QLabel[role="num"] { font-family: @serif@; font-size: 34px; font-weight: 600; color: @text@; }
QLabel[role="mono"] { font-family: @mono@; font-size: 14px; }
QFrame#Sidebar { background: @sidebar@; border: 1px solid @line_soft@; border-radius: 14px; }\nQFrame#Card, QFrame#CardRaised, QFrame#CardAccent, QFrame#CardPlain { border-radius: 14px; }
QFrame#Card { background: @surface@; border: 1px solid @line_soft@; }
QFrame#CardRaised { background: @surface2@; border: 1px solid @line@; }
QFrame#CardAccent { background: rgba(201,161,91,0.07); border: 1px solid rgba(201,161,91,0.38); }
QFrame#CardPlain { background: transparent; border: 1px dashed @line@; }
QFrame#Divider { background: @line_soft@; border: none; max-height: 1px; min-height: 1px; }
QLabel[pill="true"] { border-radius: 11px; padding: 2px 10px; font-size: 12px; font-weight: 600; min-height: 18px; max-height: 22px; background: @surface3@; color: @text2@; }
QLabel[pill="true"][tone="brass"] { background: rgba(201,161,91,0.16); color: @brass_hi@; }
QLabel[pill="true"][tone="success"] { background: rgba(88,179,148,0.16); color: @success@; }
QLabel[pill="true"][tone="danger"] { background: rgba(224,112,122,0.16); color: @danger@; }
QLabel[pill="true"][tone="warning"] { background: rgba(224,166,75,0.16); color: @warning@; }
QLabel[pill="true"][tone="info"] { background: rgba(127,174,221,0.16); color: @info@; }
QPushButton { background: @surface2@; color: @text@; border: 1px solid @line@; border-radius: 8px; padding: 0 14px; min-height: 34px; font-weight: 600; }
QPushButton:hover { background: @surface3@; border-color: #35485D; }
QPushButton:pressed { background: #26364A; }
QPushButton:focus { border: 2px solid @brass_hi@; }
QComboBox:focus, QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus { border: 2px solid @brass_hi@; }
QTableWidget:focus, QTableView:focus { border: 2px solid @brass_hi@; }
QPushButton:disabled { color: @text3@; background: @surface@; border-color: @line_soft@; }
QPushButton[kind="primary"], QPushButton#PrimaryButton { background: @brass@; color: @on_brass@; border: 1px solid @brass_hi@; font-weight: 800; }
QPushButton[kind="primary"]:hover, QPushButton#PrimaryButton:hover { background: @brass_hi@; }
QPushButton[kind="ghost"] { background: transparent; border: 1px solid transparent; color: @text2@; }
QPushButton[kind="ghost"]:hover { background: @surface3@; color: @text@; }
QPushButton[kind="danger"] { background: transparent; color: @danger@; border: 1px solid rgba(224,112,122,0.45); }
QPushButton[size="sm"] { min-height: 28px; padding: 0 10px; font-size: 13px; }
QPushButton[nav="true"] { background: transparent; border: 1px solid transparent; border-radius: 9px; text-align: left; padding: 0 12px; min-height: 40px; color: @text2@; font-weight: 500; }
QPushButton[nav="true"]:hover { background: @surface2@; color: @text@; }
QPushButton[nav="true"]:checked { background: rgba(201,161,91,0.13); color: @brass_hi@; font-weight: 700; }
QPushButton[seg="true"] { background: transparent; border: none; border-radius: 6px; padding: 0 14px; min-height: 30px; color: @text2@; font-weight: 600; }
QPushButton[seg="true"]:checked { background: @brass@; color: @on_brass@; }
QFrame#SegBar { background: @well@; border: 1px solid @line_soft@; border-radius: 9px; }
QLineEdit, QPlainTextEdit, QTextEdit, QDoubleSpinBox, QSpinBox, QComboBox { background: @well@; color: @text@; border: 1px solid @line@; border-radius: 8px; padding: 0 12px; min-height: 34px; selection-background-color: @brass_lo@; selection-color: @text@; }
QLineEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus { border-color: @brass@; }
QComboBox QAbstractItemView { background: @surface2@; color: @text@; selection-background-color: @surface3@; selection-color: @brass_hi@; }
QTableWidget, QTableView { background: @surface@; alternate-background-color: #141D27; border: 1px solid @line_soft@; border-radius: 12px; gridline-color: transparent; selection-background-color: rgba(201,161,91,0.14); selection-color: @text@; }
QTableWidget::item, QTableView::item { padding: 0 12px; border-bottom: 1px solid @line_soft@; }
QHeaderView::section { background: @surface@; color: @text2@; border: none; border-bottom: 1px solid @line@; padding: 10px 12px; font-size: 12px; font-weight: 600; }
QListWidget { background: transparent; border: none; padding: 0; }
QListWidget#Sidebar { background: @sidebar@; border: 1px solid @line_soft@; border-radius: 12px; padding: 8px; }
QListWidget#Sidebar::item { color: @text2@; padding: 13px 10px; border-radius: 8px; margin: 3px 0; }
QListWidget#Sidebar::item:selected { background: @surface3@; color: @brass_hi@; border-left: 3px solid @brass@; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: #2C3B4D; border-radius: 4px; min-height: 36px; margin: 0 2px; }
QStatusBar { background: @sidebar@; color: @text3@; border-top: 1px solid @line_soft@; font-size: 12px; }
QProgressBar { background: @surface3@; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; text-align: center; color: transparent; }
QProgressBar::chunk { background: @brass@; border-radius: 4px; }
QLabel#BrandTitle { font-size: 20px; font-weight: 800; letter-spacing: 2px; color: @text@; }
QLabel#Eyebrow { color: @brass_hi@; font-size: 10px; font-weight: 800; letter-spacing: 1.8px; }
QLabel#MatchTitle { color: @text@; font-size: 17px; font-weight: 700; }
QLabel#SectionTitle { font-family: @serif@; color: @text@; font-size: 25px; font-weight: 600; padding: 6px 0; }
QLabel#Muted { color: @text2@; font-size: 13px; }
QLabel#Footnote { color: @text3@; font-size: 10px; letter-spacing: 1px; }
QLabel#SavedBadge { color: @success@; font-size: 10px; font-weight: 800; letter-spacing: 1px; padding: 8px 12px; background: rgba(88,179,148,.12); border: 1px solid rgba(88,179,148,.3); border-radius: 8px; }
QStatusBar::item { border: none; }
"""


def build_qss() -> str:
    values = {
        "bg": C.bg, "sidebar": C.sidebar, "surface": C.surface, "surface2": C.surface2,
        "surface3": C.surface3, "well": C.well, "line": C.line, "line_soft": C.line_soft,
        "text": C.text, "text2": C.text2, "text3": C.text3, "brass": C.brass,
        "brass_hi": C.brass_hi, "brass_lo": C.brass_lo, "on_brass": C.on_brass,
        "success": C.success, "danger": C.danger, "warning": C.warning, "info": C.info,
        "sans": '"IBM Plex Sans","Segoe UI Variable Text","Segoe UI",Arial,sans-serif',
        "serif": '"Spectral","Georgia","Cambria",serif',
        "mono": '"IBM Plex Mono","Cascadia Mono","Consolas",monospace',
    }
    qss = _QSS
    for key, value in values.items():
        qss = qss.replace(f"@{key}@", value)
    return qss


def install_translations(app) -> None:
    try:
        translator = QTranslator(app)
        path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if translator.load(QLocale("it_IT"), "qtbase", "_", path):
            app.installTranslator(translator)
            app._c5r_translator = translator
    except Exception:
        pass


def apply_theme(app) -> None:
    load_fonts()
    app.setStyle("Fusion")
    app.setFont(font(SANS, 14))
    app.setStyleSheet(build_qss())
    install_translations(app)
