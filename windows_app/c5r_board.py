"""Scacchiera vettoriale C5R con mosse legali e interazione mouse/touch."""
from __future__ import annotations

import chess
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPainterPath, QPen, QRadialGradient, QTransform
from PySide6.QtWidgets import QSizePolicy, QWidget

import c5r_theme as T
from c5r_theme import C, SANS, SYMBOLS, font, with_alpha

BOARD_THEMES = [
    {"name":"Noce","light":"#E8DABD","dark":"#A67B58","hi":(240,200,90)},
    {"name":"Ardesia","light":"#D7DDE4","dark":"#6C8196","hi":(240,205,100)},
    {"name":"Foresta","light":"#E4E7D0","dark":"#6F8E6A","hi":(238,206,92)},
    {"name":"Notte","light":"#9DA8B7","dark":"#4B5769","hi":(226,186,84)},
]
_GLYPHS = {chess.KING:"\u265A",chess.QUEEN:"\u265B",chess.ROOK:"\u265C",
           chess.BISHOP:"\u265D",chess.KNIGHT:"\u265E",chess.PAWN:"\u265F"}
_REF_PX = 100
_PATHS, _REF_HEIGHT = {}, [0.0]


def _symbol_font():
    families = QFontDatabase.families()
    family = SYMBOLS if SYMBOLS in families else "Segoe UI Symbol"
    f = QFont(family)
    f.setPixelSize(_REF_PX)
    return f


def _piece_path(piece_type):
    if piece_type not in _PATHS:
        raw = QPainterPath()
        raw.addText(0,0,_symbol_font(),_GLYPHS[piece_type])
        rect = raw.boundingRect()
        t = QTransform()
        t.translate(-(rect.x()+rect.width()/2),-rect.bottom())
        _PATHS[piece_type] = t.map(raw)
        _REF_HEIGHT[0] = max(_REF_HEIGHT[0],rect.height())
    return _PATHS[piece_type]


