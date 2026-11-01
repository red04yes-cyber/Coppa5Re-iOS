from __future__ import annotations
import json, os, random, sys
from datetime import datetime
from pathlib import Path
import chess
import chess.pgn
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QComboBox,
    QDoubleSpinBox, QLineEdit, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea, QMessageBox,
    QListWidget, QInputDialog, QFileDialog, QAbstractItemView, QSizePolicy
)

APP_NAME = "Coppa dei 5 Re"
PLAYERS = {
    "simone": ("Simone", "Easyclapp0"), "roberto": ("Roberto", "chuckyn0"),
    "matteo": ("Matteo", "mmathoo"), "jacopo": ("Jacopo", "jjand1"),
    "lotario": ("Lotario", "LotarioDettori"),
}
ORDER = list(PLAYERS)
GAMES = [
    ("R1-M1", 1, "jacopo", "roberto"), ("R1-M2", 1, "lotario", "matteo"),
    ("R2-M1", 2, "simone", "roberto"), ("R2-M2", 2, "lotario", "jacopo"),
    ("R3-M1", 3, "matteo", "simone"), ("R3-M2", 3, "roberto", "lotario"),
    ("R4-M1", 4, "simone", "lotario"), ("R4-M2", 4, "matteo", "jacopo"),
    ("R5-M1", 5, "jacopo", "simone"), ("R5-M2", 5, "roberto", "matteo"),
]
BYES = {1: "simone", 2: "matteo", 3: "jacopo", 4: "roberto", 5: "lotario"}
# Prior soggettivi 1-X-2, aggiornati con i punti e usati nelle simulazioni.
PRIORS = {
    "R1-M1": (.10,.13,.77), "R1-M2": (.12,.18,.70), "R2-M1": (.43,.18,.39),
    "R2-M2": (.22,.20,.58), "R3-M1": (.25,.15,.60), "R3-M2": (.78,.14,.08),
    "R4-M1": (.72,.15,.13), "R4-M2": (.56,.20,.24), "R5-M1": (.10,.12,.78),
    "R5-M2": (.60,.18,.22),
}
RESULT_OPTIONS = [(None,"In corso"),("1-0","1–0"),("1/2-1/2","½–½"),("0-1","0–1")]
GOLD="#D8B36A"; BG="#090D12"; PANEL="#111923"; PANEL2="#151F2B"
LINE="#283444"; TEXT="#EEF1F5"; MUTED="#8F9BAA"; GREEN="#65C69A"

def name(pid): return PLAYERS.get(pid,(pid,""))[0]
def game(game_id): return next(g for g in GAMES if g[0] == game_id)
def storage_path():
    folder = Path(os.environ.get("APPDATA", str(Path.home()))) / "Coppa5Re"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "tournament.json"

