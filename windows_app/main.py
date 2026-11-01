from __future__ import annotations
import json, os, random, sys, shutil, hashlib, math, csv, time, subprocess
from datetime import datetime
from pathlib import Path
from itertools import combinations
import chess
import chess.pgn
from PySide6.QtCore import Qt, QSize, Signal, QThread, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPdfWriter, QKeySequence, QShortcut
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QComboBox,
    QDoubleSpinBox, QLineEdit, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea, QMessageBox,
    QListWidget, QInputDialog, QFileDialog, QAbstractItemView, QSizePolicy,
    QDialog, QDialogButtonBox, QProgressBar, QStackedWidget
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
DEFAULT_GAMES = list(GAMES)
# Prior soggettivi 1-X-2, aggiornati con i punti e usati nelle simulazioni.
PRIORS = {
    "R1-M1": (.10,.13,.77), "R1-M2": (.12,.18,.70), "R2-M1": (.43,.18,.39),
    "R2-M2": (.22,.20,.58), "R3-M1": (.25,.15,.60), "R3-M2": (.78,.14,.08),
    "R4-M1": (.72,.15,.13), "R4-M2": (.56,.20,.24), "R5-M1": (.10,.12,.78),
    "R5-M2": (.60,.18,.22),
}

PAIR_PRIORS = {}
for _gid, _round, _white, _black in DEFAULT_GAMES:
    PAIR_PRIORS[frozenset((_white, _black))] = (_white, _black, PRIORS[_gid])

def validate_schedule(schedule):
    if len(schedule) != 10:
        raise ValueError("Il girone deve contenere esattamente 10 partite.")
    expected_ids = {f"R{r}-M{m}" for r in range(1, 6) for m in (1, 2)}
    if {g[0] for g in schedule} != expected_ids:
        raise ValueError("Ogni turno deve avere due partite: M1 e M2.")
    pairings = set()
    byes = []
    for rnd in range(1, 6):
        round_games = [g for g in schedule if g[1] == rnd]
        if len(round_games) != 2:
            raise ValueError(f"Il turno {rnd} deve avere due partite.")
        seen = []
        for _gid, _r, white, black in round_games:
            if white not in PLAYERS or black not in PLAYERS or white == black:
                raise ValueError(f"Accoppiamento non valido al turno {rnd}.")
            seen.extend([white, black])
            pair = frozenset((white, black))
            if pair in pairings:
                raise ValueError("Ci sono partite ripetute: ogni coppia deve incontrarsi una sola volta.")
            pairings.add(pair)
        bye_candidates = [p for p in ORDER if p not in seen]
        if len(bye_candidates) != 1 or len(set(seen)) != 4:
            raise ValueError(f"Al turno {rnd} ogni giocatore deve giocare al massimo una volta e uno solo deve riposare.")
        byes.append(bye_candidates[0])
    if len(pairings) != 10 or set(pairings) != {frozenset(pair) for pair in combinations(ORDER, 2)}:
        raise ValueError("Il calendario deve contenere tutti i 10 scontri diretti, una volta ciascuno.")
    if len(set(byes)) != 5:
        raise ValueError("Ogni giocatore deve avere esattamente un turno di riposo.")
    return True

def make_random_schedule():
    ring = ORDER[:]
    random.shuffle(ring)
    ring.append(None)
    raw_rounds = []
    for rnd in range(1, 6):
        pairs = [(ring[i], ring[-1-i]) for i in range(3)]
        matches = [(a, b) for a, b in pairs if a is not None and b is not None]
        raw_rounds.append((rnd, matches))
        ring = [ring[0], ring[-1]] + ring[1:-1]

    best = None
    best_score = float("inf")
    for _ in range(3000):
        candidate = []
        white_count = {p: 0 for p in ORDER}
        for rnd, matches in raw_rounds:
            oriented = []
            for a, b in matches:
                white, black = (a, b) if random.random() < 0.5 else (b, a)
                white_count[white] += 1
                oriented.append((white, black))
            candidate.append((rnd, oriented))
        score = sum((white_count[p] - 2) ** 2 for p in ORDER)
        if score < best_score:
            best, best_score = candidate, score
        if score == 0:
            break

    schedule = []
    for rnd, matches in best:
        for idx, (white, black) in enumerate(matches, 1):
            schedule.append((f"R{rnd}-M{idx}", rnd, white, black))
    validate_schedule(schedule)
    return schedule

