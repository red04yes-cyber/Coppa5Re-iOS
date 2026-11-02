"""Widget riutilizzabili C5R: composizione, navigazione, controlli e visualizzazioni."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QEasingCurve, QObject, QPointF, QRect, QRectF, QSize, Qt, QPropertyAnimation, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout, QHeaderView, QLabel,
    QLayout, QMenu, QPushButton, QScrollArea, QSizePolicy, QStatusBar,
    QStyledItemDelegate, QStyle, QStyleOptionViewItem, QTableWidget, QVBoxLayout, QWidget,
)

try:
    from . import c5r_theme as T
    from .c5r_theme import C, MONO, SANS, SERIF, font, icon, mix, with_alpha
except ImportError:
    import c5r_theme as T
    from c5r_theme import C, MONO, SANS, SERIF, font, icon, mix, with_alpha


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def label(text: str = "", role: str = "body", wrap: bool = False, align=None, selectable: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setProperty("role", role)
    lab.setWordWrap(wrap)
    if align is not None:
        lab.setAlignment(align)
    if selectable:
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lab


def pill(text: str = "", tone: str = "neutral") -> QLabel:
    lab = QLabel(text)
    lab.setProperty("pill", True)
    lab.setProperty("tone", tone)
    lab.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lab


def set_pill(lab: QLabel, text: str, tone: str = "neutral") -> None:
    lab.setText(text)
    if lab.property("tone") != tone:
        lab.setProperty("tone", tone)
        repolish(lab)


_KIND_ICON_COLORS = {
    "primary": (C.on_brass, C.on_brass), "danger": (C.danger, C.danger),
    "ghost": (C.text2, C.text), "outline": (C.text2, C.brass_hi),
    "secondary": (C.text2, C.text),
}


def button(text: str = "", kind: str = "secondary", icon_name: str | None = None,
           size: str | None = None, tip: str | None = None, checkable: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("kind", kind)
    if size:
        btn.setProperty("size", size)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setCheckable(checkable)
    if icon_name:
        normal, hover = _KIND_ICON_COLORS.get(kind, _KIND_ICON_COLORS["secondary"])
        px = 16 if size == "sm" else 18
        btn.setIcon(icon(icon_name, normal, px, active=hover))
        btn.setIconSize(QSize(px, px))
    if tip:
        btn.setToolTip(tip)
    return btn


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    return line


def hbox(*widgets, spacing: int = 8, margins=(0, 0, 0, 0)):
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, QLayout):
            lay.addLayout(w)
        else:
            lay.addWidget(w)
    return lay


def field(caption: str, widget: QWidget, hint: str | None = None) -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lay.addWidget(label(caption, "field"))
    lay.addWidget(widget)
    if hint:
        lay.addWidget(label(hint, "caption", wrap=True))
    return box


class FlowLayout(QLayout):
    def __init__(self, parent=None, hspacing: int = 8, vspacing: int = 8):
        super().__init__(parent)
        self._items = []
        self._h, self._v = hspacing, vspacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left()+m.right(), m.top()+m.bottom())

    def _layout(self, rect, test_only):
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = area.x(), area.y(), 0
        for item in self._items:
            if item.isEmpty():
                continue
            hint = item.sizeHint()
            if x + hint.width() > area.right() + 1 and line_h > 0:
                x, y, line_h = area.x(), y + line_h + self._v, 0
            if not test_only:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x += hint.width() + self._h
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + m.bottom()


class CardGlowController(QObject):
    """Glow leggero, animato solo al passaggio del mouse."""
    TARGETS = {"Card", "CardAccent", "CardRaised", "CardPlain"}

    def __init__(self, root: QWidget):
        super().__init__(root)
        self._effects, self._animations = {}, {}
        for frame in root.findChildren(QFrame):
            if frame.objectName() in self.TARGETS:
                frame.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
                frame.installEventFilter(self)

    def eventFilter(self, watched, event):
        if isinstance(watched, QFrame) and watched.objectName() in self.TARGETS:
            if event.type() == QEvent.Type.Enter:
                self._animate(watched, True)
            elif event.type() == QEvent.Type.Leave:
                self._animate(watched, False)
        return super().eventFilter(watched, event)

    def _animate(self, frame: QFrame, active: bool):
        old = self._animations.pop(frame, None)
        if old:
            old.stop()
        effect = self._effects.get(frame)
        if active and effect is None:
            effect = QGraphicsDropShadowEffect(frame)
            effect.setOffset(0, 0)
            color = QColor(C.info if frame.objectName() == "CardPlain" else C.brass_hi)
            color.setAlpha(48)
            effect.setColor(color)
            effect.setBlurRadius(0)
            frame.setGraphicsEffect(effect)
            self._effects[frame] = effect
        if effect is None:
            return
        anim = QPropertyAnimation(effect, b"blurRadius", self)
        anim.setDuration(165 if active else 125)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(effect.blurRadius())
        anim.setEndValue(15.0 if active else 0.0)
        if not active:
            anim.finished.connect(lambda f=frame, e=effect: self._clear(f, e))
        self._animations[frame] = anim
        anim.start()

    def _clear(self, frame: QFrame, effect: QGraphicsDropShadowEffect):
        if self._effects.get(frame) is not effect:
            return
        self._effects.pop(frame, None)
        self._animations.pop(frame, None)
        try:
            if frame.graphicsEffect() is effect:
                frame.setGraphicsEffect(None)
        except RuntimeError:
            pass


class Card(QFrame):
    def __init__(self, title: str | None = None, subtitle: str | None = None,
                 variant: str = "Card", padding: int = 20, spacing: int = 12,
                 action: QWidget | None = None):
        super().__init__()
        self.setObjectName(variant)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(padding, padding-2 if title else padding, padding, padding)
        outer.setSpacing(spacing)
        if title or action:
            head, text = QHBoxLayout(), QVBoxLayout()
            text.setSpacing(2)
            if title:
                self.title_label = label(title, "h3")
                text.addWidget(self.title_label)
            if subtitle:
                text.addWidget(label(subtitle, "muted", wrap=True))
            head.addLayout(text, 1)
            if action:
                head.addWidget(action, 0, Qt.AlignmentFlag.AlignTop)
            outer.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(spacing)
        self.body.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self.body, 1)


class PageScroll(QScrollArea):
    def __init__(self, title: str, subtitle: str = "", actions: list | None = None, max_width: int = 1280):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        self.setWidget(holder)
        outer = QHBoxLayout(holder)
        outer.setContentsMargins(0, 0, 0, 0)
        column = QWidget()
        column.setMaximumWidth(max_width)
        column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        outer.addWidget(column, 1)
        outer.addStretch(0)
        self.content = QVBoxLayout(column)
        self.content.setContentsMargins(30, 26, 30, 30)
        self.content.setSpacing(20)
        head, text = QHBoxLayout(), QVBoxLayout()
        text.setSpacing(4)
        self.title_label = label(title, "h1")
        text.addWidget(self.title_label)
        if subtitle:
            text.addWidget(label(subtitle, "lead", wrap=True))
        head.addLayout(text, 1)
        if actions:
            row = QHBoxLayout()
            for action in actions:
                row.addWidget(action)
            head.addLayout(row)
        self.content.addLayout(head)

    def add(self, widget_or_layout, stretch: int = 0):
        if isinstance(widget_or_layout, QLayout):
            self.content.addLayout(widget_or_layout, stretch)
        else:
            self.content.addWidget(widget_or_layout, stretch)


class StatTile(QFrame):
    def __init__(self, caption: str, icon_name: str | None = None):
        super().__init__()
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(2)
        top = QHBoxLayout()
        top.addWidget(label(caption, "field"), 1)
        if icon_name:
            ic = QLabel()
            ic.setPixmap(T.pixmap(icon_name, C.text3, 18))
            top.addWidget(ic)
        lay.addLayout(top)
        self.value = label("—", "num")
        self._counter_timer = QTimer(self)
        self._counter_timer.setInterval(18)
        self._counter_timer.timeout.connect(self._advance_counter)
        self._counter_start = self._counter_target = self._counter_step = 0
        self._counter_frames = 12
        self._counter_final = ""
        lay.addWidget(self.value)
        self.hint = label("", "muted", wrap=True)
        lay.addWidget(self.hint)

    def set(self, value: str, hint: str = "") -> None:
        text, old = str(value), self.value.text()
        if text != old and old.lstrip("-").isdigit() and text.lstrip("-").isdigit():
            self._counter_timer.stop()
            self._counter_start, self._counter_target = int(old), int(text)
            self._counter_final, self._counter_step = text, 0
            if self._counter_start != self._counter_target:
                self._counter_timer.start()
            else:
                self.value.setText(text)
        else:
            self._counter_timer.stop()
            self.value.setText(text)
        self.hint.setText(hint)
        self.hint.setVisible(bool(hint))

    def _advance_counter(self):
        self._counter_step += 1
        x = min(1.0, self._counter_step / self._counter_frames)
        eased = 1.0 - (1.0 - x) ** 3
        n = round(self._counter_start + (self._counter_target - self._counter_start) * eased)
        self.value.setText(str(n))
        if self._counter_step >= self._counter_frames:
            self.value.setText(self._counter_final)
            self._counter_timer.stop()


class EmptyState(QFrame):
    def __init__(self, icon_name: str, title: str, text: str = ""):
        super().__init__()
        self.setObjectName("CardPlain")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 28, 24, 28)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic = QLabel()
        ic.setPixmap(T.pixmap(icon_name, C.text3, 32))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ic)
        lay.addWidget(label(title, "h3", align=Qt.AlignmentFlag.AlignCenter))
        if text:
            lay.addWidget(label(text, "muted", wrap=True, align=Qt.AlignmentFlag.AlignCenter))


class SegmentedControl(QFrame):
    changed = Signal(object)

    def __init__(self, options: list, value=None, size: str | None = None):
        super().__init__()
        self.setObjectName("SegBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self._buttons, self._value = {}, value
        for val, text in options:
            btn = QPushButton(text)
            btn.setProperty("seg", True)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, v=val: self._clicked(v))
            lay.addWidget(btn)
            self._buttons[val] = btn
        self._apply()

    def _clicked(self, value):
        if value != self._value:
            self._value = value
            self._apply()
            self.changed.emit(value)

    def _apply(self):
        for val, btn in self._buttons.items():
            btn.blockSignals(True)
            btn.setChecked(val == self._value)
            btn.blockSignals(False)

    def set_value(self, value):
        self._value = value
        self._apply()

    def value(self):
        return self._value


RESULT_LABELS = {"1-0": "1–0", "1/2-1/2": "½–½", "0-1": "0–1"}


class ResultPicker(QFrame):
    valueChanged = Signal(object)

    def __init__(self, compact: bool = False):
        super().__init__()
        self._value = None
        self.setObjectName("SegBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self._buttons = {}
        for val, text in RESULT_LABELS.items():
            btn = QPushButton(text)
            btn.setProperty("seg", True)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip({"1-0": "Vince il Bianco", "1/2-1/2": "Patta", "0-1": "Vince il Nero"}[val])
            btn.clicked.connect(lambda _=False, v=val: self._emit(v))
            lay.addWidget(btn)
            self._buttons[val] = btn
        self.more = QPushButton()
        self.more.setProperty("seg", True)
        self.more.setIcon(icon("more", C.text2, 16))
        self.more.setToolTip("Altre opzioni: in corso o partita annullata")
        menu = QMenu(self.more)
        menu.addAction("In corso (azzera il risultato)").triggered.connect(lambda: self._emit(None))
        menu.addAction("Annullata / esclusa").triggered.connect(lambda: self._emit("VOID"))
        self.more.setMenu(menu)
        lay.addWidget(self.more)
        self._apply()

    def _emit(self, value):
        if value != self._value:
            self.valueChanged.emit(value)
        self._apply()

    def _apply(self):
        for val, btn in self._buttons.items():
            btn.blockSignals(True)
            btn.setChecked(val == self._value)
            btn.blockSignals(False)
        self.more.setText("Annullata" if self._value == "VOID" else "")

    def set_value(self, value):
        self._value = value
        self._apply()

    def value(self):
        return self._value


class Avatar(QWidget):
    def __init__(self, initials: str = "?", tint: str = C.brass, size: int = 36):
        super().__init__()
        self._initials, self._tint = initials, tint
        self._pixmap = None
        self.setFixedSize(size, size)

    def set_player(self, initials: str, tint: str):
        self._initials, self._tint = initials, tint
        self.update()

    def set_pixmap(self, pixmap: QPixmap | None):
        self._pixmap = pixmap if pixmap is not None and not pixmap.isNull() else None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._pixmap is not None:
            clip = QPainterPath()
            clip.addEllipse(r)
            p.setClipPath(clip)
            p.drawPixmap(self.rect(), self._pixmap)
            p.setClipping(False)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(with_alpha(self._tint, .75), 1.4))
            p.drawEllipse(r)
            return
        p.setBrush(with_alpha(self._tint, .20))
        p.setPen(QPen(with_alpha(self._tint, .65), 1.4))
        p.drawEllipse(r)
        p.setPen(mix(self._tint, "#FFFFFF", .35))
        p.setFont(font(SERIF, max(12, int(self.width()*.44)), 600))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self._initials)


class ClockChip(QWidget):
    def __init__(self, big: bool = False):
        super().__init__()
        self._text, self._active, self._low = "00:00", False, False
        self._big = big
        self.setFixedHeight(46 if big else 36)
        self.setMinimumWidth(116 if big else 92)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_time(self, seconds, active: bool = False):
        text = T.fmt_clock(seconds)
        low = int(seconds) <= 30 and active
        if (text, active, low) != (self._text, self._active, self._low):
            self._text, self._active, self._low = text, active, low
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        if self._low:
            bg, border, fg = with_alpha(C.danger, .20), C.danger, QColor("#FFD7DA")
        elif self._active:
            bg, border, fg = with_alpha(C.brass, .20), C.brass, QColor(C.text)
        else:
            bg, border, fg = QColor(C.well), QColor(C.line_soft), QColor(C.text2)
        p.setBrush(bg)
        p.setPen(QPen(QColor(border), 1.2))
        p.drawRoundedRect(r, 8, 8)
        p.setPen(fg)
        p.setFont(font(MONO, 24 if self._big else 19, 600))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self._text)


class ProbBar(QWidget):
    def __init__(self, color: str = C.brass, height: int = 12):
        super().__init__()
        self._value, self._text, self._color = 0.0, "", color
        self.setFixedHeight(height+4)
        self.setMinimumWidth(120)

    def set(self, value: float, text: str = "", color: str | None = None):
        self._value = max(0.0, min(1.0, value))
        self._text = text
        if color:
            self._color = color
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()-4
        fm = QFontMetrics(font(SANS, 13, 600))
        label_w = fm.horizontalAdvance("100,0%")+10
        track = QRectF(0, 2, max(10, self.width()-label_w), h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.surface3))
        p.drawRoundedRect(track, h/2, h/2)
        if self._value > 0:
            fill = QRectF(track.x(), track.y(), max(h, track.width()*self._value), h)
            p.setBrush(QColor(self._color))
            p.drawRoundedRect(fill, h/2, h/2)
        p.setPen(QColor(C.text))
        p.setFont(font(SANS, 13, 600))
        p.drawText(QRectF(track.right()+8, 0, label_w, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)


class PillDelegate(QStyledItemDelegate):
    TONES = {
        "success": (C.success, .16), "danger": (C.danger, .16), "warning": (C.warning, .16),
        "info": (C.info, .16), "brass": (C.brass_hi, .16), "neutral": (C.text2, .12),
    }

    def paint(self, painter, option, index):
        tone, text = index.data(Qt.ItemDataRole.UserRole+1), index.data(Qt.ItemDataRole.DisplayRole)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        if opt.widget:
            opt.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        if not tone or not text:
            if text:
                painter.setPen(QColor(C.text))
                painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, str(text))
            return
        color, alpha = self.TONES.get(tone, self.TONES["neutral"])
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = font(SANS, 13, 600)
        painter.setFont(f)
        w = QFontMetrics(f).horizontalAdvance(str(text))+22
        r = QRectF(option.rect.center().x()-w/2, option.rect.center().y()-11, w, 22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(with_alpha(color, alpha))
        painter.drawRoundedRect(r, 11, 11)
        painter.setPen(QColor(color))
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, str(text))
        painter.restore()


def style_table(table: QTableWidget, row_height: int = 48, selectable: bool = True):
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setMinimumSectionSize(48)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setShowGrid(False)
    table.setAlternatingRowColors(False)
    table.setFrameShape(QFrame.Shape.NoFrame)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.TextElideMode.ElideRight)
    if selectable:
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    else:
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus if not selectable else Qt.FocusPolicy.StrongFocus)


def table_card(table: QTableWidget) -> QFrame:
    frame = QFrame()
    frame.setObjectName("Card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(0, 0, 0, 0)
    table.setStyleSheet("QTableWidget{background:transparent;border:none;border-radius:14px;}")
    lay.addWidget(table)
    return frame


class EvalBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(22)
        self.setMinimumHeight(120)
        self._white, self._text, self._enabled, self._flipped = .5, "", False, False

    def set_eval(self, white_fraction: float, text: str):
        self._white = max(0.0, min(1.0, white_fraction))
        self._text, self._enabled = text, True
        self.setToolTip(text)
        self.update()

    def set_off(self, tip: str = ""):
        self._enabled = False
        self._text = ""
        self.setToolTip(tip)
        self.update()

    def set_flipped(self, flipped: bool):
        self._flipped = flipped
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 0, -2, 0)
        clip = QPainterPath()
        clip.addRoundedRect(r, 6, 6)
        p.setClipPath(clip)
        p.fillRect(r, QColor("#1E1A17"))
        if self._enabled:
            h = r.height()*self._white
            white_rect = QRectF(r.x(), r.y(), r.width(), h) if self._flipped else QRectF(r.x(), r.bottom()-h, r.width(), h)
            p.fillRect(white_rect, QColor("#F2ECDD"))
            p.setPen(QPen(QColor(C.brass), 1.4))
            p.drawLine(QPointF(r.x(), r.center().y()), QPointF(r.right(), r.center().y()))
        else:
            p.fillRect(r, QColor(C.surface3))
        p.setClipping(False)
        p.setPen(QPen(QColor(C.line), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 6, 6)


class LineChart(QWidget):
    def __init__(self):
        super().__init__()
        self.series, self.x_labels = [], []
        self.setMinimumHeight(220)

    def set_data(self, x_labels: list, series: list):
        self.x_labels, self.series = x_labels, series
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.series or not self.x_labels:
            return
        name_w = 96
        left, right, top, bottom = 34, name_w+12, 12, 30
        plot = QRectF(left, top, self.width()-left-right, self.height()-top-bottom)
        top_value = max(1.0, max((max(vals) if vals else 0) for _, _, vals in self.series))
        top_value = float(int(top_value+.999))
        steps = int(top_value*2)
        p.setFont(font(SANS, 11, 400))
        for i in range(steps+1):
            v = i/2
            y = plot.bottom()-plot.height()*(v/top_value)
            p.setPen(QPen(QColor(C.line_soft if i%2 else C.line), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            if i%2 == 0:
                p.setPen(QColor(C.text3))
                p.drawText(QRectF(0, y-8, left-8, 16), Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter, f"{v:g}")
        n = len(self.x_labels)
        xs = [plot.left()+plot.width()*i/max(1,n-1) for i in range(n)]
        p.setPen(QColor(C.text2))
        for x, text in zip(xs, self.x_labels):
            p.drawText(QRectF(x-30, plot.bottom()+8, 60, 16), Qt.AlignmentFlag.AlignCenter, text)
        ends = []
        for name, color, values in self.series:
            pts = [QPointF(xs[i], plot.bottom()-plot.height()*(v/top_value)) for i,v in enumerate(values)]
            if len(pts)>1:
                path = QPainterPath(pts[0])
                for pt in pts[1:]:
                    path.lineTo(pt)
                p.setPen(QPen(QColor(color), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
            p.setBrush(QColor(C.surface))
            p.setPen(QPen(QColor(color), 2))
            for pt in pts:
                p.drawEllipse(pt, 3.6, 3.6)
            if pts:
                ends.append([pts[-1].y(), name, color])
        ends.sort(key=lambda e:e[0])
        for i in range(1,len(ends)):
            if ends[i][0]-ends[i-1][0]<16:
                ends[i][0]=ends[i-1][0]+16
        p.setFont(font(SANS, 12, 600))
        for y,name,color in ends:
            p.setPen(QColor(color))
            p.drawText(QRectF(plot.right()+12,y-9,name_w,18), Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter, name)


_TONE_ICONS = {"success": ("check", C.success), "danger": ("alert", C.danger),
               "warning": ("alert", C.warning), "info": ("info", C.info)}


class ToastHost(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(24,24,24,24)
        self._lay.setSpacing(8)
        self._lay.addStretch(1)
        self._toasts = []

    def reposition(self):
        parent = self.parentWidget()
        if parent:
            self.setGeometry(parent.rect())
            self.raise_()

    def show_toast(self, text: str, tone: str = "info", timeout: int = 3800):
        for existing in self._toasts:
            if existing.property("toast_text") == text:
                existing._timer.start(timeout)
                return
        while len(self._toasts)>=3:
            self._dismiss(self._toasts[0], animate=False)
        toast = QFrame()
        toast.setObjectName("Toast")
        toast.setProperty("toast_tone", tone)
        toast.setProperty("toast_text", text)
        toast.setMaximumWidth(460)
        row = QHBoxLayout(toast)
        row.setContentsMargins(14,11,16,11)
        row.setSpacing(10)
        name,color = _TONE_ICONS.get(tone, _TONE_ICONS["info"])
        ic = QLabel()
        ic.setPixmap(T.pixmap(name,color,18))
        row.addWidget(ic,0,Qt.AlignmentFlag.AlignTop)
        msg = label(text,"body",wrap=True)
        row.addWidget(msg,1)
        effect = QGraphicsOpacityEffect(toast)
        effect.setOpacity(0)
        toast.setGraphicsEffect(effect)
        self._lay.addWidget(toast,0,Qt.AlignmentFlag.AlignRight)
        self._toasts.append(toast)
        fade = QPropertyAnimation(effect,b"opacity",toast)
        fade.setDuration(160)
        fade.setStartValue(0)
        fade.setEndValue(1)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade.start()
        toast._fade_in = fade
        timer = QTimer(toast)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda t=toast:self._dismiss(t))
        timer.start(timeout)
        toast._timer = timer
        self.raise_()

    def _dismiss(self, toast: QFrame, animate: bool = True):
        if toast not in self._toasts:
            return
        self._toasts.remove(toast)
        toast._timer.stop()
        effect = toast.graphicsEffect()
        if animate and effect is not None:
            fade = QPropertyAnimation(effect,b"opacity",toast)
            fade.setDuration(200)
            fade.setStartValue(effect.opacity())
            fade.setEndValue(0)
            fade.finished.connect(toast.deleteLater)
            fade.start()
            toast._fade_out = fade
        else:
            toast.hide()
            toast.deleteLater()


class ToastStatusBar(QStatusBar):
    _DANGER = ("illegale","non registrata","non registrato","non valida","non valido","non riuscit","errore")
    _WARN = ("non disponibile","torna all","attendi","rimuovi il risultato","non è cambiato")
    _OK = ("salvat","completat","esportat","registrat","aggiornat","avviato","ripristinat","terminata")

    def __init__(self, host: ToastHost | None = None):
        super().__init__()
        self.host = host
        self.setSizeGripEnabled(False)

    def showMessage(self, text, timeout=0):
        if not text:
            return
        low = text.lower()
        tone = "danger" if any(k in low for k in self._DANGER) else (
            "warning" if any(k in low for k in self._WARN) else (
            "success" if any(k in low for k in self._OK) else "info"))
        super().showMessage(text, timeout)
        if self.host:
            duration = max(2600, int(timeout) or 3800)
            if tone == "danger":
                duration = max(duration, 5200)
            elif tone == "warning":
                duration = max(duration, 4200)
            self.host.show_toast(text, tone, duration)


class SideNav(QFrame):
    currentChanged = Signal(str)
    EXPANDED, COLLAPSED = 248, 76

    def __init__(self, brand: QWidget, title: str, tagline: str):
        super().__init__()
        self.setObjectName("Sidebar")
        self._buttons, self._texts, self._group_labels = {}, {}, []
        self._collapsed, self._current = False, None
        self.setFixedWidth(self.EXPANDED)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14,18,14,14)
        lay.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(brand,0,Qt.AlignmentFlag.AlignVCenter)
        self.brand_text = QWidget()
        bt = QVBoxLayout(self.brand_text)
        bt.setContentsMargins(0,0,0,0)
        bt.setSpacing(0)
        bt.addWidget(label(title,"h2"))
        bt.addWidget(label(tagline,"caption"))
        head.addWidget(self.brand_text,1)
        lay.addLayout(head)
        lay.addSpacing(18)
        self._lay = lay

    def add_group(self, title: str):
        lab = label(title,"caption")
        lab.setContentsMargins(12,12,0,4)
        self._lay.addWidget(lab)
        self._group_labels.append(lab)

    def add_item(self, key: str, text: str, icon_name: str, tip: str = ""):
        btn = QPushButton(text)
        btn.setProperty("nav",True)
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIcon(icon(icon_name,C.text2,20,active=C.text,checked=C.brass_hi))
        btn.setIconSize(QSize(20,20))
        btn.setToolTip(tip or text)
        btn.clicked.connect(lambda _=False,k=key:self.set_current(k,emit=True))
        self._lay.addWidget(btn)
        self._buttons[key], self._texts[key] = btn,text
        return btn

    def finish(self, footer: QWidget | None = None):
        self._lay.addStretch(1)
        if footer:
            self._lay.addWidget(footer)
        self.toggle_btn = button("Comprimi","ghost","sidebar",tip="Comprimi o espandi il menu")
        self.toggle_btn.setProperty("nav",True)
        self.toggle_btn.clicked.connect(lambda:self.set_collapsed(not self._collapsed))
        self._lay.addWidget(self.toggle_btn)

    def set_current(self,key: str,emit: bool=False):
        if key not in self._buttons:
            return
        self._current = key
        for k,btn in self._buttons.items():
            btn.blockSignals(True)
            btn.setChecked(k==key)
            btn.blockSignals(False)
        if emit:
            self.currentChanged.emit(key)

    def current(self):
        return self._current

    def set_collapsed(self,collapsed: bool):
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.setFixedWidth(self.COLLAPSED if collapsed else self.EXPANDED)
        self.brand_text.setVisible(not collapsed)
        for lab in self._group_labels:
            lab.setVisible(not collapsed)
        for key,btn in self._buttons.items():
            btn.setText("" if collapsed else self._texts[key])
        self.toggle_btn.setText("" if collapsed else "Comprimi")
        for btn in self._buttons.values():
            btn.setStyleSheet("padding:0;" if collapsed else "")




# --------------------------------------------------------------------------
# Componenti premium per schede giocatore e abbinamenti
# --------------------------------------------------------------------------
class Swatch(QWidget):
    """Indicatore compatto del colore dei pezzi assegnato al giocatore."""

    def __init__(self, white: bool = True, size: int = 12):
        super().__init__()
        self._white = white
        self.setFixedSize(size, size)

    def set_white(self, white: bool) -> None:
        self._white = white
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#F4EEDF") if self._white else QColor("#15120F"))
        painter.setPen(QPen(QColor("#8C8372") if self._white else QColor("#6C6558"), 1.2))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 3, 3)


class PlayerStrip(QFrame):
    """Scheda giocatore con avatar, colore, rating, turno e orologio."""

    def __init__(self, big: bool = False):
        super().__init__()
        self.setObjectName("RowHover")
        self._big = big
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8) if not big else layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)
        self.avatar = Avatar("?", C.brass, 44 if big else 32)
        layout.addWidget(self.avatar)

        text = QVBoxLayout()
        text.setSpacing(1)
        name_row = QHBoxLayout()
        name_row.setSpacing(7)
        self.swatch = Swatch(True, 14 if big else 12)
        name_row.addWidget(self.swatch)
        self.name = label("Giocatore", "h2" if big else "h3")
        name_row.addWidget(self.name, 1)
        self.material = label("", "caption")
        name_row.addWidget(self.material)
        text.addLayout(name_row)
        self.sub = label("", "muted" if big else "caption")
        text.addWidget(self.sub)
        layout.addLayout(text, 1)

        self.turn = pill("Al tratto", "brass")
        layout.addWidget(self.turn)
        self.clock = ClockChip(big)
        layout.addWidget(self.clock)
        self.turn.hide()

    def set_photo(self, pixmap: QPixmap | None) -> None:
        self.avatar.set_pixmap(pixmap)

    def set_data(
        self, name: str, handle: str, tint: str, white: bool, seconds,
        running: bool, to_move: bool, material: int = 0, points: str = "",
        show_clock: bool = True,
    ) -> None:
        self.avatar.set_player(name[:1].upper(), tint)
        self.name.setText(name)
        self.swatch.set_white(white)
        self.material.setText(f"+{material}" if material > 0 else "")
        side = "Bianco" if white else "Nero"
        self.sub.setText(" · ".join(part for part in (handle, side, points) if part))
        self.turn.setVisible(to_move)
        self.clock.setVisible(show_clock)
        if show_clock:
            self.clock.set_time(seconds, bool(running and to_move))


class FormStrip(QWidget):
    """Ultimi risultati: V vittoria, X pareggio, P sconfitta."""

    COLORS = {"V": C.success, "X": C.text3, "P": C.danger}

    def __init__(self):
        super().__init__()
        self._items: list[str] = []
        self.setFixedHeight(22)
        self.setMinimumWidth(96)

    def set_items(self, items: list) -> None:
        self._items = [str(item) for item in list(items)[-4:]]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(font(SANS, 11, 700))
        x = 0.0
        for item in self._items:
            color = QColor(self.COLORS.get(item, C.text3))
            rect = QRectF(x, 1, 20, 20)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(with_alpha(color, 0.18))
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(color)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, item)
            x += 24
        if not self._items:
            painter.setPen(QColor(C.text3))
            painter.setFont(font(SANS, 12, 400))
            painter.drawText(
                QRectF(0, 0, 90, 22),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                "—",
            )


class MatchLine(QWidget):
    """Abbinamento con indicatori del colore Bianco/Nero."""

    def __init__(self, big: bool = False):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        role = "h2" if big else "h3"
        self.sw1, self.sw2 = Swatch(True), Swatch(False)
        self.n1, self.n2 = label("", role), label("", role)
        self.vs = label("vs", "caption")
        for widget in (self.sw1, self.n1, self.vs, self.sw2, self.n2):
            layout.addWidget(widget)
        layout.addStretch(1)

    def set_players(self, white: str, black: str) -> None:
        self.n1.setText(white)
        self.n2.setText(black)