class BoardWidget(QWidget):
    moveRequested = Signal(str)
    def __init__(self, interactive=True):
        super().__init__()
        self.interactive=interactive; self.board=chess.Board()
        self.selected=None; self.targets=set(); self.locked=False
        self.setMinimumSize(320,320); self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
    def sizeHint(self): return QSize(420,420)
    def set_position(self, board, locked=False):
        self.board=board.copy(stack=True); self.locked=locked
        self.selected=None; self.targets=set(); self.update()
    def board_geometry(self):
        side=max(8,min(self.width()-38,self.height()-38))
        cell=side/8
        return (self.width()-side)/2,(self.height()-side)/2,cell,side
    def paintEvent(self, event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),QColor(PANEL))
        x0,y0,c,side=self.board_geometry()
        last=self.board.peek() if self.board.move_stack else None
        checked=self.board.king(self.board.turn) if self.board.is_check() else None
        for row in range(8):
            for file in range(8):
                sq=chess.square(file,7-row); x=x0+file*c; y=y0+row*c
                col=QColor("#C7B894") if (file+7-row)%2==0 else QColor("#273545")
                if last and sq in (last.from_square,last.to_square):
                    col=QColor("#758D68") if (file+7-row)%2==0 else QColor("#536F51")
                if sq==self.selected: col=QColor("#D1A653")
                if sq==checked: col=QColor("#A84949")
                p.fillRect(int(x),int(y),int(c+1),int(c+1),col)
                if sq in self.targets:
                    p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(18,26,34,130))
                    r=c*.16; p.drawEllipse(int(x+c/2-r),int(y+c/2-r),int(r*2),int(r*2))
                piece=self.board.piece_at(sq)
                if piece:
                    f=QFont("Segoe UI Symbol"); f.setPixelSize(max(20,int(c*.72))); p.setFont(f)
                    p.setPen(QColor("#FAF7F0") if piece.color else QColor("#111923"))
                    p.drawText(int(x),int(y),int(c),int(c),Qt.AlignmentFlag.AlignCenter,piece.unicode_symbol())
        p.setPen(QColor(MUTED)); p.setFont(QFont("Segoe UI",9))
        for f in range(8):
            p.drawText(int(x0+f*c),int(y0+side+3),int(c),14,Qt.AlignmentFlag.AlignHCenter,chess.FILE_NAMES[f])
        for r in range(8):
            p.drawText(int(x0-17),int(y0+r*c+c/2-7),14,14,Qt.AlignmentFlag.AlignCenter,str(8-r))
        p.setPen(QPen(QColor(LINE),1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(int(x0),int(y0),int(side),int(side))
    def mousePressEvent(self,event):
        if not self.interactive or self.locked or event.button()!=Qt.MouseButton.LeftButton: return
        x0,y0,c,side=self.board_geometry(); x=event.position().x(); y=event.position().y()
        f=int((x-x0)/c); r=int((y-y0)/c)
        if not(0<=f<8 and 0<=r<8):
            self.selected=None; self.targets=set(); self.update(); return
        sq=chess.square(f,7-r)
        if self.selected is not None and sq in self.targets:
            moves=[m for m in self.board.legal_moves if m.from_square==self.selected and m.to_square==sq]
            if moves:
                mv=moves[0]
                if mv.promotion:
                    opts=["Donna","Torre","Alfiere","Cavallo"]
                    pieces={"Donna":chess.QUEEN,"Torre":chess.ROOK,"Alfiere":chess.BISHOP,"Cavallo":chess.KNIGHT}
                    choice,ok=QInputDialog.getItem(self,"Promozione","Promuovi il pedone a:",opts,0,False)
                    if not ok: return
                    mv=chess.Move(mv.from_square,mv.to_square,promotion=pieces[choice])
                self.selected=None; self.targets=set(); self.moveRequested.emit(mv.uci()); self.update(); return
        piece=self.board.piece_at(sq)
        if piece and piece.color==self.board.turn:
            self.selected=sq; self.targets={m.to_square for m in self.board.legal_moves if m.from_square==sq}
        else:
            self.selected=None; self.targets=set()
        self.update()

class BoardCard(QFrame):
    def __init__(self,app,slot,initial):
        super().__init__(); self.app=app; self.slot=slot; self.game_id=initial
        self.setObjectName("Card"); lay=QVBoxLayout(self); lay.setContentsMargins(15,13,15,13); lay.setSpacing(8)
        top=QHBoxLayout(); tag=QLabel(f"TAVOLO 0{slot}"); tag.setObjectName("Eyebrow"); top.addWidget(tag); top.addStretch()
        self.selector=QComboBox()
        for gid,r,w,b in GAMES: self.selector.addItem(f"R{r} · {name(w)} – {name(b)}",gid)
        self.selector.setCurrentIndex(self.selector.findData(initial)); self.selector.currentIndexChanged.connect(self.select_game)
        self.selector.setMinimumWidth(220); top.addWidget(self.selector); lay.addLayout(top)
        self.match=QLabel(); self.match.setObjectName("MatchTitle"); lay.addWidget(self.match)
        self.board=BoardWidget(True); self.board.moveRequested.connect(self.move); lay.addWidget(self.board,1)
        bottom=QHBoxLayout(); self.turn=QLabel(); self.turn.setObjectName("Muted"); bottom.addWidget(self.turn,1)
        self.result=QComboBox()
        for value,label in RESULT_OPTIONS: self.result.addItem(label,value)
        self.result.currentIndexChanged.connect(lambda i:self.app.set_result(self.game_id,self.result.itemData(i)))
        bottom.addWidget(self.result); lay.addLayout(bottom)
        controls=QHBoxLayout()
        self.undo=QPushButton("↶  Annulla mossa"); self.undo.clicked.connect(lambda:self.app.undo(self.game_id))
        pgn=QPushButton("Esporta PGN"); pgn.clicked.connect(lambda:self.app.export_pgn(self.game_id))
        reset=QPushButton("Reset"); reset.clicked.connect(lambda:self.app.reset_board(self.game_id))
        controls.addWidget(self.undo); controls.addStretch(); controls.addWidget(pgn); controls.addWidget(reset); lay.addLayout(controls)
        self.refresh()
    def select_game(self,i):
        self.game_id=self.selector.itemData(i); self.refresh()
    def move(self,uci): self.app.record_move(self.game_id,uci)
    def refresh(self):
        gid,r,w,b=game(self.game_id); board=self.app.get_board(gid)
        self.match.setText(f"{name(w)}  <span style='color:{GOLD}'>vs</span>  {name(b)}")
        self.turn.setText("PARTITA CONCLUSA · SCACCHIERA BLOCCATA" if self.app.results.get(gid) else
                          f"AL MUOVERE: {'BIANCO' if board.turn else 'NERO'} · {board.fullmove_number}ª mossa")
        self.board.set_position(board,bool(self.app.results.get(gid)))
        self.result.blockSignals(True); self.result.setCurrentIndex(max(0,self.result.findData(self.app.results.get(gid)))); self.result.blockSignals(False)
        self.undo.setEnabled(bool(board.move_stack) and not self.app.results.get(gid))

class SpectatorCard(QFrame):
    def __init__(self,label):
        super().__init__(); self.setObjectName("Card")
        lay=QVBoxLayout(self); self.tag=QLabel(label); self.tag.setObjectName("Eyebrow")
        self.match=QLabel(); self.match.setObjectName("MatchTitle"); self.board=BoardWidget(False)
        lay.addWidget(self.tag); lay.addWidget(self.match); lay.addWidget(self.board,1)
    def update_game(self,app,gid):
        _,r,w,b=game(gid); self.match.setText(f"{name(w)}  <span style='color:{GOLD}'>vs</span>  {name(b)}")
        self.board.set_position(app.get_board(gid),True)

class BroadcastWindow(QWidget):
    def __init__(self,app):
        super().__init__(); self.app=app; self.setWindowTitle("C5R · Regia streaming")
        self.setStyleSheet(f"background:{BG};color:{TEXT};")
        root=QVBoxLayout(self); head=QHBoxLayout()
        logo=QLabel("♛  COPPA DEI 5 RE"); logo.setStyleSheet(f"color:{GOLD};font-size:23px;font-weight:900;letter-spacing:3px;")
        live=QLabel("● LIVE  ·  VISTA SPETTATORE"); live.setStyleSheet(f"color:{GREEN};font-weight:900;")
        head.addWidget(logo); head.addStretch(); head.addWidget(live); root.addLayout(head)
        row=QHBoxLayout(); self.cards=[SpectatorCard("TAVOLO 01"),SpectatorCard("TAVOLO 02")]
        for c in self.cards: row.addWidget(c,1)
        root.addLayout(row,1); self.footer=QLabel(); self.footer.setStyleSheet(f"color:{GOLD};font-size:15px;font-weight:800;padding:10px;")
        root.addWidget(self.footer); self.refresh_from_app()
    def refresh_from_app(self):
        for c,live in zip(self.cards,self.app.live_cards): c.update_game(self.app,live.game_id)
        self.footer.setText("CLASSIFICA     "+"   •   ".join(f"{name(x['id'])} {x['points']:.1f} pt" for x in self.app.standings()))
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape: self.close()
        else: super().keyPressEvent(event)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Coppa dei 5 Re · Control Room")
        self.resize(1500,950); self.setMinimumSize(1160,780)
        self.results={}; self.penalties=[]; self.moves={}; self.boards={}; self.broadcast=None
        self.load_state(); self.build_ui(); self.refresh_all()
    def load_state(self):
        path=storage_path()
        if path.exists():
            try:
                data=json.loads(path.read_text(encoding="utf-8"))
                self.results=data.get("results",{}); self.penalties=data.get("penalties",[]); self.moves=data.get("moves",{})
            except Exception: self.results={}; self.penalties=[]; self.moves={}
    def save(self):
        path=storage_path(); tmp=path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"results":self.results,"penalties":self.penalties,"moves":self.moves,
                                  "saved_at":datetime.now().isoformat(timespec="seconds")},ensure_ascii=False,indent=2),encoding="utf-8")
        tmp.replace(path)
    def get_board(self,gid):
        if gid not in self.boards:
            b=chess.Board()
            for uci in self.moves.get(gid,[]):
                try:
                    m=chess.Move.from_uci(uci)
                    if m in b.legal_moves: b.push(m)
                except Exception: break
            self.boards[gid]=b
        return self.boards[gid]
    def record_move(self,gid,uci):
        if self.results.get(gid): self.statusBar().showMessage("Partita conclusa: rimuovi il risultato prima di continuare.",3500); return
        b=self.get_board(gid)
        try:
            m=chess.Move.from_uci(uci)
            if m not in b.legal_moves: self.statusBar().showMessage("Mossa illegale: non registrata.",3000); return
            b.push(m); self.moves[gid]=[x.uci() for x in b.move_stack]; self.save(); self.refresh_all()
        except Exception as exc: self.statusBar().showMessage(f"Mossa non registrata: {exc}",4000)
    def undo(self,gid):
        b=self.get_board(gid)
        if b.move_stack and not self.results.get(gid):
            b.pop(); self.moves[gid]=[x.uci() for x in b.move_stack]; self.save(); self.refresh_all()
    def reset_board(self,gid):
        if QMessageBox.question(self,"Reset","Cancellare tutte le mosse di questa partita?")==QMessageBox.StandardButton.Yes:
            self.boards[gid]=chess.Board(); self.moves[gid]=[]; self.save(); self.refresh_all()
    def set_result(self,gid,value):
        if value is None: self.results.pop(gid,None)
        else: self.results[gid]=value
        self.save(); self.refresh_all(); self.statusBar().showMessage("Risultato salvato · classifica e quote aggiornate.",3000)
    def raw_stats(self):
        pts={p:0.0 for p in PLAYERS}; played={p:0 for p in PLAYERS}
        wins={p:0 for p in PLAYERS}; draws={p:0 for p in PLAYERS}; losses={p:0 for p in PLAYERS}
        for gid,r,w,b in GAMES:
            result=self.results.get(gid)
            if not result: continue
            played[w]+=1; played[b]+=1
            if result=="1-0": pts[w]+=1; wins[w]+=1; losses[b]+=1
            elif result=="0-1": pts[b]+=1; wins[b]+=1; losses[w]+=1
            else: pts[w]+=.5; pts[b]+=.5; draws[w]+=1; draws[b]+=1
        return pts,played,wins,draws,losses
    def penalty_points(self):
        out={p:0.0 for p in PLAYERS}
        for item in self.penalties:
            if item.get("player") in out: out[item["player"]]+=float(item.get("points",0))
        return out
    def standings(self):
        pts,played,wins,draws,losses=self.raw_stats(); pen=self.penalty_points()
        rows=[{"id":p,"played":played[p],"wins":wins[p],"draws":draws[p],"losses":losses[p],
               "penalty":pen[p],"points":pts[p]+pen[p]} for p in PLAYERS]
        return sorted(rows,key=lambda x:(-x["points"],ORDER.index(x["id"])))
    def odds(self,n=7000):
        raw,played,_,_,_=self.raw_stats(); pen=self.penalty_points()
        current={p:raw[p]+pen[p] for p in PLAYERS}
        form={p:(raw[p]/played[p] if played[p] else .5) for p in PLAYERS}
        remaining=[g for g in GAMES if not self.results.get(g[0])]
        win={p:0.0 for p in PLAYERS}; top={p:0.0 for p in PLAYERS}
        rng=random.Random(20261101+len(self.results)*101+len(self.penalties)*17+int(sum(current.values())*10))
        for _ in range(n):
            score=current.copy()
            for gid,r,w,b in remaining:
                pw,pd,pb=PRIORS[gid]
                shift=max(-.12,min(.12,.09*(form[w]-form[b])))
                pw=max(.025,pw+shift); pb=max(.025,pb-shift); total=pw+pd+pb
                pw,pd= pw/total,pd/total
                draw=rng.random()
                if draw<pw: score[w]+=1
                elif draw<pw+pd: score[w]+=.5; score[b]+=.5
                else: score[b]+=1
            best=max(score.values()); tied=[p for p in PLAYERS if score[p]==best]
            for p in tied: win[p]+=1/len(tied)
            slots=4
            for value in sorted(set(score.values()),reverse=True):
                group=[p for p in PLAYERS if score[p]==value]
                if slots<=0: break
                share=min(1.0,slots/len(group))
                for p in group: top[p]+=share
                slots-=min(slots,len(group))
        return {p:(win[p]/n,top[p]/n) for p in PLAYERS}
    def build_ui(self):
        root=QWidget(); outer=QVBoxLayout(root); outer.setContentsMargins(22,18,22,16); outer.setSpacing(14)
        header=QHBoxLayout(); crown=QLabel("♛"); crown.setStyleSheet(f"color:{GOLD};font-size:36px;font-weight:900;")
        header.addWidget(crown); texts=QVBoxLayout()
        title=QLabel("COPPA DEI 5 RE"); title.setObjectName("BrandTitle")
        sub=QLabel("CONTROL ROOM  ·  TOURNAMENT EDITION"); sub.setObjectName("Eyebrow")
        texts.addWidget(title); texts.addWidget(sub); header.addLayout(texts); header.addStretch()
        saved=QLabel("●  OFFLINE  ·  SALVATAGGIO AUTOMATICO"); saved.setObjectName("SavedBadge"); header.addWidget(saved)
        stream=QPushButton("◉  VISTA STREAMING"); stream.setObjectName("PrimaryButton"); stream.clicked.connect(self.open_broadcast); header.addWidget(stream)
        outer.addLayout(header)
        self.tabs=QTabWidget()
        self.tabs.addTab(self.build_live(),"LIVE ARENA"); self.tabs.addTab(self.build_calendar(),"CALENDARIO")
        self.tabs.addTab(self.build_standings(),"CLASSIFICA"); self.tabs.addTab(self.build_odds(),"QUOTE")
        self.tabs.addTab(self.build_penalties(),"PENALITÀ"); self.tabs.addTab(self.build_playoffs(),"PLAYOFF")
        outer.addWidget(self.tabs,1)
        foot=QLabel("COPPA DEI 5 RE  /  DAL 15 NOVEMBRE 2026  /  DATI LOCALI SU QUESTO PC"); foot.setObjectName("Footnote")
        outer.addWidget(foot); self.setCentralWidget(root)
        self.statusBar().showMessage("Pronto · seleziona un pezzo e poi la casa di destinazione.")
    def build_live(self):
        page=QWidget(); l=QHBoxLayout(page); l.setContentsMargins(0,14,0,0); l.setSpacing(14)
        self.live_cards=[BoardCard(self,1,"R1-M1"),BoardCard(self,2,"R1-M2")]
        for c in self.live_cards: l.addWidget(c,1)
        return page
    def build_calendar(self):
        page=QWidget(); l=QVBoxLayout(page)
        h=QLabel("PROGRAMMA E RISULTATI"); h.setObjectName("SectionTitle"); l.addWidget(h)
        d=QLabel("Calendario round-robin già caricato. Ogni risultato aggiorna immediatamente classifica e simulazioni quote.")
        d.setObjectName("Muted"); l.addWidget(d)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        content=QWidget(); v=QVBoxLayout(content); self.calendar_combos={}
        for gid,r,w,b in GAMES:
            card=QFrame(); card.setObjectName("Card"); row=QHBoxLayout(card)
            tag=QLabel(f"ROUND {r}"); tag.setObjectName("Eyebrow"); tag.setFixedWidth(85)
            matchup=QLabel(f"{name(w)}  <span style='color:{GOLD}'>vs</span>  {name(b)}"); matchup.setObjectName("MatchTitle")
            combo=QComboBox()
            for val,label in RESULT_OPTIONS: combo.addItem(label,val)
            combo.currentIndexChanged.connect(lambda i,gid=gid,cb=combo:self.set_result(gid,cb.itemData(i)))
            self.calendar_combos[gid]=combo; row.addWidget(tag); row.addWidget(matchup,1); row.addWidget(combo); v.addWidget(card)
        for r,p in BYES.items():
            bye=QLabel(f"ROUND {r}  ·  Riposa: {name(p)}  ·  BYE"); bye.setObjectName("Muted"); v.addWidget(bye)
        v.addStretch(); scroll.setWidget(content); l.addWidget(scroll,1); return page
    def build_standings(self):
        page=QWidget(); l=QVBoxLayout(page)
        h=QLabel("CLASSIFICA GENERALE"); h.setObjectName("SectionTitle"); l.addWidget(h)
        d=QLabel("Vittoria 1 pt · patta 0,5 pt · sconfitta 0 pt · penalità sottratte. Gli ex aequo restano pari finché non viene definito uno spareggio.")
        d.setObjectName("Muted"); l.addWidget(d)
        self.st_table=QTableWidget(0,8); self.st_table.setHorizontalHeaderLabels(["POS","GIOCATORE","G","V","X","P","PEN.","PT"])
        self.st_table.verticalHeader().setVisible(False); self.st_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.st_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.st_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        for c in (0,2,3,4,5,6,7): self.st_table.horizontalHeader().setSectionResizeMode(c,QHeaderView.ResizeMode.ResizeToContents)
        l.addWidget(self.st_table,1); self.st_summary=QLabel(); self.st_summary.setObjectName("Muted"); l.addWidget(self.st_summary)
        return page
    def build_odds(self):
        page=QWidget(); l=QVBoxLayout(page)
        h=QLabel("QUOTE E PROBABILITÀ"); h.setObjectName("SectionTitle"); l.addWidget(h)
        desc=QLabel("Simulazione Monte Carlo sulle partite ancora da giocare, ricalcolata dopo ogni risultato e penalità. Quote eque indicative: non sono quote bookmaker né suggerimenti di puntata.")
        desc.setObjectName("Muted"); desc.setWordWrap(True); l.addWidget(desc)
        self.odds_table=QTableWidget(0,4); self.odds_table.setHorizontalHeaderLabels(["GIOCATORE","VINCENTE TORNEO","QUOTA EQUA","TOP 4"])
        self.odds_table.verticalHeader().setVisible(False); self.odds_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.odds_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.odds_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for c in (1,2,3): self.odds_table.horizontalHeader().setSectionResizeMode(c,QHeaderView.ResizeMode.ResizeToContents)
        l.addWidget(self.odds_table,1); self.odds_footer=QLabel(); self.odds_footer.setObjectName("Muted"); l.addWidget(self.odds_footer)
        return page
    def build_penalties(self):
        page=QWidget(); l=QVBoxLayout(page)
        h=QLabel("REGISTRO PENALITÀ"); h.setObjectName("SectionTitle"); l.addWidget(h)
        d=QLabel("Registra detrazioni di punti, scegliendo giocatore, importo e motivazione. Le modifiche sono annullabili dal registro.")
        d.setObjectName("Muted"); l.addWidget(d)
        card=QFrame(); card.setObjectName("Card"); grid=QGridLayout(card)
        grid.addWidget(QLabel("GIOCATORE"),0,0); self.pen_player=QComboBox()
        for p in PLAYERS: self.pen_player.addItem(name(p),p)
        grid.addWidget(self.pen_player,1,0); grid.addWidget(QLabel("PENALITÀ"),0,1)
        self.pen_amount=QDoubleSpinBox(); self.pen_amount.setRange(.5,10); self.pen_amount.setSingleStep(.5); self.pen_amount.setValue(.5); self.pen_amount.setSuffix(" pt")
        grid.addWidget(self.pen_amount,1,1); grid.addWidget(QLabel("MOTIVAZIONE"),0,2)
        self.pen_reason=QLineEdit(); self.pen_reason.setPlaceholderText("Ritardo, infrazione, decisione arbitro…"); grid.addWidget(self.pen_reason,1,2)
        add=QPushButton("REGISTRA PENALITÀ"); add.setObjectName("PrimaryButton"); add.clicked.connect(self.add_penalty); grid.addWidget(add,1,3)
        l.addWidget(card); self.pen_list=QListWidget(); l.addWidget(self.pen_list,1)
        row=QHBoxLayout(); row.addStretch(); rem=QPushButton("Annulla voce selezionata"); rem.clicked.connect(self.remove_penalty); row.addWidget(rem); l.addLayout(row)
        return page
    def bracket_card(self,title,a,b):
        f=QFrame(); f.setObjectName("Card"); v=QVBoxLayout(f)
        h=QLabel(title); h.setObjectName("Eyebrow"); x=QLabel(a); x.setObjectName("MatchTitle"); y=QLabel(b); y.setObjectName("MatchTitle")
        v.addWidget(h); v.addWidget(x); v.addWidget(y); f.labels=(h,x,y); return f
    def build_playoffs(self):
        page=QWidget(); l=QVBoxLayout(page)
        h=QLabel("TABELLONE PLAYOFF"); h.setObjectName("SectionTitle"); l.addWidget(h)
        d=QLabel("Tabellone provvisorio: semifinali 1ª–4ª e 2ª–3ª, poi finale e finale 3°/4° posto. Ex aequo da risolvere con spareggio.")
        d.setObjectName("Muted"); d.setWordWrap(True); l.addWidget(d)
        grid=QGridLayout(); self.sf1=self.bracket_card("SEMIFINALE 1","1ª classificata","4ª classificata")
        self.sf2=self.bracket_card("SEMIFINALE 2","2ª classificata","3ª classificata")
        self.final=self.bracket_card("FINALE","Vincente SF1","Vincente SF2")
        self.third=self.bracket_card("3° / 4° POSTO","Perdente SF1","Perdente SF2")
        grid.addWidget(self.sf1,0,0); grid.addWidget(self.sf2,0,2); grid.addWidget(self.final,1,1); grid.addWidget(self.third,2,1)
        l.addLayout(grid); l.addStretch(); return page
    def add_penalty(self):
        p=self.pen_player.currentData(); amount=float(self.pen_amount.value()); reason=self.pen_reason.text().strip() or "Penalità manuale"
        self.penalties.append({"player":p,"points":-amount,"reason":reason,"time":datetime.now().strftime("%d/%m/%Y %H:%M")})
        self.pen_reason.clear(); self.save(); self.refresh_all()
    def remove_penalty(self):
        i=self.pen_list.currentRow()
        if 0<=i<len(self.penalties): del self.penalties[i]; self.save(); self.refresh_all()
    def export_pgn(self,gid):
        b=self.get_board(gid); _,r,w,bl=game(gid); node=chess.pgn.Game.from_board(b)
        node.headers["Event"]=APP_NAME; node.headers["Round"]=str(r); node.headers["White"]=name(w); node.headers["Black"]=name(bl)
        node.headers["Result"]=self.results.get(gid,"*")
        content=node.accept(chess.pgn.StringExporter(headers=True,variations=False,comments=False))
        path,_=QFileDialog.getSaveFileName(self,"Esporta PGN",gid+".pgn","Partite PGN (*.pgn)")
        if path: Path(path).write_text(content,encoding="utf-8"); self.statusBar().showMessage("PGN esportato.",2500)
    def refresh_all(self):
        if not hasattr(self,"live_cards"): return
        for c in self.live_cards: c.refresh()
        for gid,cb in self.calendar_combos.items():
            cb.blockSignals(True); cb.setCurrentIndex(max(0,cb.findData(self.results.get(gid)))); cb.blockSignals(False)
        self.refresh_standings(); self.refresh_odds(); self.refresh_penalties(); self.refresh_playoffs()
        if self.broadcast and self.broadcast.isVisible(): self.broadcast.refresh_from_app()
    def refresh_standings(self):
        rows=self.standings(); self.st_table.setRowCount(5); previous=None; rank=0
        for i,x in enumerate(rows):
            if previous is None or x["points"]!=previous: rank=i+1
            previous=x["points"]; vals=[f"{rank}°",name(x["id"]),str(x["played"]),str(x["wins"]),str(x["draws"]),str(x["losses"]),
                   f"{x['penalty']:+.1f}" if x["penalty"] else "—",f"{x['points']:.1f}"]
            for c,val in enumerate(vals):
                item=QTableWidgetItem(val); item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c!=1 else Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
                if x["id"]=="simone": item.setForeground(QColor(GOLD))
                if c==7: item.setFont(QFont("Segoe UI",11,QFont.Weight.Bold))
                self.st_table.setItem(i,c,item)
        self.st_summary.setText(f"PARTITE CONCLUSE  {len(self.results)}/10     ·     RIMANENTI  {10-len(self.results)}     ·     PENALITÀ  {len(self.penalties)}")
    def refresh_odds(self):
        values=self.odds(); ordered=sorted(PLAYERS,key=lambda p:values[p][0],reverse=True); self.odds_table.setRowCount(5)
        for i,p in enumerate(ordered):
            win,top=values[p]; vals=[name(p),f"{win*100:.1f}%",("—" if win<=0 else f"{1/win:.2f}"),f"{top*100:.1f}%"]
            for c,val in enumerate(vals):
                item=QTableWidgetItem(val); item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c else Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
                if p=="simone": item.setForeground(QColor(GOLD))
                self.odds_table.setItem(i,c,item)
        self.odds_footer.setText(f"7.000 scenari simulati · {len(self.results)} risultati registrati · quota equa = 1 / probabilità stimata.")
    def refresh_penalties(self):
        self.pen_list.clear()
        if not self.penalties: self.pen_list.addItem("Nessuna penalità registrata.")
        for x in self.penalties:
            self.pen_list.addItem(f"{name(x.get('player',''))}   {x.get('points',0):+.1f} pt   ·   {x.get('reason','')}   ·   {x.get('time','')}")
    def refresh_playoffs(self):
        rows=self.standings(); names=[name(x["id"]) for x in rows]
        self.sf1.labels[0].setText("SEMIFINALE 1 · "+("CLASSIFICA FINALE" if len(self.results)==10 else "PROIEZIONE"))
        self.sf1.labels[1].setText("1°  "+names[0]); self.sf1.labels[2].setText("4°  "+names[3])
        self.sf2.labels[0].setText("SEMIFINALE 2 · "+("CLASSIFICA FINALE" if len(self.results)==10 else "PROIEZIONE"))
        self.sf2.labels[1].setText("2°  "+names[1]); self.sf2.labels[2].setText("3°  "+names[2])
    def open_broadcast(self):
        if self.broadcast is None: self.broadcast=BroadcastWindow(self)
        self.broadcast.refresh_from_app(); self.broadcast.showFullScreen(); self.broadcast.raise_(); self.broadcast.activateWindow()
    def closeEvent(self,event):
        self.save()
        if self.broadcast: self.broadcast.close()
        event.accept()