def paint_piece(p,piece_type,color,cx,ground,cell,opacity=1.0,grow=1.0):
    path = _piece_path(piece_type)
    for pt in _GLYPHS:
        _piece_path(pt)
    scale = cell*.80/_REF_HEIGHT[0]*grow
    t = QTransform()
    t.translate(cx,ground)
    t.scale(scale,scale)
    shape = t.map(path)
    p.save()
    p.setOpacity(opacity)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0,0,0,70))
    shadow = QTransform()
    shadow.translate(0,cell*.028)
    p.drawPath(shadow.map(shape))
    if color == chess.WHITE:
        fill,edge,halo = QColor("#F7F2E4"),QColor("#2A2016"),QColor(20,14,8,70)
    else:
        fill,edge,halo = QColor("#28231F"),QColor("#0A0806"),QColor(250,240,220,85)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(halo,cell*.055,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    p.drawPath(shape)
    p.setBrush(fill)
    p.setPen(QPen(edge,cell*.030,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    p.drawPath(shape)
    p.restore()


class BoardWidget(QWidget):
    moveRequested = Signal(str)
    orientationChanged = Signal(bool)

    def __init__(self,interactive=True):
        super().__init__()
        self.interactive=interactive
        self.board=chess.Board()
        self.selected=None
        self.targets=set()
        self.captures=set()
        self.locked=False
        self.flipped=False
        self.theme_index=0
        self.drag_source=None
        self.drag_pos=QPointF()
        self.press_pos=QPointF()
        self.dragging=False
        self.hover=None
        self.promotion=None
        self.show_coords=True
        self.move_flash=0.0
        self.flash_timer=QTimer(self)
        self.flash_timer.setInterval(40)
        self.flash_timer.timeout.connect(self.fade_move_flash)
        self.setMinimumSize(280,280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def sizeHint(self):
        return QSize(520,520)

    def set_position(self,board,locked=False):
        old_len=len(self.board.move_stack)
        old_last=self.board.peek() if self.board.move_stack else None
        self.board=board.copy(stack=True)
        self.locked=locked
        new_last=self.board.peek() if self.board.move_stack else None
        if len(self.board.move_stack)>old_len or (new_last and new_last!=old_last):
            self.move_flash=1.0
            self.flash_timer.start()
        self._clear_selection()
        self.promotion=None
        self.update()

    def set_theme(self,index):
        self.theme_index=index%len(BOARD_THEMES)
        self.update()

    def cycle_theme(self):
        self.set_theme(self.theme_index+1)

    def toggle_orientation(self):
        self.flipped=not self.flipped
        self._clear_selection()
        self.update()
        self.orientationChanged.emit(self.flipped)

    def set_orientation(self,flipped):
        if flipped!=self.flipped:
            self.toggle_orientation()

    def fade_move_flash(self):
        self.move_flash=max(0.0,self.move_flash-.09)
        self.update()
        if self.move_flash<=0:
            self.flash_timer.stop()

    def _clear_selection(self):
        self.selected=None
        self.targets=set()
        self.captures=set()
        self.drag_source=None
        self.dragging=False

    def board_geometry(self):
        side=max(8.0,float(min(self.width(),self.height())))
        return (self.width()-side)/2,(self.height()-side)/2,side/8,side

    def _square_rect(self,square,x0,y0,c):
        file,rank=chess.square_file(square),chess.square_rank(square)
        col=7-file if self.flipped else file
        row=rank if self.flipped else 7-rank
        return QRectF(x0+col*c,y0+row*c,c,c)

    def _square_at(self,pos):
        x0,y0,c,side=self.board_geometry()
        col=int((pos.x()-x0)//c)
        row=int((pos.y()-y0)//c)
        if not (0<=col<8 and 0<=row<8):
            return None
        file=7-col if self.flipped else col
        rank=row if self.flipped else 7-row
        return chess.square(file,rank)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        x0,y0,c,side=self.board_geometry()
        theme=BOARD_THEMES[self.theme_index%len(BOARD_THEMES)]
        light,dark=QColor(theme["light"]),QColor(theme["dark"])
        hi=QColor(*theme["hi"])
        radius=max(6.0,c*.14)
        clip=QPainterPath()
        clip.addRoundedRect(QRectF(x0,y0,side,side),radius,radius)
        p.save()
        p.setClipPath(clip)
        last=self.board.peek() if self.board.move_stack else None
        check_sq=self.board.king(self.board.turn) if self.board.is_check() else None
        for sq in chess.SQUARES:
            r=self._square_rect(sq,x0,y0,c)
            is_light=(chess.square_file(sq)+chess.square_rank(sq))%2==1
            p.fillRect(r,light if is_light else dark)
            if last and sq in (last.from_square,last.to_square):
                tint=QColor(hi)
                tint.setAlphaF(min(.9,.42+.30*self.move_flash))
                p.fillRect(r,tint)
            if sq==self.selected:
                tint=QColor(hi)
                tint.setAlphaF(.78)
                p.fillRect(r,tint)
            if sq==check_sq:
                g=QRadialGradient(r.center(),c*.72)
                g.setColorAt(0,QColor(C.check))
                g.setColorAt(.55,with_alpha(C.check,.55))
                g.setColorAt(1,with_alpha(C.check,0))
                p.fillRect(r,g)
            if self.show_coords:
                self._paint_coordinate(p,sq,r,c,light,dark)
        for sq in chess.SQUARES:
            piece=self.board.piece_at(sq)
            if not piece:
                continue
            if self.dragging and sq==self.drag_source:
                paint_piece(p,piece.piece_type,piece.color,*self._piece_anchor(sq,x0,y0,c),c,opacity=.28)
            else:
                paint_piece(p,piece.piece_type,piece.color,*self._piece_anchor(sq,x0,y0,c),c)
        for sq in self.targets:
            r=self._square_rect(sq,x0,y0,c)
            if sq in self.captures:
                p.setPen(QPen(QColor(20,14,8,105),c*.075))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(r.adjusted(c*.07,c*.07,-c*.07,-c*.07))
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(20,14,8,88))
                p.drawEllipse(r.center(),c*.16,c*.16)
            if sq==self.hover and not self.dragging:
                p.setPen(QPen(QColor(20,14,8,130),max(2.0,c*.045)))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(r.adjusted(1,1,-1,-1))
        if self.dragging and self.drag_source is not None:
            if self.hover is not None and self.hover in self.targets:
                p.setPen(QPen(QColor(20,14,8,140),max(2.0,c*.05)))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(self._square_rect(self.hover,x0,y0,c).adjusted(1,1,-1,-1))
            piece=self.board.piece_at(self.drag_source)
            if piece:
                paint_piece(p,piece.piece_type,piece.color,self.drag_pos.x(),self.drag_pos.y()+c*.38,c,grow=1.14)
        if self.promotion:
            self._paint_promotion(p,x0,y0,c,side)
        p.restore()
        p.setPen(QPen(with_alpha("#000000",.35),1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(x0+.5,y0+.5,side-1,side-1),radius,radius)

    def _piece_anchor(self,sq,x0,y0,c):
        r=self._square_rect(sq,x0,y0,c)
        return r.center().x(),r.top()+c*.90

    def _paint_coordinate(self,p,sq,r,c,light,dark):
        file,rank=chess.square_file(sq),chess.square_rank(sq)
        is_light=(file+rank)%2==1
        color=QColor(dark if is_light else light)
        color.setAlphaF(.95)
        bottom_rank=7 if self.flipped else 0
        left_file=7 if self.flipped else 0
        p.setFont(font(SANS,max(9,int(c*.17)),600))
        p.setPen(color)
        pad=c*.06
        if rank==bottom_rank:
            p.drawText(QRectF(r.left(),r.bottom()-c*.26,c-pad,c*.24),
                       Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignBottom,chess.FILE_NAMES[file])
        if file==left_file:
            p.drawText(QRectF(r.left()+pad,r.top()+pad*.6,c*.4,c*.24),
                       Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop,str(rank+1))

    _PROMO_ORDER=(chess.QUEEN,chess.ROOK,chess.BISHOP,chess.KNIGHT)

    def _promotion_rects(self,x0,y0,c):
        from_sq,to_sq,color=self.promotion
        base=self._square_rect(to_sq,x0,y0,c)
        direction=1 if base.top()<y0+c*4 else -1
        return [(piece_type,QRectF(base.left(),base.top()+direction*i*c,c,c))
                for i,piece_type in enumerate(self._PROMO_ORDER)]

    def _paint_promotion(self,p,x0,y0,c,side):
        p.fillRect(QRectF(x0,y0,side,side),QColor(10,8,6,150))
        color=self.promotion[2]
        for piece_type,r in self._promotion_rects(x0,y0,c):
            hovered=r.contains(self.drag_pos)
            p.setPen(QPen(QColor(C.brass),1.5))
            p.setBrush(QColor("#2A3441") if not hovered else QColor("#3A4A5E"))
            p.drawRoundedRect(r.adjusted(2,2,-2,-2),c*.14,c*.14)
            paint_piece(p,piece_type,color,r.center().x(),r.top()+c*.88,c,grow=.96)
        p.setPen(QColor(C.text))
        p.setFont(font(SANS,max(11,int(c*.2)),600))
        p.drawText(QRectF(x0,y0+side/2-c*.3,side,c*.6),Qt.AlignmentFlag.AlignCenter,
                   "Scegli il pezzo per la promozione")

    def _targets_from(self,square):
        moves=[m for m in self.board.legal_moves if m.from_square==square]
        self.targets={m.to_square for m in moves}
        self.captures={m.to_square for m in moves if self.board.is_capture(m)}

    def _try_move(self,source,target):
        moves=[m for m in self.board.legal_moves if m.from_square==source and m.to_square==target]
        if not moves:
            return False
        move=moves[0]
        if move.promotion:
            self.promotion=(source,target,self.board.turn)
            self.drag_pos=QPointF(-1,-1)
            self._clear_selection()
            self.update()
            return True
        self._clear_selection()
        self.moveRequested.emit(move.uci())
        self.update()
        return True

    def mousePressEvent(self,event):
        if not self.interactive or self.locked or event.button()!=Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        pos=event.position()
        if self.promotion:
            x0,y0,c,side=self.board_geometry()
            for piece_type,r in self._promotion_rects(x0,y0,c):
                if r.contains(pos):
                    from_sq,to_sq,_=self.promotion
                    self.promotion=None
                    self.moveRequested.emit(chess.Move(from_sq,to_sq,promotion=piece_type).uci())
                    self.update()
                    return
            self.promotion=None
            self.update()
            return
        sq=self._square_at(pos)
        if sq is None:
            self._clear_selection()
            self.update()
            return
        if self.selected is not None and sq in self.targets:
            if self._try_move(self.selected,sq):
                return
        piece=self.board.piece_at(sq)
        if piece and piece.color==self.board.turn:
            self.selected=sq
            self._targets_from(sq)
            self.drag_source=sq
            self.press_pos=pos
            self.drag_pos=pos
            self.dragging=False
        else:
            self._clear_selection()
        self.update()

    def mouseMoveEvent(self,event):
        pos=event.position()
        self.drag_pos=pos
        sq=self._square_at(pos)
        if self.promotion:
            self.update()
            return
        if self.drag_source is not None and event.buttons()&Qt.MouseButton.LeftButton:
            if not self.dragging and (pos-self.press_pos).manhattanLength()>6:
                self.dragging=True
            self.hover=sq
            self.update()
            return
        if self.interactive and not self.locked:
            movable=sq is not None and self.board.piece_at(sq) is not None and self.board.piece_at(sq).color==self.board.turn
            target=self.selected is not None and sq in self.targets
            self.setCursor(Qt.CursorShape.PointingHandCursor if movable or target else Qt.CursorShape.ArrowCursor)
            new_hover=sq if target else None
            if new_hover!=self.hover:
                self.hover=new_hover
                self.update()

    def mouseReleaseEvent(self,event):
        if not self.interactive or self.locked or event.button()!=Qt.MouseButton.LeftButton:
            return
        source,was_dragging=self.drag_source,self.dragging
        self.drag_source=None
        self.dragging=False
        if source is None or not was_dragging:
            self.update()
            return
        target=self._square_at(event.position())
        if target is None or target==source or target not in self.targets or not self._try_move(source,target):
            self.hover=None
            self.update()

    def leaveEvent(self,event):
        if self.hover is not None:
            self.hover=None
            self.update()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape and (self.selected is not None or self.promotion):
            self.promotion=None
            self._clear_selection()
            self.update()
        else:
            super().keyPressEvent(event)