class ScheduleEditorDialog(QDialog):
    def __init__(self, current_schedule, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modifica il girone")
        self.setMinimumWidth(880)
        self.schedule = None
        self.controls = []
        root = QVBoxLayout(self)
        intro = QLabel("Modifica gli accoppiamenti turno per turno. Ogni giocatore deve comparire una sola volta per turno; ogni coppia si incontra una sola volta.")
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        root.addWidget(intro)
        grid = QGridLayout()
        headers = ["TURNO", "TAVOLO 1 · BIANCO", "TAVOLO 1 · NERO",
                   "TAVOLO 2 · BIANCO", "TAVOLO 2 · NERO", "RIPOSA"]
        for col, title in enumerate(headers):
            label = QLabel(title)
            label.setObjectName("Eyebrow")
            grid.addWidget(label, 0, col)
        for rnd in range(1, 6):
            row_games = [g for g in current_schedule if g[1] == rnd]
            row_games.sort(key=lambda g: g[0])
            current_bye = next(p for p in ORDER if p not in [row_games[0][2], row_games[0][3], row_games[1][2], row_games[1][3]])
            values = [rnd, row_games[0][2], row_games[0][3], row_games[1][2], row_games[1][3], current_bye]
            round_label = QLabel(f"ROUND {rnd}")
            round_label.setObjectName("MatchTitle")
            grid.addWidget(round_label, rnd, 0)
            row_controls = []
            for col, value in enumerate(values[1:], 1):
                combo = QComboBox()
                for pid in ORDER:
                    combo.addItem(name(pid), pid)
                combo.setCurrentIndex(combo.findData(value))
                grid.addWidget(combo, rnd, col)
                row_controls.append(combo)
            self.controls.append(row_controls)
        root.addLayout(grid)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def validate_and_accept(self):
        proposed = []
        for rnd, row in enumerate(self.controls, 1):
            w1, b1, w2, b2, bye = [combo.currentData() for combo in row]
            if len({w1, b1, w2, b2, bye}) != 5:
                QMessageBox.warning(self, "Turno non valido", f"Nel turno {rnd} ogni giocatore deve comparire una sola volta, compreso chi riposa.")
                return
            proposed.extend([(f"R{rnd}-M1", rnd, w1, b1), (f"R{rnd}-M2", rnd, w2, b2)])
        try:
            validate_schedule(proposed)
        except ValueError as exc:
            QMessageBox.warning(self, "Girone non valido", str(exc))
            return
        self.schedule = proposed
        self.accept()

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
        self.selected=None; self.targets=set(); self.locked=False; self.flipped=False; self.theme_index=0; self.drag_source=None
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
                board_file=7-file if self.flipped else file
                board_rank=row if self.flipped else 7-row
                sq=chess.square(board_file,board_rank); x=x0+file*c; y=y0+row*c
                themes=[("#C7B894","#273545"),("#E8D8B8","#8A6748"),("#E9EDF2","#68849C"),("#C6D2B3","#566E4A")]
                light,dark=themes[self.theme_index%len(themes)]
                col=QColor(light) if (board_file+board_rank)%2==1 else QColor(dark)
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
            label_file=7-f if self.flipped else f
            p.drawText(int(x0+f*c),int(y0+side+3),int(c),14,Qt.AlignmentFlag.AlignHCenter,chess.FILE_NAMES[label_file])
        for r in range(8):
            label_rank=r+1 if self.flipped else 8-r
            p.drawText(int(x0-17),int(y0+r*c+c/2-7),14,14,Qt.AlignmentFlag.AlignCenter,str(label_rank))
        p.setPen(QPen(QColor(LINE),1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(int(x0),int(y0),int(side),int(side))
    def mousePressEvent(self,event):
        if not self.interactive or self.locked or event.button()!=Qt.MouseButton.LeftButton: return
        x0,y0,c,side=self.board_geometry(); x=event.position().x(); y=event.position().y()
        f=int((x-x0)/c); r=int((y-y0)/c)
        if not(0<=f<8 and 0<=r<8):
            self.selected=None; self.targets=set(); self.update(); return
        board_file=7-f if self.flipped else f
        board_rank=r if self.flipped else 7-r
        sq=chess.square(board_file,board_rank)
        piece_at=self.board.piece_at(sq)
        self.drag_source=sq if piece_at and piece_at.color==self.board.turn else None
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
    def mouseReleaseEvent(self,event):
        if not self.interactive or self.locked or event.button()!=Qt.MouseButton.LeftButton:
            return
        source=self.drag_source
        self.drag_source=None
        if source is None:
            return
        x0,y0,c,side=self.board_geometry()
        col=int((event.position().x()-x0)/c); row=int((event.position().y()-y0)/c)
        if not(0<=col<8 and 0<=row<8):
            return
        board_file=7-col if self.flipped else col
        board_rank=row if self.flipped else 7-row
        target=chess.square(board_file,board_rank)
        if target==source:
            return
        moves=[m for m in self.board.legal_moves if m.from_square==source and m.to_square==target]
        if moves:
            move=moves[0]
            if move.promotion:
                opts=["Donna","Torre","Alfiere","Cavallo"]
                pieces={"Donna":chess.QUEEN,"Torre":chess.ROOK,"Alfiere":chess.BISHOP,"Cavallo":chess.KNIGHT}
                choice,ok=QInputDialog.getItem(self,"Promozione","Promuovi il pedone a:",opts,0,False)
                if not ok: return
                move=chess.Move(move.from_square,move.to_square,promotion=pieces[choice])
            self.selected=None; self.targets=set(); self.moveRequested.emit(move.uci()); self.update()
    def toggle_orientation(self):
        self.flipped=not self.flipped; self.selected=None; self.targets=set(); self.update()
    def cycle_theme(self):
        self.theme_index=(self.theme_index+1)%4; self.update()

class LogoWidget(QWidget):
    def __init__(self,width=100,height=110,parent=None):
        super().__init__(parent)
        self.setFixedSize(width,height)
        base=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))
        logo=base/"assets"/"c5r-logo.svg"
        if not logo.exists():
            logo=Path(__file__).resolve().parent/"assets"/"c5r-logo.svg"
        self.renderer=QSvgRenderer(str(logo))
    def paintEvent(self,event):
        painter=QPainter(self)
        self.renderer.render(painter,self.rect())
        painter.end()


class EngineAnalysisWorker(QThread):
    analysisReady = Signal(str, int)

    def __init__(self, engine_path, game_id, board, parent=None):
        super().__init__(parent)
        self.engine_path = engine_path
        self.game_id = game_id
        self.position = board.copy(stack=True)

    def run(self):
        engine = None
        try:
            import chess.engine
            popen_args={}
            if os.name=="nt":
                startupinfo=subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow=subprocess.SW_HIDE
                popen_args={"creationflags":subprocess.CREATE_NO_WINDOW,"startupinfo":startupinfo}
            engine = chess.engine.SimpleEngine.popen_uci(self.engine_path, timeout=8, cwd=str(Path(self.engine_path).parent), **popen_args)
            try:
                engine.configure({"Threads": 2, "Hash": 96})
            except Exception:
                pass
            info = engine.analyse(self.position, chess.engine.Limit(depth=12, time=1.5))
            score = info["score"].white().score(mate_score=10000)
            if score is not None:
                self.analysisReady.emit(self.game_id, int(score))
        except Exception:
            pass
        finally:
            if engine is not None:
                try:
                    engine.quit()
                except Exception:
                    pass


class BoardCard(QFrame):
    def __init__(self,app,slot,initial):
        super().__init__(); self.app=app; self.slot=slot; self.game_id=initial
        self.setObjectName("Card"); lay=QVBoxLayout(self); lay.setContentsMargins(15,13,15,13); lay.setSpacing(8)
        top=QHBoxLayout(); tag=QLabel(f"TAVOLO 0{slot}"); tag.setObjectName("Eyebrow"); top.addWidget(tag); top.addStretch()
        self.selector=QComboBox()
        self.refresh_selector()
        self.selector.currentIndexChanged.connect(self.select_game)
        self.selector.setMinimumWidth(220); top.addWidget(self.selector); lay.addLayout(top)
        self.match=QLabel(); self.match.setObjectName("MatchTitle"); lay.addWidget(self.match)
        self.clock_label=QLabel(); self.clock_label.setObjectName("Muted"); lay.addWidget(self.clock_label)
        self.history_index=None
        self.board=BoardWidget(True); self.board.moveRequested.connect(self.move); lay.addWidget(self.board,1)
        nav=QHBoxLayout()
        self.prev_move_btn=QPushButton("◀  Mossa precedente"); self.prev_move_btn.clicked.connect(self.previous_move)
        self.next_move_btn=QPushButton("Mossa successiva  ▶"); self.next_move_btn.clicked.connect(self.next_move)
        self.view_ply=QLabel("0 / 0"); self.view_ply.setObjectName("Muted")
        nav.addWidget(self.prev_move_btn); nav.addWidget(self.view_ply,1); nav.addWidget(self.next_move_btn); lay.addLayout(nav)
        self.history=QLabel("MOSSE  ·  Nessuna mossa"); self.history.setObjectName("Muted"); self.history.setWordWrap(True); self.history.setMaximumHeight(48); lay.addWidget(self.history)
        self.eval_bar=QProgressBar(); self.eval_bar.setRange(0,1000); self.eval_bar.setValue(500)
        self.eval_bar.setTextVisible(True); self.eval_bar.setFormat("VALUTAZIONE · motore non configurato")
        self.eval_bar.setFixedHeight(19); lay.addWidget(self.eval_bar)
        self.engine_worker=None
        bottom=QHBoxLayout(); self.turn=QLabel(); self.turn.setObjectName("Muted"); bottom.addWidget(self.turn,1)
        self.result=QComboBox()
        for value,label in RESULT_OPTIONS: self.result.addItem(label,value)
        self.result.currentIndexChanged.connect(lambda i:self.app.set_result(self.game_id,self.result.itemData(i)))
        bottom.addWidget(self.result); lay.addLayout(bottom)
        controls=QHBoxLayout()
        self.undo=QPushButton("↶  Annulla mossa"); self.undo.clicked.connect(lambda:self.app.undo(self.game_id))
        pgn=QPushButton("Esporta PGN"); pgn.clicked.connect(lambda:self.app.export_pgn(self.game_id))
        reset=QPushButton("Reset"); reset.clicked.connect(lambda:self.app.reset_board(self.game_id))
        engine=QPushButton("STOCKFISH INTEGRATO"); engine.setEnabled(bool(self.app.find_engine()))
        self.clock_btn=QPushButton("AVVIA OROLOGIO"); self.clock_btn.clicked.connect(lambda:self.app.start_clock(self.game_id))
        self.rotate_btn=QPushButton("RUOTA"); self.rotate_btn.clicked.connect(self.board.toggle_orientation)
        self.theme_btn=QPushButton("TEMA SCACCHIERA"); self.theme_btn.clicked.connect(self.board.cycle_theme)
        notes=QPushButton("NOTA ARBITRO"); notes.clicked.connect(lambda:self.app.prompt_match_note(self.game_id))
        controls.addWidget(self.undo); controls.addWidget(self.clock_btn); controls.addStretch()
        controls.addWidget(self.rotate_btn); controls.addWidget(self.theme_btn); controls.addWidget(notes)
        controls.addWidget(engine); controls.addWidget(pgn); controls.addWidget(reset); lay.addLayout(controls)
        self.refresh()
    def refresh_selector(self):
        current = self.game_id
        self.selector.blockSignals(True)
        self.selector.clear()
        for gid, rnd, white, black in GAMES:
            self.selector.addItem(f"R{rnd} · {name(white)} – {name(black)}", gid)
        self.selector.setCurrentIndex(max(0, self.selector.findData(current)))
        self.selector.blockSignals(False)
    def select_game(self,i):
        value = self.selector.itemData(i)
        if value:
            self.game_id=value
            self.refresh()
    def move(self,uci):
        if self.history_index is not None and self.history_index < len(self.app.get_board(self.game_id).move_stack):
            self.app.statusBar().showMessage("Torna all'ultima posizione per continuare a giocare.",2500); return
        self.app.record_move(self.game_id,uci)
    def previous_move(self):
        full=self.app.get_board(self.game_id)
        self.history_index=max(0,(len(full.move_stack) if self.history_index is None else self.history_index)-1)
        self.refresh()
    def next_move(self):
        full=self.app.get_board(self.game_id)
        self.history_index=min(len(full.move_stack),(len(full.move_stack) if self.history_index is None else self.history_index)+1)
        self.refresh()
    def refresh_clock(self):
        self.clock_label.setText(self.app.clock_text(self.game_id))
        state=self.app.clock_data(self.game_id)
        self.clock_btn.setEnabled(not self.app.results.get(self.game_id) and not state.get("started"))
        self.clock_btn.setText("OROLOGIO IN CORSO" if state.get("started") else "AVVIA OROLOGIO")
    def update_evaluation(self, gid, board):
        path=self.app.engine_path or self.app.find_engine()
        if not path:
            self.eval_bar.setValue(500)
            self.eval_bar.setFormat("VALUTAZIONE · configura Stockfish per attivarla")
            return
        if self.engine_worker is not None and self.engine_worker.isRunning():
            self.pending_engine_position=(gid,board.copy(stack=True))
            return
        self.pending_engine_position=None
        self.eval_bar.setFormat("ANALISI STOCKFISH · profondità 12…")
        worker=EngineAnalysisWorker(path,gid,board,self)
        worker.analysisReady.connect(self.show_evaluation)
        worker.finished.connect(self.run_pending_evaluation)
        self.engine_worker=worker
        worker.start()
    def run_pending_evaluation(self):
        pending=getattr(self,"pending_engine_position",None)
        if pending:
            self.pending_engine_position=None
            self.update_evaluation(pending[0],pending[1])
    def show_evaluation(self, gid, score):
        if gid != self.game_id:
            return
        white_pct=1.0/(1.0+math.exp(-max(-4000,min(4000,score))/400.0))
        self.eval_bar.setValue(int(white_pct*1000))
        if score >= 10000:
            label="BIANCO · MATTO"
        elif score <= -10000:
            label="NERO · MATTO"
        elif score > 0:
            label=f"BIANCO +{score/100:.2f} · {white_pct*100:.0f}%"
        elif score < 0:
            label=f"NERO +{abs(score)/100:.2f} · {white_pct*100:.0f}%"
        else:
            label="PARI · 50%"
        self.eval_bar.setFormat(label)
    def refresh(self):
        self.refresh_selector()
        gid,r,w,b=game(self.game_id); board=self.app.get_board(gid)
        prior_ply=getattr(self,"known_ply",len(board.move_stack))
        if self.history_index is None or self.history_index==prior_ply:
            self.history_index=len(board.move_stack)
        self.history_index=min(self.history_index,len(board.move_stack))
        self.known_ply=len(board.move_stack)
        visible=chess.Board()
        for move in board.move_stack[:self.history_index]: visible.push(move)
        self.match.setText(f"{name(w)}  <span style='color:{GOLD}'>vs</span>  {name(b)}")
        self.turn.setText("PARTITA CONCLUSA · SCACCHIERA BLOCCATA" if self.app.results.get(gid) else
                          f"AL MUOVERE: {'BIANCO' if board.turn else 'NERO'} · {board.fullmove_number}ª mossa")
        self.board.set_position(visible,bool(self.app.results.get(gid)) or self.history_index<len(board.move_stack))
        self.update_evaluation(gid, board)
        self.view_ply.setText(f"{self.history_index} / {len(board.move_stack)}")
        self.prev_move_btn.setEnabled(self.history_index>0)
        self.next_move_btn.setEnabled(self.history_index<len(board.move_stack))
        self.refresh_clock()
        replay=chess.Board(); san=[]
        for mv in board.move_stack:
            prefix=f"{replay.fullmove_number}. " if replay.turn==chess.WHITE else f"{replay.fullmove_number}... "
            san.append(prefix+replay.san(mv)); replay.push(mv)
        self.history.setText("MOSSE  ·  "+("  ".join(san[-12:]) if san else "Nessuna mossa"))
        self.result.blockSignals(True); self.result.setCurrentIndex(max(0,self.result.findData(self.app.results.get(gid)))); self.result.blockSignals(False)
        self.undo.setEnabled(bool(board.move_stack) and not self.app.results.get(gid))

class SpectatorCard(QFrame):
    def __init__(self,label):
        super().__init__(); self.setObjectName("Card")
        lay=QVBoxLayout(self); self.tag=QLabel(label); self.tag.setObjectName("Eyebrow")
        self.match=QLabel(); self.match.setObjectName("MatchTitle")
        self.status=QLabel(); self.status.setObjectName("Muted")
        self.clock=QLabel(); self.clock.setObjectName("Muted")
        self.board=BoardWidget(False)
        lay.addWidget(self.tag); lay.addWidget(self.match); lay.addWidget(self.status); lay.addWidget(self.clock); lay.addWidget(self.board,1)
    def update_game(self,app,gid):
        _,r,w,b=game(gid); self.match.setText(f"{name(w)}  <span style='color:{GOLD}'>vs</span>  {name(b)}")
        result=app.results.get(gid); clock=app.clock_data(gid)
        self.status.setText("CONCLUSA" if result else ("IN CORSO" if clock.get("started") else "LIVE"))
        self.clock.setText(app.clock_text(gid))
        self.board.set_position(app.get_board(gid),True)

class BroadcastWindow(QWidget):
    def __init__(self,app):
        super().__init__(); self.app=app; self.setWindowTitle("C5R · Regia streaming")
        self.setStyleSheet(f"background:{BG};color:{TEXT};")
        root=QVBoxLayout(self); head=QHBoxLayout()
        logo=LogoWidget(100,110)
        live=QLabel("● LIVE  ·  VISTA SPETTATORE"); live.setStyleSheet(f"color:{GREEN};font-weight:900;")
        head.addWidget(logo); head.addStretch(); head.addWidget(live); root.addLayout(head)
        row=QHBoxLayout(); self.cards=[SpectatorCard("TAVOLO 01"),SpectatorCard("TAVOLO 02")]
        for c in self.cards: row.addWidget(c,1)
        root.addLayout(row,1); self.footer=QLabel(); self.footer.setStyleSheet(f"color:{GOLD};font-size:15px;font-weight:800;padding:10px;")
        root.addWidget(self.footer)
        self.refresh_from_app()
    def refresh_from_app(self):
        for c,live in zip(self.cards,self.app.live_cards): c.update_game(self.app,live.game_id)
        self.footer.setText("CLASSIFICA     "+"   •   ".join(f"{name(x['id'])} {x['points']:.1f} pt" for x in self.app.standings()))
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape: self.close()
        else: super().keyPressEvent(event)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Coppa dei 5 Re · Control Room")
        self.resize(1500,950); self.setMinimumSize(880,620)
        self.results={}; self.penalties=[]; self.moves={}; self.boards={}; self.broadcast=None; self.engine_path=None
        self._odds_cache_key=None; self._odds_cache=None
        self.time_control="15+3"; self.clocks={}; self.audit_log=[]; self.match_notes={}; self.referee=""
        self.tie_break="Nessuno"; self.playoff_results={}; self.eval_history={}; self.clock_ticks=0; self.board_theme=0
        self.load_state(); self.build_ui(); self.refresh_all()
        self.clock_timer=QTimer(self); self.clock_timer.timeout.connect(self.tick_clocks); self.clock_timer.start(1000)
        self.install_shortcuts()
    def load_state(self):
        path=storage_path()
        if path.exists():
            try:
                data=json.loads(path.read_text(encoding="utf-8"))
                self.results=data.get("results",{}); self.penalties=data.get("penalties",[]); self.moves=data.get("moves",{}); self.engine_path=data.get("engine_path")
                self.time_control=data.get("time_control","15+3"); self.clocks=data.get("clocks",{})
                self.audit_log=data.get("audit_log",[]); self.match_notes=data.get("match_notes",{})
                self.referee=data.get("referee",""); self.tie_break=data.get("tie_break","Nessuno")
                self.playoff_results=data.get("playoff_results",{}); self.playoff_winners=data.get("playoff_winners",{}); self.eval_history=data.get("eval_history",{})
                saved_schedule=data.get("schedule")
                if saved_schedule:
                    parsed=[(g["id"],int(g["round"]),g["white"],g["black"]) for g in saved_schedule]
                    if validate_schedule(parsed):
                        GAMES[:] = parsed
                        BYES.clear()
                        for rnd in range(1,6):
                            played=[p for g in GAMES if g[1]==rnd for p in (g[2],g[3])]
                            BYES[rnd]=next(p for p in ORDER if p not in played)
            except Exception: self.results={}; self.penalties=[]; self.moves={}
    def save(self):
        path=storage_path(); tmp=path.with_suffix(".tmp")
        stored_schedule=[{"id":gid,"round":rnd,"white":white,"black":black} for gid,rnd,white,black in GAMES]
        tmp.write_text(json.dumps({"results":self.results,"penalties":self.penalties,"moves":self.moves,
                                  "schedule":stored_schedule,"engine_path":self.engine_path,"time_control":self.time_control,
                                  "clocks":self.clocks,"audit_log":self.audit_log,"match_notes":self.match_notes,
                                  "referee":self.referee,"tie_break":self.tie_break,"playoff_results":self.playoff_results,
                                  "eval_history":self.eval_history,"playoff_winners":getattr(self,"playoff_winners",{}),"saved_at":datetime.now().isoformat(timespec="seconds")},ensure_ascii=False,indent=2),encoding="utf-8")
        tmp.replace(path)
    def find_engine(self):
        candidates=[]
        if self.engine_path:
            candidates.append(Path(self.engine_path))
        candidates.extend([
            Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent)) / "stockfish" / "stockfish.exe",
            Path(sys.executable).resolve().parent / "stockfish.exe",
            Path(__file__).resolve().parent / "stockfish.exe",
            storage_path().parent / "stockfish.exe",
        ])
        found=shutil.which("stockfish")
        if found:
            candidates.insert(0,Path(found))
        for candidate in candidates:
            if candidate.is_file():
                self.engine_path=str(candidate)
                return self.engine_path
        return None
    def choose_engine(self):
        path,_=QFileDialog.getOpenFileName(self,"Seleziona motore Stockfish","","Programmi (*.exe);;Tutti i file (*)")
        if path:
            self.engine_path=path
            self.save()
            self.refresh_all()
            self.statusBar().showMessage("Stockfish configurato: valutazione attiva sulle scacchiere.",4000)
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
        if self.results.get(gid):
            self.statusBar().showMessage("Partita conclusa: rimuovi il risultato prima di continuare.",3500); return
        b=self.get_board(gid)
        try:
            move=chess.Move.from_uci(uci)
            if move not in b.legal_moves:
                self.statusBar().showMessage("Mossa illegale: non registrata.",3000); return
            mover="white" if b.turn else "black"
            clock=self.clock_data(gid)
            b.push(move)
            if clock.get("started"): clock[mover]+=self.increment_seconds()
            self.moves[gid]=[x.uci() for x in b.move_stack]
            self.log_operation("Mossa",gid,"",uci)
            outcome=b.outcome(claim_draw=True)
            if outcome is not None:
                clock["started"]=False
                self.set_result(gid,b.result(claim_draw=True),confirm=False,
                    detail=outcome.termination.name.replace("_"," ").lower())
                self.statusBar().showMessage("Partita terminata automaticamente: "+outcome.termination.name.replace("_"," ").lower(),5000)
            self.save(); self.refresh_all()
        except Exception as exc:
            self.statusBar().showMessage(f"Mossa non registrata: {exc}",4000)
    def undo(self,gid):
        b=self.get_board(gid)
        if b.move_stack and not self.results.get(gid):
            b.pop(); self.moves[gid]=[x.uci() for x in b.move_stack]; self.save(); self.refresh_all()
    def reset_board(self,gid):
        if QMessageBox.question(self,"Reset","Cancellare tutte le mosse di questa partita?")==QMessageBox.StandardButton.Yes:
            self.boards[gid]=chess.Board(); self.moves[gid]=[]; self.clocks.pop(gid,None); self.save(); self.refresh_all()
    def set_result(self,gid,value,confirm=True,detail="inserimento manuale"):
        old=self.results.get(gid)
        if old==value: return
        if old is not None and confirm:
            answer=QMessageBox.question(self,"Conferma modifica risultato",
                f"La partita {gid} ha già risultato {old}. Vuoi sostituirlo con {value or 'In corso'}?",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:
                self.refresh_all(); return
        if value is None: self.results.pop(gid,None)
        else:
            self.results[gid]=value
            self.clock_data(gid)["started"]=False
        self.log_operation("Risultato",gid,old or "In corso",value or "In corso",detail)
        self.save(); self.refresh_all()
        self.statusBar().showMessage("Risultato salvato · classifica e quote aggiornate.",3000)
    def clock_data(self,gid):
        if gid not in self.clocks:
            base,_=self.time_control.split("+"); seconds=int(base)*60
            self.clocks[gid]={"white":seconds,"black":seconds,"started":False}
        else:
            base,_=self.time_control.split("+"); seconds=int(base)*60
            self.clocks[gid].setdefault("white",seconds)
            self.clocks[gid].setdefault("black",seconds)
            self.clocks[gid].setdefault("started",False)
        return self.clocks[gid]
    def increment_seconds(self):
        return int(self.time_control.split("+")[1])
    def clock_text(self,gid):
        c=self.clock_data(gid)
        def fmt(v):
            v=max(0,int(v)); return f"{v//60:02d}:{v%60:02d}"
        return f"BIANCO {fmt(c['white'])}   ·   NERO {fmt(c['black'])}"
    def start_clock(self,gid):
        if self.results.get(gid): return
        self.clock_data(gid)["started"]=True
        self.save(); self.refresh_all()
        self.statusBar().showMessage("Cronometro avviato.",2000)
    def set_time_control(self,value):
        if value==self.time_control: return
        if self.results or any(self.moves.values()) or any(c.get("started") for c in self.clocks.values()):
            QMessageBox.information(self,"Tempo di gioco","Il controllo del tempo si può cambiare solo prima di iniziare il girone.")
            self.live_time.blockSignals(True)
            self.live_time.setCurrentText(self.time_control)
            self.live_time.blockSignals(False)
            return
        self.time_control=value; self.clocks={}
        self.save(); self.refresh_all()
    def tick_clocks(self):
        changed=False; timed_out=[]
        for gid,_,white,black in GAMES:
            clock=self.clock_data(gid)
            if not clock.get("started") or self.results.get(gid): continue
            side="white" if self.get_board(gid).turn else "black"
            clock[side]=max(0,int(clock[side])-1); changed=True
            if clock[side]<=0:
                timed_out.append((gid,"0-1" if side=="white" else "1-0"))
        for gid,result in timed_out:
            self.clock_data(gid)["started"]=False
            board=self.get_board(gid)
            flagged_side=chess.WHITE if result=="0-1" else chess.BLACK
            opponent=not flagged_side
            if board.has_insufficient_material(opponent):
                result="1/2-1/2"
            self.set_result(gid,result,confirm=False,detail="tempo scaduto")
        if changed:
            self.clock_ticks+=1
            for card in getattr(self,"live_cards",[]): card.refresh_clock()
            if self.broadcast and self.broadcast.isVisible(): self.broadcast.refresh_from_app()
            if self.clock_ticks%5==0: self.save()
    def log_operation(self,action,entity,before,after,detail=""):
        self.audit_log.append({"time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "referee":self.referee,"action":action,"entity":str(entity),
            "before":str(before),"after":str(after),"detail":str(detail)})
        self._odds_cache_key=None
    def add_match_note(self,gid,text,kind="Nota"):
        text=text.strip()
        if not text: return
        self.match_notes.setdefault(gid,[]).append({"time":datetime.now().strftime("%d/%m/%Y %H:%M"),
            "referee":self.referee,"kind":kind,"text":text})
        self.log_operation(kind,gid,"",text)
        self.save(); self.statusBar().showMessage("Annotazione arbitrale salvata.",2500)
    def prompt_match_note(self,gid):
        text,ok=QInputDialog.getMultiLineText(self,"Nota / incidente",
            f"Partita {gid} · arbitro: {self.referee or 'non indicato'}","")
        if ok: self.add_match_note(gid,text,"Incidente" if "incidente" in text.lower() else "Nota")
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
    def tie_break_value(self,p,group=None):
        raw,played,wins,draws,losses=self.raw_stats()
        selected=set(group or PLAYERS.keys())
        if self.tie_break=="Numero vittorie": return wins[p]
        value=0.0
        for gid,r,white,black in GAMES:
            result=self.results.get(gid)
            if not result or p not in (white,black): continue
            opponent=black if p==white else white
            if self.tie_break=="Scontro diretto" and opponent not in selected: continue
            score=1.0 if (result=="1-0" and p==white) or (result=="0-1" and p==black) else (0.5 if result=="1/2-1/2" else 0.0)
            if self.tie_break=="Scontro diretto": value+=score
            elif self.tie_break=="Sonneborn-Berger": value+=raw[opponent]*score
            elif self.tie_break=="Buchholz": value+=raw[opponent]
            
        return value
    def standings(self):
        pts,played,wins,draws,losses=self.raw_stats(); pen=self.penalty_points()
        rows=[{"id":p,"played":played[p],"wins":wins[p],"draws":draws[p],"losses":losses[p],
               "penalty":pen[p],"points":pts[p]+pen[p]} for p in PLAYERS]
        grouped={}
        for row in rows: grouped.setdefault(row["points"],[]).append(row)
        ordered=[]
        for points in sorted(grouped,reverse=True):
            group=grouped[points]
            group_ids=[row["id"] for row in group]
            group.sort(key=lambda row:(-self.tie_break_value(row["id"],group_ids),ORDER.index(row["id"])))
            ordered.extend(group)
        return ordered
    def odds(self,n=15000):
        raw,played,_,_,_=self.raw_stats(); pen=self.penalty_points()
        current={p:raw[p]+pen[p] for p in PLAYERS}
        form={p:(raw[p]+1.0)/(played[p]+2.0) for p in PLAYERS}
        remaining=[g for g in GAMES if not self.results.get(g[0])]
        win={p:0.0 for p in PLAYERS}; top={p:0.0 for p in PLAYERS}
        seed_payload=json.dumps({"results":self.results,"penalties":self.penalties,
                                 "schedule":GAMES},sort_keys=True,ensure_ascii=False,default=str)
        digest=hashlib.sha256(seed_payload.encode("utf-8")).digest()
        cache_key=(n,digest)
        if cache_key==self._odds_cache_key and self._odds_cache is not None:
            return self._odds_cache.copy()
        seed=int.from_bytes(digest[:8],"big")
        rng=random.Random(seed)
        for _ in range(n):
            score=current.copy()
            for gid,r,w,b in remaining:
                base_white, base_black, (pw,pd,pb)=PAIR_PRIORS[frozenset((w,b))]
                if w != base_white:
                    pw, pb = pb, pw
                shift=max(-.18,min(.18,.20*(form[w]-form[b])))
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
        output={p:(win[p]/n,top[p]/n) for p in PLAYERS}
        self._odds_cache_key=cache_key
        self._odds_cache=output
        return output.copy()
    def build_ui(self):
        root=QWidget(); outer=QVBoxLayout(root); outer.setContentsMargins(22,18,22,16); outer.setSpacing(14)
        header=QHBoxLayout(); logo=LogoWidget(76,82)
        header.addWidget(logo); texts=QVBoxLayout()
        title=QLabel("COPPA DEI 5 RE"); title.setObjectName("BrandTitle")
        sub=QLabel("CONTROL ROOM  ·  TOURNAMENT EDITION"); sub.setObjectName("Eyebrow")
        texts.addWidget(title); texts.addWidget(sub); header.addLayout(texts); header.addStretch()
        saved=QLabel("●  OFFLINE  ·  SALVATAGGIO AUTOMATICO"); saved.setObjectName("SavedBadge"); header.addWidget(saved)
        time_label=QLabel("TEMPO"); time_label.setObjectName("Eyebrow"); header.addWidget(time_label)
        self.live_time=QComboBox(); self.live_time.addItems(["15+3","30+10"])
        self.live_time.setCurrentText(self.time_control); self.live_time.currentTextChanged.connect(self.set_time_control)
        header.addWidget(self.live_time)
        stream=QPushButton("◉  VISTA STREAMING"); stream.setObjectName("PrimaryButton"); stream.clicked.connect(self.open_broadcast); header.addWidget(stream)
        outer.addLayout(header)
        workspace=QHBoxLayout(); workspace.setSpacing(12)
        self.nav=QListWidget(); self.nav.setObjectName("Sidebar"); self.nav.setFixedWidth(190)
        nav_items=["◈  DASHBOARD","♟  LIVE ARENA","♜  ESTRAZIONE","▦  CALENDARIO","☷  CLASSIFICA",
                   "◉  QUOTE","⚑  PENALITÀ","♛  PLAYOFF","▤  ARCHIVIO","⇄  TESTA A TESTA",
                   "☷  REGISTRO","⚙  IMPOSTAZIONI"]
        self.nav.addItems(nav_items)
        self.tabs=QStackedWidget()
        pages=[self.build_dashboard(),self.build_live(),self.build_draw_page(),self.build_calendar(),
               self.build_standings(),self.build_odds(),self.build_penalties(),self.build_playoffs(),
               self.build_archive(),self.build_h2h(),self.build_audit(),self.build_settings()]
        for page in pages: self.tabs.addWidget(page)
        self.nav.currentRowChanged.connect(self.tabs.setCurrentIndex)
        self.nav.setCurrentRow(0)
        workspace.addWidget(self.nav); workspace.addWidget(self.tabs,1)
        outer.addLayout(workspace,1)
        foot=QLabel("COPPA DEI 5 RE  /  DAL 15 NOVEMBRE 2026  /  DATI LOCALI SU QUESTO PC"); foot.setObjectName("Footnote")
        outer.addWidget(foot); self.setCentralWidget(root)
        self.statusBar().showMessage("Pronto · seleziona un pezzo e poi la casa di destinazione.")
    def build_dashboard(self):
        page=QWidget(); root=QVBoxLayout(page)
        hero=QFrame(); hero.setObjectName("Card"); hl=QHBoxLayout(hero)
        crown=LogoWidget(170,190)
        title=QLabel("<span style='font-size:27px;font-weight:900;color:#EEF1F5'>C5R · COPPA DEI 5 RE</span><br><span style='color:#D8B36A;letter-spacing:3px'>CHESS TOURNAMENT CONTROL ROOM</span>")
        title.setTextFormat(Qt.TextFormat.RichText)
        hl.addWidget(crown); hl.addWidget(title,1); root.addWidget(hero)
        self.dashboard_summary=QLabel(); self.dashboard_summary.setObjectName("SectionTitle"); root.addWidget(self.dashboard_summary)
        self.dashboard_detail=QLabel(); self.dashboard_detail.setObjectName("Muted"); root.addWidget(self.dashboard_detail)
        actions=QGridLayout()
        items=[("ESPORTA PGN TORNEO",self.export_all_pgn),("CLASSIFICA CSV",self.export_standings_csv),
               ("CLASSIFICA PDF",self.export_standings_pdf),("BACKUP DATI",self.export_backup),
               ("RIPRISTINA BACKUP",self.restore_backup)]
        for i,(label,callback) in enumerate(items):
            button=QPushButton(label); button.setObjectName("PrimaryButton" if i==0 else "")
            button.clicked.connect(callback); actions.addWidget(button,i//3,i%3)
        root.addLayout(actions)
        tip=QLabel("Usa LIVE ARENA per giocare, CALENDARIO per registrare i risultati e ARCHIVIO per consultare le partite concluse.")
        tip.setObjectName("Muted"); tip.setWordWrap(True); root.addWidget(tip); root.addStretch()
        return page

    def build_archive(self):
        page=QWidget(); layout=QVBoxLayout(page)
        title=QLabel("ARCHIVIO PARTITE"); title.setObjectName("SectionTitle"); layout.addWidget(title)
        self.archive_table=QTableWidget(0,6)
        self.archive_table.setHorizontalHeaderLabels(["TURNO","PARTITA","BIANCO","NERO","RISULTATO","MOSSE / NOTE"])
        self.archive_table.verticalHeader().setVisible(False)
        self.archive_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.archive_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.archive_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.archive_table,1)
        row=QHBoxLayout(); allpgn=QPushButton("ESPORTA TUTTO IL TORNEO IN PGN")
        allpgn.setObjectName("PrimaryButton"); allpgn.clicked.connect(self.export_all_pgn); row.addWidget(allpgn)
        one=QPushButton("ESPORTA PARTITA SELEZIONATA")
        one.clicked.connect(self.export_selected_archive_game); row.addWidget(one); row.addStretch()
        layout.addLayout(row); return page

    def build_h2h(self):
        page=QWidget(); layout=QVBoxLayout(page)
        title=QLabel("STATISTICHE TESTA A TESTA"); title.setObjectName("SectionTitle"); layout.addWidget(title)
        desc=QLabel("Vittorie-pareggi-sconfitte per il giocatore indicato sulla riga rispetto a quello indicato nella colonna.")
        desc.setObjectName("Muted"); desc.setWordWrap(True); layout.addWidget(desc)
        self.h2h_table=QTableWidget(5,6)
        self.h2h_table.setHorizontalHeaderLabels(["GIOCATORE"]+[name(p) for p in ORDER])
        self.h2h_table.verticalHeader().setVisible(False)
        self.h2h_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.h2h_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for c in range(1,6): self.h2h_table.horizontalHeader().setSectionResizeMode(c,QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.h2h_table,1); return page

    def build_audit(self):
        page=QWidget(); layout=QVBoxLayout(page)
        title=QLabel("REGISTRO OPERAZIONI E ARBITRAGGIO"); title.setObjectName("SectionTitle"); layout.addWidget(title)
        self.audit_table=QTableWidget(0,7)
        self.audit_table.setHorizontalHeaderLabels(["DATA/ORA","ARBITRO","AZIONE","OGGETTO","PRIMA","DOPO","DETTAGLI"])
        self.audit_table.verticalHeader().setVisible(False)
        self.audit_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.audit_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.audit_table.horizontalHeader().setSectionResizeMode(6,QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.audit_table,1)
        export=QPushButton("ESPORTA REGISTRO CSV"); export.clicked.connect(self.export_audit_csv)
        layout.addWidget(export,0,Qt.AlignmentFlag.AlignRight); return page

    def build_settings(self):
        page=QWidget(); layout=QVBoxLayout(page)
        title=QLabel("IMPOSTAZIONI TORNEO"); title.setObjectName("SectionTitle"); layout.addWidget(title)
        card=QFrame(); card.setObjectName("Card"); grid=QGridLayout(card)
        grid.addWidget(QLabel("ARBITRO"),0,0)
        self.referee_input=QLineEdit(self.referee); self.referee_input.setPlaceholderText("Nome arbitro / direttore di gara")
        grid.addWidget(self.referee_input,0,1)
        grid.addWidget(QLabel("CRITERIO DI SPAREGGIO"),1,0)
        self.tie_break_combo=QComboBox()
        self.tie_break_combo.addItems(["Nessuno","Scontro diretto","Sonneborn-Berger","Buchholz","Numero vittorie"])
        self.tie_break_combo.setCurrentText(self.tie_break if self.tie_break in ["Nessuno","Scontro diretto","Sonneborn-Berger","Buchholz","Numero vittorie"] else "Nessuno")
        grid.addWidget(self.tie_break_combo,1,1)
        save=QPushButton("SALVA IMPOSTAZIONI"); save.setObjectName("PrimaryButton"); save.clicked.connect(self.save_settings)
        grid.addWidget(save,2,1); layout.addWidget(card)
        desc=QLabel("Il criterio selezionato viene applicato soltanto in caso di pari punti. Con “Nessuno” gli ex aequo restano tali.")
        desc.setObjectName("Muted"); desc.setWordWrap(True); layout.addWidget(desc)
        layout.addStretch(); return page

    def save_settings(self):
        self.referee=self.referee_input.text().strip()
        self.tie_break=self.tie_break_combo.currentText()
        self.log_operation("Impostazioni torneo","","",f"arbitro={self.referee}; spareggio={self.tie_break}")
        self.save(); self.refresh_all()
        self.statusBar().showMessage("Impostazioni torneo salvate.",2500)

    def install_shortcuts(self):
        shortcuts=[("Ctrl+S",self.save),("Ctrl+E",self.export_all_pgn),
                   ("Ctrl+Shift+B",self.export_backup),("Ctrl+1",lambda:self.tabs.setCurrentIndex(1)),
                   ("Ctrl+2",lambda:self.tabs.setCurrentIndex(2)),("Ctrl+3",lambda:self.tabs.setCurrentIndex(3))]
        self.shortcuts=[]
        for key,callback in shortcuts:
            shortcut=QShortcut(QKeySequence(key),self)
            shortcut.activated.connect(callback); self.shortcuts.append(shortcut)

    def refresh_dashboard(self):
        if not hasattr(self,"dashboard_summary"): return
        done=len(self.results); running=sum(1 for gid,_,_,_ in GAMES if self.clock_data(gid).get("started"))
        self.dashboard_summary.setText(f"PARTITE CONCLUSE  {done}/10     ·     IN CORSO  {running}     ·     CONTROLLO {self.time_control}")
        leader=self.standings()[0]
        self.dashboard_detail.setText(f"LEADER ATTUALE  ·  {name(leader['id'])}  ·  {leader['points']:.1f} punti     |     ARBITRO  ·  {self.referee or 'non impostato'}")

    def refresh_archive(self):
        if not hasattr(self,"archive_table"): return
        finished=[g for g in GAMES if self.results.get(g[0])]
        self.archive_table.setRowCount(len(finished))
        for row,(gid,rnd,white,black) in enumerate(finished):
            values=[f"ROUND {rnd}",gid,name(white),name(black),self.results[gid],
                    f"{len(self.moves.get(gid,[]))} mosse · {len(self.match_notes.get(gid,[]))} note"]
            for col,value in enumerate(values):
                item=QTableWidgetItem(value); item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.archive_table.setItem(row,col,item)

    def refresh_h2h(self):
        if not hasattr(self,"h2h_table"): return
        for row,p in enumerate(ORDER):
            self.h2h_table.setItem(row,0,QTableWidgetItem(name(p)))
            for col,opponent in enumerate(ORDER,1):
                if p==opponent:
                    self.h2h_table.setItem(row,col,QTableWidgetItem("—")); continue
                wins=draws=losses=0
                for gid,rnd,w,b in GAMES:
                    if frozenset((w,b))!=frozenset((p,opponent)): continue
                    result=self.results.get(gid)
                    if not result: continue
                    score=1 if (result=="1-0" and p==w) or (result=="0-1" and p==b) else (.5 if result=="1/2-1/2" else 0)
                    if score==1: wins+=1
                    elif score==.5: draws+=1
                    else: losses+=1
                self.h2h_table.setItem(row,col,QTableWidgetItem(f"{wins}–{draws}–{losses}"))

    def refresh_audit(self):
        if not hasattr(self,"audit_table"): return
        entries=list(reversed(self.audit_log))
        self.audit_table.setRowCount(len(entries))
        for row,entry in enumerate(entries):
            vals=[entry.get("time",""),entry.get("referee",""),entry.get("action",""),
                  entry.get("entity",""),entry.get("before",""),entry.get("after",""),entry.get("detail","")]
            for col,value in enumerate(vals):
                self.audit_table.setItem(row,col,QTableWidgetItem(str(value)))

    def export_all_pgn(self):
        path,_=QFileDialog.getSaveFileName(self,"Esporta tutte le partite","Coppa5Re-Torneo.pgn","PGN (*.pgn)")
        if not path: return
        chunks=[]
        for gid,rnd,white,black in GAMES:
            node=chess.pgn.Game.from_board(self.get_board(gid))
            node.headers["Event"]=APP_NAME; node.headers["Round"]=str(rnd)
            node.headers["White"]=name(white); node.headers["Black"]=name(black)
            node.headers["Result"]=self.results.get(gid,"*"); node.headers["Site"]="Coppa dei 5 Re"
            chunks.append(node.accept(chess.pgn.StringExporter(headers=True,variations=False,comments=False)))
        Path(path).write_text("\\n\\n".join(chunks)+"\\n",encoding="utf-8")
        self.statusBar().showMessage("Archivio PGN esportato.",3000)

    def export_selected_archive_game(self):
        row=self.archive_table.currentRow()
        if row<0: return
        finished=[g for g in GAMES if self.results.get(g[0])]
        if row<len(finished): self.export_pgn(finished[row][0])

    def export_standings_csv(self):
        path,_=QFileDialog.getSaveFileName(self,"Esporta classifica","Classifica-C5R.csv","CSV (*.csv)")
        if not path: return
        with open(path,"w",newline="",encoding="utf-8-sig") as file:
            writer=csv.writer(file,delimiter=";")
            writer.writerow(["Posizione","Giocatore","Partite","Vittorie","Patte","Sconfitte","Penalità","Punti","Spareggio"])
            for position,row in enumerate(self.standings(),1):
                writer.writerow([position,name(row["id"]),row["played"],row["wins"],row["draws"],row["losses"],
                    row["penalty"],row["points"],self.tie_break_value(row["id"])])
        self.statusBar().showMessage("Classifica CSV esportata.",2500)

    def export_standings_pdf(self):
        path,_=QFileDialog.getSaveFileName(self,"Esporta classifica PDF","Classifica-C5R.pdf","PDF (*.pdf)")
        if not path: return
        writer=QPdfWriter(path); writer.setTitle("Classifica Coppa dei 5 Re"); writer.setResolution(150)
        painter=QPainter(writer)
        try:
            painter.setPen(QColor(GOLD)); painter.setFont(QFont("Segoe UI",22,QFont.Weight.Bold))
            painter.drawText(180,220,"COPPA DEI 5 RE")
            painter.setPen(QColor("#222222")); painter.setFont(QFont("Segoe UI",11))
            painter.drawText(180,300,"CLASSIFICA GENERALE")
            painter.drawText(180,360,f"Tempo: {self.time_control}    Spareggio: {self.tie_break}")
            y=470
            painter.setFont(QFont("Segoe UI",9,QFont.Weight.Bold))
            painter.drawText(180,y,"POS   GIOCATORE   G   V   X   P   PEN.   PT"); y+=65
            painter.setFont(QFont("Segoe UI",10))
            for i,row in enumerate(self.standings(),1):
                values=[str(i),name(row["id"]),str(row["played"]),str(row["wins"]),str(row["draws"]),
                        str(row["losses"]),f"{row['penalty']:+.1f}",f"{row['points']:.1f}"]
                painter.drawText(180,y,"      ".join(values)); y+=58
        finally:
            painter.end()
        self.statusBar().showMessage("Classifica PDF esportata.",2500)

    def export_audit_csv(self):
        path,_=QFileDialog.getSaveFileName(self,"Esporta registro","Registro-C5R.csv","CSV (*.csv)")
        if not path: return
        with open(path,"w",newline="",encoding="utf-8-sig") as file:
            writer=csv.writer(file,delimiter=";")
            writer.writerow(["Data","Arbitro","Azione","Oggetto","Prima","Dopo","Dettagli"])
            for e in self.audit_log:
                writer.writerow([e.get(k,"") for k in ("time","referee","action","entity","before","after","detail")])
        self.statusBar().showMessage("Registro operazioni esportato.",2500)

    def export_backup(self):
        self.save()
        path,_=QFileDialog.getSaveFileName(self,"Backup torneo","Backup-C5R.json","JSON (*.json)")
        if path:
            shutil.copy2(storage_path(),path)
            self.statusBar().showMessage("Backup completo salvato.",2500)

    def restore_backup(self):
        path,_=QFileDialog.getOpenFileName(self,"Ripristina backup","","Backup torneo (*.json)")
        if not path: return
        try:
            data=json.loads(Path(path).read_text(encoding="utf-8"))
            if data.get("schedule"):
                schedule=[(g["id"],int(g["round"]),g["white"],g["black"]) for g in data["schedule"]]
                validate_schedule(schedule)
            answer=QMessageBox.question(self,"Ripristina backup",
                "I dati attuali verranno sostituiti dal backup selezionato. Continuare?",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes: return
            shutil.copy2(path,storage_path())
            self.boards.clear(); self._odds_cache_key=None; self._odds_cache=None
            self.results={}; self.penalties=[]; self.moves={}; self.clocks={}; self.audit_log=[]; self.match_notes={}
            self.load_state(); self.refresh_all()
            self.statusBar().showMessage("Backup ripristinato.",3000)
        except Exception as exc:
            QMessageBox.critical(self,"Backup non valido",f"Impossibile ripristinare il backup: {exc}")

    def build_live(self):
        page=QWidget(); l=QHBoxLayout(page); l.setContentsMargins(0,14,0,0); l.setSpacing(14)
        self.live_cards=[BoardCard(self,1,"R1-M1"),BoardCard(self,2,"R1-M2")]
        for c in self.live_cards: l.addWidget(c,1)
        return page
    def build_draw_page(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.setSpacing(12)
        title=QLabel("ESTRAZIONE DEL GIRONE"); title.setObjectName("SectionTitle"); layout.addWidget(title)
        desc=QLabel("Il sorteggio crea un round-robin completo: 5 turni, 2 partite per turno e un riposo a turno. Ogni coppia si incontra una sola volta e ogni giocatore riposa una volta.")
        desc.setObjectName("Muted"); desc.setWordWrap(True); layout.addWidget(desc)
        controls=QHBoxLayout()
        draw=QPushButton("♜  ESTRAZIONE RANDOM"); draw.setObjectName("PrimaryButton"); draw.clicked.connect(self.random_draw)
        edit=QPushButton("MODIFICA GIRONE"); edit.clicked.connect(self.open_schedule_editor)
        reset=QPushButton("RIPRISTINA CALENDARIO"); reset.clicked.connect(self.reset_schedule)
        controls.addWidget(draw); controls.addWidget(edit); controls.addStretch(); controls.addWidget(reset)
        layout.addLayout(controls)
        self.draw_table=QTableWidget(5,4); self.draw_table.setHorizontalHeaderLabels(["TURNO","TAVOLO 1","TAVOLO 2","RIPOSA"])
        self.draw_table.verticalHeader().setVisible(False); self.draw_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.draw_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.draw_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        for col in (1,2,3): self.draw_table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.Stretch)
        self.draw_table.setMinimumHeight(320); layout.addWidget(self.draw_table)
        note=QLabel("Nota: applicare un nuovo sorteggio o cambiare gli accoppiamenti azzera gli eventuali risultati e le mosse già registrate, dopo una richiesta di conferma. Le penalità restano associate ai giocatori.")
        note.setObjectName("Muted"); note.setWordWrap(True); layout.addWidget(note)
        self.refresh_draw_page()
        return page

    def refresh_draw_page(self):
        if not hasattr(self,"draw_table"): return
        self.draw_table.setRowCount(5)
        for rnd in range(1,6):
            matches=sorted([g for g in GAMES if g[1]==rnd],key=lambda g:g[0])
            values=[f"ROUND {rnd}",
                    f"{name(matches[0][2])}  vs  {name(matches[0][3])}",
                    f"{name(matches[1][2])}  vs  {name(matches[1][3])}",
                    name(BYES[rnd])]
            for col,value in enumerate(values):
                item=QTableWidgetItem(value); item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col==0 or col==3: item.setForeground(QColor(GOLD))
                self.draw_table.setItem(rnd-1,col,item)

    def apply_schedule(self, proposed):
        proposed=[tuple(g) for g in proposed]
        try:
            validate_schedule(proposed)
        except ValueError as exc:
            QMessageBox.warning(self,"Calendario non valido",str(exc)); return False
        if proposed==GAMES:
            self.statusBar().showMessage("Il girone non è cambiato.",2500); return False
        if self.results or any(self.moves.values()):
            answer=QMessageBox.question(self,"Sostituire il girone?",
                "Ci sono già risultati o mosse registrate. Cambiare il calendario cancellerà risultati e mosse per evitare di attribuirli alle partite sbagliate. Continuare?",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes: return False
            self.results.clear(); self.moves.clear(); self.boards.clear()
        GAMES[:]=proposed
        BYES.clear()
        for rnd in range(1,6):
            played=[p for g in GAMES if g[1]==rnd for p in (g[2],g[3])]
            BYES[rnd]=next(p for p in ORDER if p not in played)
        self.save(); self.refresh_all()
        self.statusBar().showMessage("Girone aggiornato e salvato sul PC.",3500)
        return True

    def random_draw(self):
        proposed=make_random_schedule()
        if self.apply_schedule(proposed):
            self.statusBar().showMessage("Estrazione completata: nuovi accoppiamenti, colori e turni di riposo sorteggiati.",4500)

    def open_schedule_editor(self):
        dialog=ScheduleEditorDialog(GAMES,self)
        if dialog.exec()==QDialog.DialogCode.Accepted and dialog.schedule:
            self.apply_schedule(dialog.schedule)

    def reset_schedule(self):
        self.apply_schedule(DEFAULT_GAMES)

    def build_calendar(self):
        page=QWidget(); l=QVBoxLayout(page)
        h=QLabel("PROGRAMMA E RISULTATI"); h.setObjectName("SectionTitle"); l.addWidget(h)
        d=QLabel("Calendario round-robin già caricato. Ogni risultato aggiorna immediatamente classifica e simulazioni quote.")
        d.setObjectName("Muted"); l.addWidget(d)
        filters=QHBoxLayout()
        self.filter_round=QComboBox(); self.filter_round.addItems(["Tutti i turni"]+[f"Round {r}" for r in range(1,6)])
        self.filter_player=QComboBox(); self.filter_player.addItem("Tutti i giocatori",None)
        for pid in ORDER: self.filter_player.addItem(name(pid),pid)
        self.filter_status=QComboBox(); self.filter_status.addItems(["Tutti gli stati","In corso","Concluse"])
        for control in (self.filter_round,self.filter_player,self.filter_status):
            control.currentIndexChanged.connect(self.apply_calendar_filters); filters.addWidget(control)
        l.addLayout(filters)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        content=QWidget(); v=QVBoxLayout(content); self.calendar_combos={}; self.calendar_pairings={}; self.calendar_bye_labels={}; self.calendar_cards={}
        for gid,r,w,b in GAMES:
            card=QFrame(); card.setObjectName("Card"); row=QHBoxLayout(card)
            tag=QLabel(f"ROUND {r}"); tag.setObjectName("Eyebrow"); tag.setFixedWidth(85)
            matchup=QLabel(f"{name(w)}  <span style='color:{GOLD}'>vs</span>  {name(b)}"); matchup.setObjectName("MatchTitle")
            self.calendar_pairings[gid]=matchup; self.calendar_cards[gid]=card
            combo=QComboBox()
            for val,label in RESULT_OPTIONS: combo.addItem(label,val)
            combo.currentIndexChanged.connect(lambda i,gid=gid,cb=combo:self.set_result(gid,cb.itemData(i)))
            self.calendar_combos[gid]=combo; row.addWidget(tag); row.addWidget(matchup,1); row.addWidget(combo); v.addWidget(card)
        for r,p in BYES.items():
            bye=QLabel(f"ROUND {r}  ·  Riposa: {name(p)}  ·  BYE"); bye.setObjectName("Muted")
            self.calendar_bye_labels[r]=bye; v.addWidget(bye)
        v.addStretch(); scroll.setWidget(content); l.addWidget(scroll,1); return page
    def apply_calendar_filters(self):
        if not hasattr(self,"calendar_cards"): return
        rnd_text=self.filter_round.currentText()
        selected_player=self.filter_player.currentData()
        state=self.filter_status.currentText()
        for gid,card in self.calendar_cards.items():
            _,rnd,white,black=game(gid)
            matches_round=(rnd_text=="Tutti i turni" or rnd_text==f"Round {rnd}")
            matches_player=(selected_player is None or selected_player in (white,black))
            completed=bool(self.results.get(gid))
            matches_state=(state=="Tutti gli stati" or (state=="Concluse" and completed) or (state=="In corso" and not completed))
            card.setVisible(matches_round and matches_player and matches_state)
        if hasattr(self,"calendar_bye_labels"):
            for rnd,label in self.calendar_bye_labels.items():
                label.setVisible(rnd_text=="Tutti i turni" or rnd_text==f"Round {rnd}")

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
        row=QHBoxLayout(); row.addStretch()
        edit=QPushButton("Modifica selezionata"); edit.clicked.connect(self.edit_penalty); row.addWidget(edit)
        rem=QPushButton("Annulla voce selezionata"); rem.clicked.connect(self.remove_penalty); row.addWidget(rem); l.addLayout(row)
        return page
    def bracket_card(self,title,a,b):
        f=QFrame(); f.setObjectName("Card"); v=QVBoxLayout(f)
        h=QLabel(title); h.setObjectName("Eyebrow"); x=QLabel(a); x.setObjectName("MatchTitle"); y=QLabel(b); y.setObjectName("MatchTitle")
        v.addWidget(h); v.addWidget(x); v.addWidget(y); f.labels=(h,x,y); return f
    def build_playoffs(self):
        page=QWidget(); l=QVBoxLayout(page)
        h=QLabel("TABELLONE PLAYOFF"); h.setObjectName("SectionTitle"); l.addWidget(h)
        d=QLabel("Semifinali 1ª–4ª e 2ª–3ª, finale e finale 3°/4° posto. I risultati sono indipendenti dal girone e si possono correggere dal tabellone.")
        d.setObjectName("Muted"); d.setWordWrap(True); l.addWidget(d)
        grid=QGridLayout(); self.sf1=self.bracket_card("SEMIFINALE 1","1ª classificata","4ª classificata")
        self.sf2=self.bracket_card("SEMIFINALE 2","2ª classificata","3ª classificata")
        self.final=self.bracket_card("FINALE","Vincente SF1","Vincente SF2")
        self.third=self.bracket_card("3° / 4° POSTO","Perdente SF1","Perdente SF2")
        self.playoff_cards={"sf1":self.sf1,"sf2":self.sf2,"final":self.final,"third":self.third}
        self.playoff_winners=getattr(self,"playoff_winners",{})
        for key,card in self.playoff_cards.items():
            card.result_box=QComboBox()
            for value,label in RESULT_OPTIONS: card.result_box.addItem(label,value)
            card.result_box.currentIndexChanged.connect(lambda i,k=key,c=card:self.set_playoff_result(k,c.result_box.itemData(i)))
            card.winner_box=QComboBox(); card.winner_box.addItem("Vincitore da definire",None)
            card.winner_box.currentIndexChanged.connect(lambda i,k=key,c=card:self.set_playoff_winner(k,c.winner_box.itemData(i)))
            card.layout().addWidget(card.result_box); card.layout().addWidget(card.winner_box)
        grid.addWidget(self.sf1,0,0); grid.addWidget(self.sf2,0,2); grid.addWidget(self.final,1,1); grid.addWidget(self.third,2,1)
        l.addLayout(grid); l.addStretch(); return page
    def set_playoff_result(self,key,value):
        old=self.playoff_results.get(key)
        if old==value: return
        if old is not None:
            answer=QMessageBox.question(self,"Modifica risultato playoff",
                f"Sostituire {old} con {value or 'In corso'}?",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:
                self.refresh_playoffs(); return
        if value is None: self.playoff_results.pop(key,None)
        else: self.playoff_results[key]=value
        self.log_operation("Risultato playoff",key,old or "In corso",value or "In corso")
        self.save(); self.refresh_playoffs()
    def set_playoff_winner(self,key,player):
        if player is None:
            self.playoff_winners.pop(key,None)
        else:
            self.playoff_winners[key]=player
        self.save(); self.refresh_playoffs()
    def playoff_pair_winner(self,key):
        pair=getattr(self,"playoff_pairs",{}).get(key,(None,None))
        result=self.playoff_results.get(key)
        if result=="1-0": return pair[0]
        if result=="0-1": return pair[1]
        if result=="1/2-1/2": return self.playoff_winners.get(key)
        return None
    def add_penalty(self):
        p=self.pen_player.currentData(); amount=float(self.pen_amount.value()); reason=self.pen_reason.text().strip() or "Penalità manuale"
        entry={"player":p,"points":-amount,"reason":reason,"time":datetime.now().strftime("%d/%m/%Y %H:%M")}
        self.penalties.append(entry)
        self.log_operation("Penalità aggiunta",p,"0",f"{-amount:+.1f}",reason)
        self.pen_reason.clear(); self.save(); self.refresh_all()
    def edit_penalty(self):
        i=self.pen_list.currentRow()
        if not 0<=i<len(self.penalties): return
        item=self.penalties[i]
        amount,ok=QInputDialog.getDouble(self,"Modifica penalità","Importo della detrazione (punti):",
            abs(float(item.get("points",0))),0.5,10.0,1)
        if not ok: return
        reason,ok=QInputDialog.getText(self,"Modifica motivazione","Motivazione:",text=item.get("reason",""))
        if not ok: return
        before=dict(item); item["points"]=-abs(amount); item["reason"]=reason.strip() or "Penalità manuale"
        item["time"]=datetime.now().strftime("%d/%m/%Y %H:%M")
        self.log_operation("Penalità modificata",item.get("player"),before,item)
        self.save(); self.refresh_all()
    def remove_penalty(self):
        i=self.pen_list.currentRow()
        if 0<=i<len(self.penalties):
            item=self.penalties.pop(i)
            self.log_operation("Penalità annullata",item.get("player"),item,"0")
            self.save(); self.refresh_all()
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
            g=game(gid)
            if hasattr(self,"calendar_pairings"):
                self.calendar_pairings[gid].setText(f"{name(g[2])}  <span style='color:{GOLD}'>vs</span>  {name(g[3])}")
            cb.blockSignals(True); cb.setCurrentIndex(max(0,cb.findData(self.results.get(gid)))); cb.blockSignals(False)
        if hasattr(self,"calendar_bye_labels"):
            for rnd,label in self.calendar_bye_labels.items():
                label.setText(f"ROUND {rnd}  ·  Riposa: {name(BYES[rnd])}  ·  BYE")
        self.refresh_draw_page()
        self.refresh_standings(); self.refresh_odds(); self.refresh_penalties(); self.refresh_playoffs()
        self.refresh_dashboard(); self.refresh_archive(); self.refresh_h2h(); self.refresh_audit()
        self.apply_calendar_filters()
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
        self.odds_footer.setText(f"15.000 scenari simulati · aggiornamento deterministico a ogni risultato, penalità o calendario · quota equa = 1 / probabilità stimata.")
    def refresh_penalties(self):
        self.pen_list.clear()
        if not self.penalties: self.pen_list.addItem("Nessuna penalità registrata.")
        for x in self.penalties:
            self.pen_list.addItem(f"{name(x.get('player',''))}   {x.get('points',0):+.1f} pt   ·   {x.get('reason','')}   ·   {x.get('time','')}")
    def refresh_playoffs(self):
        if not hasattr(self,"playoff_cards"): return
        rows=self.standings(); ids=[x["id"] for x in rows]
        self.playoff_pairs={
            "sf1":(ids[0],ids[3]),"sf2":(ids[1],ids[2]),
            "final":(self.playoff_pair_winner("sf1"),self.playoff_pair_winner("sf2")),
            "third":(self.playoff_pairs.get("sf1",(None,None))[1] if self.playoff_pair_winner("sf1") else None,
                     self.playoff_pairs.get("sf2",(None,None))[1] if self.playoff_pair_winner("sf2") else None)}
        # Rebuild losers directly from the semifinal pair and winner.
        for key,semi in (("final","sf1"),("third","sf1")):
            pair=self.playoff_pairs.get(semi,(None,None)); winner=self.playoff_pair_winner(semi)
            if key=="final":
                self.playoff_pairs["final"]=(winner,self.playoff_pair_winner("sf2"))
            else:
                loser=next((p for p in pair if p and p!=winner),None)
                pair2=self.playoff_pairs.get("sf2",(None,None)); winner2=self.playoff_pair_winner("sf2")
                loser2=next((p for p in pair2 if p and p!=winner2),None)
                self.playoff_pairs["third"]=(loser,loser2)
        labels={
            "sf1":("SEMIFINALE 1",self.playoff_pairs["sf1"]),
            "sf2":("SEMIFINALE 2",self.playoff_pairs["sf2"]),
            "final":("FINALE",self.playoff_pairs["final"]),
            "third":("3° / 4° POSTO",self.playoff_pairs["third"])}
        for key,card in self.playoff_cards.items():
            title,pair=labels[key]
            card.labels[0].setText(title)
            card.labels[1].setText(name(pair[0]) if pair[0] else "Da definire")
            card.labels[2].setText(name(pair[1]) if pair[1] else "Da definire")
            result=self.playoff_results.get(key)
            card.result_box.blockSignals(True)
            card.result_box.setCurrentIndex(max(0,card.result_box.findData(result)))
            card.result_box.blockSignals(False)
            card.winner_box.blockSignals(True); card.winner_box.clear()
            card.winner_box.addItem("Vincitore da definire",None)
            for p in pair:
                if p: card.winner_box.addItem(name(p),p)
            chosen=self.playoff_winners.get(key)
            card.winner_box.setCurrentIndex(max(0,card.winner_box.findData(chosen)))
            card.winner_box.setEnabled(result=="1/2-1/2")
            card.winner_box.blockSignals(False)
    def open_broadcast(self):
        if self.broadcast is None: self.broadcast=BroadcastWindow(self)
        self.broadcast.refresh_from_app()
        self.broadcast.showNormal()
        self.broadcast.resize(1180,760)
        self.broadcast.show()
        self.broadcast.raise_()
        self.broadcast.activateWindow()
    def closeEvent(self,event):
        for card in getattr(self,"live_cards",[]):
            worker=getattr(card,"engine_worker",None)
            if worker is not None and worker.isRunning():
                worker.wait(3000)
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
QListWidget#Sidebar{{background:#0C131D;border:1px solid {LINE};border-radius:12px;padding:8px;font-weight:800;}}
QListWidget#Sidebar::item{{color:{MUTED};padding:13px 10px;border-radius:8px;margin:3px 0;}}
QListWidget#Sidebar::item:selected{{background:#1B2633;color:{GOLD};border-left:3px solid {GOLD};}}
QListWidget#Sidebar::item:hover{{background:#151F2B;color:{TEXT};}}
QListWidget{{background:{PANEL};border:1px solid {LINE};border-radius:10px;padding:8px;}}
QProgressBar{{background:#0D141D;color:{TEXT};border:1px solid {LINE};border-radius:6px;text-align:center;font-size:10px;font-weight:800;}}
QProgressBar::chunk{{background:#B68D48;border-radius:5px;}}
QListWidget::item{{padding:12px;border-bottom:1px solid {LINE};}}
QListWidget::item:selected{{background:#253546;color:{GOLD};}}
QStatusBar{{background:#0D131B;color:{MUTED};border-top:1px solid {LINE};}}
QLabel{{background:transparent;}}
"""

def main():
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setStyle("Fusion"); app.setStyleSheet(STYLE)
    win=MainWindow(); win.show(); sys.exit(app.exec())
if __name__=="__main__": main()