STYLE=f"""
QMainWindow,QWidget{{background:{BG};color:{TEXT};font-family:'Segoe UI';font-size:13px;}}
QTabWidget::pane{{border:1px solid {LINE};border-radius:12px;background:{BG};top:-1px;}}
QTabBar::tab{{background:#101721;color:{MUTED};padding:12px 18px;margin-right:4px;border-top-left-radius:8px;border-top-right-radius:8px;font-weight:800;letter-spacing:1px;}}
QTabBar::tab:selected{{background:#1B2633;color:{GOLD};border-bottom:2px solid {GOLD};}}
QFrame#Card{{background:{PANEL};border:1px solid {LINE};border-radius:14px;}}
QLabel#BrandTitle{{color:{TEXT};font-size:22px;font-weight:900;letter-spacing:3px;}}
QLabel#Eyebrow{{color:{GOLD};font-size:10px;font-weight:900;letter-spacing:2px;}}
QLabel#MatchTitle{{color:{TEXT};font-size:17px;font-weight:800;}}
QLabel#SectionTitle{{color:{TEXT};font-size:21px;font-weight:900;letter-spacing:1px;padding:8px 0;}}
QLabel#Muted{{color:{MUTED};font-size:12px;}}
QLabel#Footnote{{color:#677485;font-size:10px;letter-spacing:1.5px;}}
QLabel#SavedBadge{{color:{GREEN};font-size:10px;font-weight:800;letter-spacing:1px;padding:8px 12px;background:#10241F;border:1px solid #28513F;border-radius:8px;}}
QPushButton{{background:{PANEL2};color:{TEXT};border:1px solid {LINE};border-radius:8px;padding:9px 13px;font-weight:700;}}
QPushButton:hover{{border-color:{GOLD};color:{GOLD};}}
QPushButton:disabled{{color:#5E6875;background:#10151C;}}
QPushButton#PrimaryButton{{background:#B68D48;color:#10151B;border:1px solid #D6B16B;font-weight:900;}}
QPushButton#PrimaryButton:hover{{background:#D6B16B;color:#080B10;}}
QComboBox,QLineEdit,QDoubleSpinBox{{background:#0D141D;color:{TEXT};border:1px solid {LINE};border-radius:7px;padding:8px 10px;min-height:22px;}}
QComboBox QAbstractItemView{{background:{PANEL};color:{TEXT};selection-background-color:#334457;}}
QTableWidget{{background:{PANEL};alternate-background-color:#141E29;border:1px solid {LINE};border-radius:10px;gridline-color:{LINE};}}
QTableWidget::item{{padding:12px 8px;border-bottom:1px solid {LINE};}}
QHeaderView::section{{background:#1A2633;color:{GOLD};padding:11px 8px;border:none;font-size:10px;font-weight:900;}}
QListWidget{{background:{PANEL};border:1px solid {LINE};border-radius:10px;padding:8px;}}
QListWidget::item{{padding:12px;border-bottom:1px solid {LINE};}}
QListWidget::item:selected{{background:#253546;color:{GOLD};}}
QStatusBar{{background:#0D131B;color:{MUTED};border-top:1px solid {LINE};}}
QLabel{{background:transparent;}}
"""

def main():
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setStyle("Fusion"); app.setStyleSheet(STYLE)
    win=MainWindow(); win.show(); sys.exit(app.exec())
if __name__=="__main__": main()
