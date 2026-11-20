from __future__ import annotations
import json, os, random, sys, shutil, hashlib, math, csv, time, subprocess, queue, threading, re, uuid, base64, socket, io, html, urllib.parse, secrets, hmac, zipfile, tempfile, urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, quote, urlparse, unquote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import combinations
import chess
import chess.pgn
import qrcode
try:
    from . import c5r_theme as T
    from .c5r_widgets import (
        CardGlowController, SideNav, ToastStatusBar, Card, StatTile, EmptyState, ProbBar,
        PillDelegate, style_table, table_card, LineChart, ClockChip, ResultPicker,
        EvalBar, Avatar, PlayerStrip, FormStrip, MatchLine, label as ui_label, pill as ui_pill, set_pill, button as ui_button
    )
    from .c5r_board import BoardWidget
except ImportError:
    import c5r_theme as T
    from c5r_widgets import (
        CardGlowController, SideNav, ToastStatusBar, Card, StatTile, EmptyState, ProbBar,
        PillDelegate, style_table, table_card, LineChart, ClockChip, ResultPicker,
        EvalBar, Avatar, PlayerStrip, FormStrip, MatchLine, label as ui_label, pill as ui_pill, set_pill, button as ui_button
    )
    from c5r_board import BoardWidget
from PySide6.QtCore import Qt, QSize, Signal, QThread, QTimer, QRect, QUrl, QDateTime, QByteArray, QBuffer, QIODevice, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPdfWriter, QKeySequence, QShortcut, QDesktopServices, QPixmap, QIntValidator, QPainterPath
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QComboBox,
    QDoubleSpinBox, QLineEdit, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea, QMessageBox,
    QListWidget, QListWidgetItem, QInputDialog, QFileDialog, QAbstractItemView, QSizePolicy,
    QDialog, QDialogButtonBox, QProgressBar, QStackedWidget, QPlainTextEdit, QDateTimeEdit, QGraphicsOpacityEffect
)

try:
    from .c5r_storage import atomic_write_json, read_document, decode_document
except ImportError:
    from c5r_storage import atomic_write_json, read_document, decode_document
try:
    from .c5r_history import archive_edition, import_edition_file, list_editions, career_statistics
except ImportError:
    from c5r_history import archive_edition, import_edition_file, list_editions, career_statistics

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

RESULT_OPTIONS = [(None,"In corso"),("1-0","1–0"),("1/2-1/2","½–½"),("0-1","0–1"),("VOID","Annullata / esclusa")]
GOLD="#D8B36A"; BG="#090D12"; PANEL="#111923"; PANEL2="#151F2B"
LINE="#283444"; TEXT="#EEF1F5"; MUTED="#8F9BAA"; GREEN="#65C69A"

def name(pid): return PLAYERS.get(pid,(pid,""))[0]
def game(game_id): return next(g for g in GAMES if g[0] == game_id)
def storage_path():
    folder = Path(os.environ.get("APPDATA", str(Path.home()))) / "Coppa5Re"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "tournament.json"

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


class StockfishService(QThread):
    """Un solo processo Stockfish persistente per tutta la sessione dell'app."""
    positionReady = Signal(str, int)
    moveReady = Signal(str, dict)
    gameReady = Signal(str, list)
    analysisFailed = Signal(str, str)
    moveFailed = Signal(str, str)

    def __init__(self, engine_path, parent=None):
        super().__init__(parent)
        self.engine_path = engine_path
        self.jobs = queue.Queue()
        self.pending_positions = {}
        self.scheduled_positions = set()
        self.pending_lock = threading.Lock()
        self.stop_event = threading.Event()

    def request_position(self, game_id, board):
        with self.pending_lock:
            self.pending_positions[game_id] = board.copy(stack=True)
            if game_id not in self.scheduled_positions:
                self.scheduled_positions.add(game_id)
                self.jobs.put(("position", game_id))

    def request_move(self, game_id, board_before, move_uci, player_id, ply):
        self.jobs.put(("move", game_id, board_before.copy(stack=True), move_uci, player_id, ply))

    def request_game(self, game_id, moves):
        self.jobs.put(("game", game_id, list(moves)))

    def stop(self):
        self.stop_event.set()
        self.jobs.put(None)

    def run(self):
        engine = None
        try:
            import chess.engine
            popen_args = {}
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                popen_args = {
                    "creationflags": subprocess.CREATE_NO_WINDOW,
                    "startupinfo": startupinfo,
                }
            engine = chess.engine.SimpleEngine.popen_uci(
                self.engine_path,
                timeout=12,
                cwd=str(Path(self.engine_path).parent),
                **popen_args,
            )
            try:
                engine.configure({"Threads": 2, "Hash": 96})
            except Exception:
                pass

            while not self.stop_event.is_set():
                try:
                    job = self.jobs.get(timeout=0.25)
                except queue.Empty:
                    continue
                if job is None:
                    break

                kind, game_id = job[0], job[1]
                try:
                    if kind == "position":
                        with self.pending_lock:
                            board = self.pending_positions.pop(game_id, None)
                            self.scheduled_positions.discard(game_id)
                        if board is None:
                            continue
                        info = engine.analyse(
                            board,
                            chess.engine.Limit(depth=12, time=1.0),
                        )
                        score = info["score"].white().score(mate_score=10000)
                        if score is not None:
                            self.positionReady.emit(game_id, int(score))

                    elif kind == "move":
                        board_before, move_uci, player_id, ply = job[2], job[3], job[4], job[5]
                        move = chess.Move.from_uci(move_uci)
                        if move not in board_before.legal_moves:
                            raise ValueError(f"Mossa non valida: {move_uci}")
                        mover_color = board_before.turn
                        before_info = engine.analyse(
                            board_before,
                            chess.engine.Limit(time=0.30),
                        )
                        before_score = before_info["score"].pov(mover_color).score(mate_score=10000)
                        best_move = before_info.get("pv", [None])[0]
                        board_after = board_before.copy(stack=True)
                        board_after.push(move)
                        after_info = engine.analyse(
                            board_after,
                            chess.engine.Limit(time=0.30),
                        )
                        after_score = after_info["score"].pov(mover_color).score(mate_score=10000)
                        before_ep = 1.0 / (1.0 + math.exp(-max(-4000, min(4000, before_score or 0)) / 400.0))
                        after_ep = 1.0 / (1.0 + math.exp(-max(-4000, min(4000, after_score or 0)) / 400.0))
                        ep_loss = max(0.0, before_ep - after_ep)
                        mover_material_before = sum(
                            len(board_before.pieces(piece_type, mover_color)) * value
                            for piece_type, value in ((chess.PAWN, 1), (chess.KNIGHT, 3), (chess.BISHOP, 3),
                                (chess.ROOK, 5), (chess.QUEEN, 9))
                        ) - sum(
                            len(board_before.pieces(piece_type, not mover_color)) * value
                            for piece_type, value in ((chess.PAWN, 1), (chess.KNIGHT, 3), (chess.BISHOP, 3),
                                (chess.ROOK, 5), (chess.QUEEN, 9))
                        )
                        mover_material_after = sum(
                            len(board_after.pieces(piece_type, mover_color)) * value
                            for piece_type, value in ((chess.PAWN, 1), (chess.KNIGHT, 3), (chess.BISHOP, 3),
                                (chess.ROOK, 5), (chess.QUEEN, 9))
                        ) - sum(
                            len(board_after.pieces(piece_type, not mover_color)) * value
                            for piece_type, value in ((chess.PAWN, 1), (chess.KNIGHT, 3), (chess.BISHOP, 3),
                                (chess.ROOK, 5), (chess.QUEEN, 9))
                        )
                        sacrificed = mover_material_after - mover_material_before <= -3
                        if sacrificed and best_move == move and after_score is not None and after_score > -100 and ep_loss <= 0.02:
                            label = "BRILLANTE"
                        elif best_move == move:
                            label = "MIGLIORE"
                        elif ep_loss <= 0.01:
                            label = "OTTIMA"
                        elif ep_loss <= 0.03:
                            label = "BUONA"
                        elif ep_loss <= 0.08:
                            label = "IMPRECISIONE"
                        elif ep_loss <= 0.20:
                            label = "ERRORE"
                        else:
                            label = "GRAVE ERRORE"
                        review = {
                            "ply": ply, "player": player_id, "uci": move_uci,
                            "label": label, "expected_points_loss": round(ep_loss, 4),
                            "before_cp": int(before_score or 0), "after_cp": int(after_score or 0),
                            "best_uci": best_move.uci() if best_move else "",
                        }
                        self.moveReady.emit(game_id, review)

                    elif kind == "game":
                        moves = job[2]
                        board = chess.Board()
                        positions = []
                        _, _, white_player, black_player = game(game_id)
                        for ply, uci in enumerate(moves, 1):
                            if self.stop_event.is_set():
                                break
                            move = chess.Move.from_uci(uci)
                            if move not in board.legal_moves:
                                raise ValueError(f"Mossa PGN non valida al ply {ply}: {uci}")
                            mover_color = board.turn
                            player_id = white_player if mover_color else black_player
                            before_info = engine.analyse(board, chess.engine.Limit(time=0.25))
                            before_score = before_info["score"].pov(mover_color).score(mate_score=10000)
                            best_move = before_info.get("pv", [None])[0]
                            san = board.san(move)
                            piece_values={chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,chess.ROOK:5,chess.QUEEN:9}
                            material_before=sum(len(board.pieces(pt,mover_color))*val for pt,val in piece_values.items())-sum(len(board.pieces(pt,not mover_color))*val for pt,val in piece_values.items())
                            board.push(move)
                            after_info = engine.analyse(board, chess.engine.Limit(time=0.25))
                            after_score = after_info["score"].pov(mover_color).score(mate_score=10000)
                            before_ep = 1.0 / (1.0 + math.exp(-max(-4000, min(4000, before_score or 0)) / 400.0))
                            after_ep = 1.0 / (1.0 + math.exp(-max(-4000, min(4000, after_score or 0)) / 400.0))
                            ep_loss = max(0.0, before_ep-after_ep)
                            material_after=sum(len(board.pieces(pt,mover_color))*val for pt,val in piece_values.items())-sum(len(board.pieces(pt,not mover_color))*val for pt,val in piece_values.items())
                            apparent_sacrifice=(material_after-material_before)<=-3
                            if apparent_sacrifice and best_move==move and after_score is not None and after_score>-100 and ep_loss<=0.02:
                                label = "BRILLANTE"
                            elif best_move == move:
                                label = "MIGLIORE"
                            elif ep_loss <= 0.01:
                                label = "OTTIMA"
                            elif ep_loss <= 0.03:
                                label = "BUONA"
                            elif ep_loss <= 0.08:
                                label = "IMPRECISIONE"
                            elif ep_loss <= 0.20:
                                label = "ERRORE"
                            else:
                                label = "GRAVE ERRORE"
                            positions.append({
                                "ply": ply, "san": san, "score": int(after_score or 0),
                                "fen": board.fen(), "player": player_id, "uci": uci,
                                "label": label, "expected_points_loss": round(ep_loss, 4),
                                "before_cp": int(before_score or 0), "after_cp": int(after_score or 0),
                                "best_uci": best_move.uci() if best_move else "",
                            })
                        if not self.stop_event.is_set():
                            self.gameReady.emit(game_id, positions)

                except Exception as exc:
                    if kind=="move":
                        self.moveFailed.emit(game_id,str(exc))
                    else:
                        self.analysisFailed.emit(game_id, str(exc))

        except Exception as exc:
            self.analysisFailed.emit("", str(exc))
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
        player_row=QHBoxLayout()
        player_row.setSpacing(8)
        self.white_strip=PlayerStrip()
        self.black_strip=PlayerStrip()
        player_row.addWidget(self.white_strip,1)
        player_row.addWidget(self.black_strip,1)
        lay.addLayout(player_row)
        self.state_label=QLabel(); self.state_label.setObjectName("Eyebrow"); lay.addWidget(self.state_label)
        self.history_index=None
        self._history_entries=[]
        self._history_cache_ply=-1
        self.board=BoardWidget(True); self.board.moveRequested.connect(self.move); lay.addWidget(self.board,1)
        nav=QHBoxLayout()
        self.prev_move_btn=QPushButton("◀  Mossa precedente"); self.prev_move_btn.clicked.connect(self.previous_move)
        self.next_move_btn=QPushButton("Mossa successiva  ▶"); self.next_move_btn.clicked.connect(self.next_move)
        self.view_ply=QLabel("0 / 0"); self.view_ply.setObjectName("Muted")
        nav.addWidget(self.prev_move_btn); nav.addWidget(self.view_ply,1); nav.addWidget(self.next_move_btn); lay.addLayout(nav)
        counters=QHBoxLayout()
        self.total_moves=QLabel("MOSSE GIOCATE · 0"); self.total_moves.setObjectName("Eyebrow")
        self.no_progress=QLabel("SENZA CATTURE / MOSSE DI PEDONE · 0/100"); self.no_progress.setObjectName("Muted")
        counters.addWidget(self.total_moves); counters.addStretch(); counters.addWidget(self.no_progress)
        lay.addLayout(counters)
        self.history=QLabel("MOSSE  ·  Nessuna mossa"); self.history.setObjectName("Muted"); self.history.setWordWrap(True); self.history.setMaximumHeight(48); lay.addWidget(self.history)
        self.move_quality=QLabel("GAME REVIEW C5R · in attesa della prima mossa")
        self.move_quality.setObjectName("Muted"); self.move_quality.setWordWrap(True); lay.addWidget(self.move_quality)
        self.eval_bar=QProgressBar(); self.eval_bar.setRange(0,1000); self.eval_bar.setValue(500)
        self.eval_bar.setTextVisible(True); self.eval_bar.setFormat("VALUTAZIONE · motore non configurato")
        self.eval_bar.setFixedHeight(19); lay.addWidget(self.eval_bar)
        self.engine_worker=None; self.last_eval_signature=None
        bottom=QHBoxLayout(); self.turn=QLabel(); self.turn.setObjectName("Muted"); bottom.addWidget(self.turn,1)
        self.result=QComboBox()
        for value,label in RESULT_OPTIONS: self.result.addItem(label,value)
        self.result.currentIndexChanged.connect(lambda i:self.app.set_result(self.game_id,self.result.itemData(i)))
        bottom.addWidget(self.result); lay.addLayout(bottom)
        controls=QVBoxLayout()
        control_top=QHBoxLayout(); control_bottom=QHBoxLayout()
        self.undo=QPushButton("↶  Annulla"); self.undo.clicked.connect(lambda:self.app.undo(self.game_id))
        pgn=QPushButton("PGN"); pgn.clicked.connect(lambda:self.app.export_pgn(self.game_id))
        reset=QPushButton("Reset"); reset.clicked.connect(lambda:self.app.reset_board(self.game_id))
        self.engine_btn=QPushButton("STOCKFISH · ON" if self.app.engine_enabled else "STOCKFISH · OFF"); self.engine_btn.clicked.connect(self.app.toggle_engine); self.engine_btn.setEnabled(bool(self.app.find_engine()))
        self.clock_btn=QPushButton("AVVIA OROLOGIO"); self.clock_btn.clicked.connect(lambda:self.app.start_clock(self.game_id))
        self.rotate_btn=QPushButton("RUOTA"); self.rotate_btn.clicked.connect(self.board.toggle_orientation)
        self.theme_btn=QPushButton("TEMA"); self.theme_btn.clicked.connect(self.board.cycle_theme)
        print_sheet=QPushButton("STAMPA SCHEDA"); print_sheet.clicked.connect(lambda:self.app.export_match_sheet_pdf(self.game_id))
        show_qr=QPushButton("QR TAVOLO"); show_qr.clicked.connect(lambda:self.app.show_match_qr_dialog(self.game_id))
        notes=QPushButton("NOTA"); notes.clicked.connect(lambda:self.app.prompt_match_note(self.game_id))
        view_notes=QPushButton("VEDI NOTE"); view_notes.clicked.connect(lambda:self.app.show_match_notes(self.game_id))
        draw_offer=QPushButton("PATTA CONCORDATA"); draw_offer.clicked.connect(lambda:self.app.offer_draw(self.game_id))
        self.claim_draw_btn=QPushButton("RECLAMA PATTA · RIPETIZIONE")
        self.claim_draw_btn.setToolTip("Disponibile quando la posizione è ripetuta tre volte o si raggiungono 50 mosse senza catture né mosse di pedone.")
        self.claim_draw_btn.clicked.connect(lambda:self.app.claim_draw(self.game_id))
        resign=QPushButton("ABBANDONO"); resign.clicked.connect(lambda:self.app.resign_game(self.game_id))
        force=QPushButton("FORZA RISULTATO"); force.clicked.connect(lambda:self.app.force_game_result(self.game_id))
        control_top.addWidget(self.undo); control_top.addWidget(self.clock_btn); control_top.addStretch()
        control_top.addWidget(self.rotate_btn); control_top.addWidget(self.theme_btn)
        control_top.addWidget(print_sheet); control_top.addWidget(show_qr)
        control_bottom.addWidget(notes); control_bottom.addWidget(view_notes)
        control_bottom.addWidget(draw_offer); control_bottom.addWidget(self.claim_draw_btn)
        control_bottom.addWidget(resign); control_bottom.addWidget(force)
        control_bottom.addWidget(self.engine_btn); control_bottom.addStretch(); control_bottom.addWidget(pgn); control_bottom.addWidget(reset)
        controls.addLayout(control_top); controls.addLayout(control_bottom); lay.addLayout(controls)
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
    def refresh_players(self, gid, white, black):
        state = self.app.clock_data(gid)
        board = self.app.get_board(gid)
        finished = self.app.results.get(gid) is not None
        running = bool(state.get("started") and not finished)
        self.white_strip.set_data(
            name(white), self.app.player_rating_summary(white),
            T.player_tint(ORDER.index(white)), True, state.get("white", 0),
            running, board.turn == chess.WHITE and not finished,
        )
        self.black_strip.set_data(
            name(black), self.app.player_rating_summary(black),
            T.player_tint(ORDER.index(black)), False, state.get("black", 0),
            running, board.turn == chess.BLACK and not finished,
        )
        self.white_strip.set_photo(self.app.player_photo_pixmap(white, 32))
        self.black_strip.set_photo(self.app.player_photo_pixmap(black, 32))

    def refresh_clock(self):
        gid, _, _, _ = game(self.game_id)
        state = self.app.clock_data(gid)
        board = self.app.get_board(gid)
        finished = self.app.results.get(gid) is not None
        running = bool(state.get("started") and not finished)
        self.white_strip.clock.set_time(
            state.get("white", 0),
            running and board.turn == chess.WHITE,
        )
        self.black_strip.clock.set_time(
            state.get("black", 0),
            running and board.turn == chess.BLACK,
        )
        self.clock_btn.setEnabled(not finished and not state.get("started"))
        self.clock_btn.setText("OROLOGIO IN CORSO" if state.get("started") else "AVVIA OROLOGIO")
        self.refresh_claim_draw_button(board)
    def refresh_claim_draw_button(self, board):
        finished = self.app.results.get(self.game_id) is not None
        claimable = board.can_claim_threefold_repetition() or board.can_claim_fifty_moves()
        self.claim_draw_btn.setEnabled(not finished and claimable)
        if board.can_claim_threefold_repetition():
            self.claim_draw_btn.setText("RECLAMA PATTA · 3 RIPETIZIONI")
        elif board.can_claim_fifty_moves():
            self.claim_draw_btn.setText("RECLAMA PATTA · 50 MOSSE")
        else:
            self.claim_draw_btn.setText("RECLAMA PATTA · NON DISPONIBILE")
    def refresh_move_counters(self, board, total_plies=None):
        total = len(board.move_stack) if total_plies is None else total_plies
        # python-chess halfmove_clock counts half-moves since the last pawn move or capture.
        # The FIDE 50-move claim threshold is 100 half-moves.
        quiet_plies = min(100, board.halfmove_clock)
        self.total_moves.setText(f"MOSSE GIOCATE · {total}")
        self.no_progress.setText(
            f"SENZA CATTURE / MOSSE DI PEDONE · {quiet_plies}/100 semimosse"
        )
    def refresh_move_quality(self):
        reviews=self.app.move_reviews.get(self.game_id,[])
        if not reviews:
            self.move_quality.setText("GAME REVIEW C5R · analisi in attesa")
            return
        review=reviews[-1]
        player=name(review.get("player",""))
        loss=float(review.get("expected_points_loss",0))*100
        self.move_quality.setText(
            f"ULTIMA MOSSA · {player}: {review.get('label','—')}  ·  perdita punti attesi {loss:.1f}%"
        )
    def update_evaluation(self, gid, board):
        if not self.app.engine_enabled:
            self.eval_bar.setValue(500)
            self.eval_bar.setFormat("ANALISI STOCKFISH DISATTIVATA")
            return
        signature = board.fen()
        if signature == self.last_eval_signature:
            return
        self.last_eval_signature = signature
        service = self.app.get_engine_service()
        if service is None:
            self.eval_bar.setValue(500)
            self.eval_bar.setFormat("STOCKFISH INTEGRATO NON DISPONIBILE")
            return
        self.eval_bar.setFormat("ANALISI STOCKFISH · in background…")
        service.request_position(gid, board)

    def show_evaluation(self, gid, score):
        if not self.app.engine_enabled or gid != self.game_id:
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
    def refresh_after_move(self,san,ply_before,mover_color):
        """Refresh only volatile controls after an ordinary move."""
        gid,_,_,_=game(self.game_id)
        board=self.app.get_board(gid)
        ply=len(board.move_stack)
        finished=self.app.results.get(gid) is not None
        clock_state=self.app.clock_data(gid)
        self.history_index=ply
        self.known_ply=ply
        self.state_label.setText("CONCLUSA" if finished else ("IN CORSO" if clock_state.get("started") or ply else "LIVE"))
        self.turn.setText("PARTITA CONCLUSA · SCACCHIERA BLOCCATA" if finished else
                          f"AL MUOVERE: {'BIANCO' if board.turn else 'NERO'} · {board.fullmove_number}ª mossa")
        self.board.set_position(board,finished)
        self.update_evaluation(gid,board)
        self.refresh_move_counters(board,ply)
        self.view_ply.setText(f"{ply} / {ply}")
        self.prev_move_btn.setEnabled(ply>0)
        self.next_move_btn.setEnabled(False)
        self.white_strip.turn.setVisible(board.turn==chess.WHITE and not finished)
        self.black_strip.turn.setVisible(board.turn==chess.BLACK and not finished)
        self.refresh_clock()
        self.refresh_move_quality()
        if self._history_cache_ply==ply_before:
            prefix=f"{ply_before//2+1}. " if mover_color==chess.WHITE else f"{ply_before//2+1}... "
            self._history_entries.append(prefix+san)
            self._history_entries=self._history_entries[-12:]
            self._history_cache_ply=ply
            self.history.setText("MOSSE  ·  "+"  ".join(self._history_entries))
        else:
            self._render_move_history(board,ply)
        self.undo.setEnabled(bool(ply) and not finished)

    def _render_move_history(self,board,ply):
        replay=chess.Board()
        entries=[]
        for move in board.move_stack[:ply]:
            prefix=f"{replay.fullmove_number}. " if replay.turn==chess.WHITE else f"{replay.fullmove_number}... "
            entries.append(prefix+replay.san(move))
            replay.push(move)
        self._history_entries=entries[-12:]
        self._history_cache_ply=ply
        self.history.setText("MOSSE  ·  "+("  ".join(self._history_entries) if entries else "Nessuna mossa"))

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
        self.engine_btn.setText("STOCKFISH · ON" if self.app.engine_enabled else "STOCKFISH · OFF")
        clock_state=self.app.clock_data(gid)
        self.refresh_players(gid,w,b)
        self.state_label.setText("CONCLUSA" if self.app.results.get(gid) else ("IN CORSO" if clock_state.get("started") or board.move_stack else "LIVE"))
        self.turn.setText("PARTITA CONCLUSA · SCACCHIERA BLOCCATA" if self.app.results.get(gid) else
                          f"{'REVISIONE · ' if self.history_index<len(board.move_stack) else ''}AL MUOVERE: {'BIANCO' if visible.turn else 'NERO'} · {visible.fullmove_number}ª mossa")
        self.board.set_position(visible,bool(self.app.results.get(gid)) or self.history_index<len(board.move_stack))
        self.update_evaluation(gid, visible)
        self.refresh_move_counters(visible,len(board.move_stack))
        self.view_ply.setText(f"{self.history_index} / {len(board.move_stack)}")
        self.prev_move_btn.setEnabled(self.history_index>0)
        self.next_move_btn.setEnabled(self.history_index<len(board.move_stack))
        self.refresh_clock()
        self.refresh_move_quality()
        self._render_move_history(visible,self.history_index)
        self.result.blockSignals(True); self.result.setCurrentIndex(max(0,self.result.findData(self.app.results.get(gid)))); self.result.blockSignals(False)
        self.undo.setEnabled(bool(board.move_stack) and not self.app.results.get(gid))

class SpectatorCard(QFrame):
    def __init__(self,label):
        super().__init__(); self.setObjectName("Card")
        lay=QVBoxLayout(self); self.tag=QLabel(label); self.tag.setObjectName("Eyebrow")
        self.white_photo=QLabel(); self.white_photo.setFixedSize(34,34)
        self.white_name=QLabel(); self.white_name.setObjectName("MatchTitle")
        self.black_photo=QLabel(); self.black_photo.setFixedSize(34,34)
        self.black_name=QLabel(); self.black_name.setObjectName("MatchTitle")
        players=QHBoxLayout(); players.addWidget(self.white_photo); players.addWidget(self.white_name,1)
        players.addWidget(QLabel("VS")); players.addWidget(self.black_name,1); players.addWidget(self.black_photo)
        self.status=QLabel(); self.status.setObjectName("Muted")
        self.clock=QLabel(); self.clock.setObjectName("Muted")
        self.board=BoardWidget(False)
        lay.addWidget(self.tag); lay.addLayout(players); lay.addWidget(self.status); lay.addWidget(self.clock); lay.addWidget(self.board,1)
    def update_position(self,app,gid):
        result=app.results.get(gid); clock=app.clock_data(gid)
        board=app.get_board(gid)
        self.status.setText("CONCLUSA" if result else ("IN CORSO" if clock.get("started") or board.move_stack else "LIVE"))
        self.clock.setText(app.clock_text(gid))
        self.board.set_position(board,True)
    def update_game(self,app,gid):
        _,r,w,b=game(gid)
        self.white_name.setText(name(w)); self.black_name.setText(name(b))
        app.set_player_avatar_label(self.white_photo,w,34)
        app.set_player_avatar_label(self.black_photo,b,34)
        self.update_position(app,gid)

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
    def refresh_game(self,gid):
        for card,live in zip(self.cards,self.app.live_cards):
            if live.game_id==gid:
                card.update_position(self.app,gid)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape: self.close()
        else: super().keyPressEvent(event)

class PublicReachabilityProbe(QThread):
    probeFinished=Signal(bool,str)
    def __init__(self,url,parent=None):
        super().__init__(parent)
        self.url=url
    def run(self):
        try:
            request=urllib.request.Request(self.url,headers={"Cache-Control":"no-cache","User-Agent":"Coppa5Re-Windows"})
            with urllib.request.urlopen(request,timeout=5) as response:
                body=response.read(256).decode("utf-8","replace")
                if response.status!=200 or "C5R local match server OK" not in body:
                    raise RuntimeError(f"Risposta HTTP inattesa ({response.status}).")
            self.probeFinished.emit(True,"Connessione pubblica raggiungibile.")
        except Exception as exc:
            self.probeFinished.emit(False,str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Coppa dei 5 Re · Control Room")
        self.resize(1500,950); self.setMinimumSize(980,680)
        self.results={}; self.penalties=[]; self.moves={}; self.boards={}; self.broadcast=None; self.engine_path=None; self.engine_enabled=True; self.engine_service=None; self.analysis_running_gid=None
        self._odds_cache_key=None; self._odds_cache=None
        self._web_match_cache={}
        self._move_save_pending=False
        self._move_save_timer=QTimer(self)
        self._move_save_timer.setSingleShot(True)
        self._move_save_timer.setInterval(120)
        self._move_save_timer.timeout.connect(self.flush_move_save)
        self.time_control="15+3"; self.clocks={}; self.audit_log=[]; self.match_notes={}; self.referee=""
        self.tie_break="Regolamento Art. 8"; self.playoff_results={}; self.eval_history={}; self.clock_ticks=0; self.board_theme=0
        self.game_terminations={}; self.move_reviews={}; self.withdrawn_players={}
        self.move_annotations={}; self.round_closures={}; self.incident_reports=[]; self.player_bios={}; self.notification_drafts=[]
        self.match_http_server=None; self.match_http_thread=None; self.match_http_host=""; self.match_http_port=0
        self.public_base_url=os.environ.get("C5R_PUBLIC_BASE_URL","").strip().rstrip("/")
        self.spectator_token=secrets.token_urlsafe(32)
        self.operational_alerts=[]
        self.long_match_minutes=120
        self._public_probe_thread=None
        self._last_public_probe=0.0
        self._public_connection_state=None
        self.ui_preferences={"theme":"dark","font_scale":1.0,"density":"comfortable"}; self.ui_profiles={}
        self._clock_runtime={}; self._last_clock_persist=time.monotonic()
        self._undo_stack=[]; self._redo_stack=[]; self._history_restoring=False; self._last_history_state=None
        self.state_load_blocked=False
        self.recovery_path=storage_path().with_name("recovery.json")
        self.offer_recovery()
        self.load_state(); self._last_history_state=self._history_snapshot(self.state_payload()); self.build_ui(); self.apply_ui_preferences(); self.refresh_all()
        self.clock_timer=QTimer(self); self.clock_timer.timeout.connect(self.tick_clocks); self.clock_timer.start(1000)
        self.notification_timer=QTimer(self); self.notification_timer.timeout.connect(self.refresh_notification_badge); self.notification_timer.start(30000)
        self.refresh_spectator_config_hint()
        if self.public_base_url:
            try:self.start_match_web_server()
            except Exception as exc:
                self.record_operational_alert("Server spettatori non avviato",str(exc),"danger","settings","local-server-start")
        self.install_shortcuts()
        self.refresh_notification_badge()
    def load_state(self):
        path=storage_path()
        backup_candidates=(path.with_suffix(path.suffix + ".bak"),path.with_suffix(path.suffix + ".bak.1"))
        if not path.exists() and not any(candidate.exists() for candidate in backup_candidates):
            return
        try:
            data, fallback = read_document(path)
            self.results=data.get("results",{}); self.penalties=data.get("penalties",[]); self.moves=data.get("moves",{}); self.engine_path=data.get("engine_path"); self.engine_enabled=bool(data.get("engine_enabled",True))
            self.time_control=data.get("time_control","15+3"); self.clocks=data.get("clocks",{})
            self.audit_log=data.get("audit_log",[]); self.match_notes=data.get("match_notes",{})
            self.referee=data.get("referee",""); self.tie_break=data.get("tie_break","Nessuno")
            self.playoff_results=data.get("playoff_results",{}); self.playoff_winners=data.get("playoff_winners",{}); self.eval_history=data.get("eval_history",{})
            self.game_terminations=data.get("game_terminations",{}); self.move_reviews=data.get("move_reviews",{})
            self.withdrawn_players=data.get("withdrawn_players",{})
            self.move_annotations=data.get("move_annotations",{})
            self.round_closures=data.get("round_closures",{}); self.incident_reports=data.get("incident_reports",[]); self.player_bios=data.get("player_bios",{}); self.notification_drafts=data.get("notification_drafts",[])
            self.ui_preferences=data.get("ui_preferences",getattr(self,"ui_preferences",{}))
            self.ui_profiles=data.get("ui_profiles",getattr(self,"ui_profiles",{}))
            self.public_base_url=str(data.get("public_base_url",self.public_base_url)).strip().rstrip("/")
            self.spectator_token=str(data.get("spectator_token") or self.spectator_token)
            self.operational_alerts=data.get("operational_alerts",[])
            self.long_match_minutes=int(data.get("long_match_minutes",120) or 120)
            saved_schedule=data.get("schedule")
            if saved_schedule:
                parsed=[(g["id"],int(g["round"]),g["white"],g["black"]) for g in saved_schedule]
                if validate_schedule(parsed):
                    GAMES[:] = parsed
                    BYES.clear()
                    for rnd in range(1,6):
                        played=[p for g in GAMES if g[1]==rnd for p in (g[2],g[3])]
                        BYES[rnd]=next(p for p in ORDER if p not in played)
            # A process restart pauses clocks; suspend/resume in this process is timed separately.
            now=time.time()
            self._clock_runtime={}
            for gid,clock in self.clocks.items():
                if clock.get("started"):
                    clock["last_wall"]=now
                    self._clock_runtime[gid]=time.monotonic()
            if fallback is not None:
                QMessageBox.warning(self,"Archivio recuperato",
                    f"Il file principale non era integro. Sono stati recuperati i dati dalla copia {fallback.name}. "
                    "Salva il torneo per rigenerare l'archivio principale.")
        except Exception as exc:
            self.state_load_blocked=True
            QMessageBox.critical(self,"Archivio non leggibile",
                f"Non è stato possibile leggere i dati del torneo in modo sicuro.\n\n{exc}\n\n"
                "I dati originali non sono stati sovrascritti. Il salvataggio resta bloccato finché non ripristini un backup valido.")

    def state_payload(self):
        stored_schedule=[{"id":gid,"round":rnd,"white":white,"black":black} for gid,rnd,white,black in GAMES]
        return {
            "results":self.results,"penalties":self.penalties,"moves":self.moves,
            "schedule":stored_schedule,"engine_path":self.engine_path,"engine_enabled":self.engine_enabled,"time_control":self.time_control,
            "clocks":self.clocks,"audit_log":self.audit_log,"match_notes":self.match_notes,
            "referee":self.referee,"tie_break":self.tie_break,"playoff_results":self.playoff_results,
            "eval_history":self.eval_history,"playoff_winners":getattr(self,"playoff_winners",{}),
            "game_terminations":self.game_terminations,"move_reviews":self.move_reviews,
            "withdrawn_players":self.withdrawn_players,
            "move_annotations":self.move_annotations,"round_closures":self.round_closures,
            "ui_preferences":self.ui_preferences,"ui_profiles":self.ui_profiles,"incident_reports":self.incident_reports,"player_bios":self.player_bios,"notification_drafts":self.notification_drafts,
            "public_base_url":self.public_base_url,"spectator_token":self.spectator_token,
            "operational_alerts":self.operational_alerts,"long_match_minutes":self.long_match_minutes,
            "saved_at":datetime.now().isoformat(timespec="seconds"),
        }

    def _history_snapshot(self,payload=None):
        data=dict(payload or self.state_payload())
        # Clocks and engine evaluations evolve without operator actions.
        for key in ("clocks","eval_history","saved_at","operational_alerts","spectator_token","public_base_url","long_match_minutes"):
            data.pop(key,None)
        return json.loads(json.dumps(data,ensure_ascii=False,sort_keys=True,default=str))

    def save(self, automatic_snapshot=True):
        if getattr(self,"state_load_blocked",False):
            self.statusBar().showMessage(
                "Salvataggio bloccato: archivio locale non leggibile. Ripristina un backup valido prima di continuare.",
                7000
            )
            return False
        payload=self.state_payload()
        current_history=self._history_snapshot(payload)
        if not self._history_restoring and self._last_history_state is not None and current_history!=self._last_history_state:
            self._undo_stack.append(self._last_history_state)
            if len(self._undo_stack)>100:
                del self._undo_stack[:-100]
            self._redo_stack.clear()
        self._last_history_state=current_history
        atomic_write_json(storage_path(),payload)
        if automatic_snapshot:
            self._maybe_create_auto_snapshot()
        return True

    def _restore_history_snapshot(self,snapshot,action_label):
        current=self.state_payload()
        merged=dict(current)
        merged.update(snapshot)
        self._history_restoring=True
        try:
            atomic_write_json(storage_path(),merged)
            self.boards.clear()
            self._odds_cache_key=None; self._odds_cache=None
            self.load_state()
            self.log_operation(action_label,"","", "Cronologia torneo ripristinata")
            self.save(automatic_snapshot=False)
        finally:
            self._history_restoring=False
        self._last_history_state=self._history_snapshot(self.state_payload())
        self.refresh_all()
        self.statusBar().showMessage(f"{action_label}: operazione applicata.",3000)

    def undo_history(self):
        if not self._undo_stack:
            self.statusBar().showMessage("Nessuna operazione del torneo da annullare.",2500)
            return
        current=self._history_snapshot(self.state_payload())
        target=self._undo_stack.pop()
        self._redo_stack.append(current)
        self._restore_history_snapshot(target,"Annullamento")

    def redo_history(self):
        if not self._redo_stack:
            self.statusBar().showMessage("Nessuna operazione da ripristinare.",2500)
            return
        current=self._history_snapshot(self.state_payload())
        target=self._redo_stack.pop()
        self._undo_stack.append(current)
        self._restore_history_snapshot(target,"Ripristino")

    def offer_recovery(self):
        path=getattr(self,"recovery_path",storage_path().with_name("recovery.json"))
        if not path.exists():
            return
        try:
            snapshot=decode_document(json.loads(path.read_text(encoding="utf-8")))
            has_moves=any(bool(items) for items in snapshot.get("moves",{}).values())
            has_running_clock=any(c.get("started") for c in snapshot.get("clocks",{}).values())
            if not has_moves and not has_running_clock:
                path.unlink(missing_ok=True)
                return
            answer=QMessageBox.question(
                self,
                "Ripristino partita",
                "È stata trovata una partita non salvata. Vuoi ripristinarla?",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer==QMessageBox.StandardButton.Yes:
                atomic_write_json(storage_path(),snapshot)
                self.statusBar().showMessage("Recovery trovato: dati dell'ultima partita ripristinati.",5000)
            path.unlink(missing_ok=True)
        except Exception as exc:
            QMessageBox.warning(self,"Recovery non leggibile",f"Il file di ripristino non è valido: {exc}")
            path.unlink(missing_ok=True)

    def save_recovery(self,persist=True):
        if getattr(self,"state_load_blocked",False):
            return
        active=any(
            (self.moves.get(gid) and not self.results.get(gid)) or self.clock_data(gid).get("started")
            for gid,_,_,_ in GAMES
        ) or any(self.clock_data(key).get("started") and not self.playoff_results.get(key)
            for key in ("sf1","sf2","final","third"))
        if not active:
            self.recovery_path.unlink(missing_ok=True)
            return
        if persist and not self.save():
            return
        tmp=self.recovery_path.with_suffix(".tmp")
        shutil.copy2(storage_path(),tmp)
        tmp.replace(self.recovery_path)

    def schedule_move_save(self):
        """Coalesce rapid move writes; keep the in-memory game and UI immediate."""
        if getattr(self,"state_load_blocked",False):
            return
        self._move_save_pending=True
        self._move_save_timer.start()

    def flush_move_save(self):
        if not self._move_save_pending:
            return
        self._move_save_pending=False
        if self.save():
            self.save_recovery(persist=False)

    def toggle_engine(self):
        if not self.find_engine():
            QMessageBox.warning(self,"Stockfish non disponibile","Il motore non è presente nella build corrente."); return
        self.engine_enabled=not self.engine_enabled
        for card in getattr(self,"live_cards",[]): card.last_eval_signature=None
        self.log_operation("Stockfish","",not self.engine_enabled,self.engine_enabled)
        self.save(); self.refresh_all()
    def find_engine(self):
        # In una build PyInstaller, dare sempre priorità al motore incluso nell'EXE.
        bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "stockfish" / "stockfish.exe"
        candidates = [
            bundled,
            Path(__file__).resolve().parent / "stockfish" / "stockfish.exe",
            Path(sys.executable).resolve().parent / "stockfish.exe",
            storage_path().parent / "stockfish.exe",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        # Compatibilità per eventuali installazioni di sviluppo non bundle.
        found = shutil.which("stockfish")
        return found if found and Path(found).is_file() else None

    def get_engine_service(self):
        if not self.engine_enabled:
            return None
        if self.engine_service is not None and self.engine_service.isRunning():
            return self.engine_service
        path = self.find_engine()
        if not path:
            return None
        service = StockfishService(path, self)
        service.positionReady.connect(self.on_engine_position_ready)
        service.moveReady.connect(self.on_move_review_ready)
        service.moveFailed.connect(self.on_move_review_failed)
        service.gameReady.connect(self.on_game_analysis_ready)
        service.analysisFailed.connect(self.on_game_analysis_failed)
        self.engine_service = service
        service.start()
        return service

    def on_engine_position_ready(self, game_id, score):
        for card in getattr(self, "live_cards", []):
            if card.game_id == game_id:
                card.show_evaluation(game_id, score)

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
            board_before=b.copy(stack=True)
            mover_color=b.turn
            ply_before=len(board_before.move_stack)
            san=board_before.san(move)
            white_player=game(gid)[2]; black_player=game(gid)[3]
            player_id=white_player if mover_color else black_player
            mover="white" if mover_color else "black"
            clock=self.clock_data(gid)
            clock_was_running=bool(clock.get("started"))
            if clock_was_running:
                side,remaining,_=self._advance_clock(gid)
                if remaining<=0:
                    self.tick_clocks(); return
            b.push(move)
            if not clock_was_running:
                # The first player is not charged for time before making the opening move.
                # Start the opponent's clock immediately after the first legal move.
                now_wall=time.time()
                clock["started"]=True
                clock["started_at"]=clock.get("started_at") or now_wall
                clock["overlong_alerted"]=False
                clock["last_wall"]=now_wall
                self._clock_runtime[gid]=time.monotonic()
            # Fischer increment is awarded for every completed move, including the first.
            if clock.get("started"): clock[mover]+=self.increment_seconds(gid)
            self.moves[gid]=[x.uci() for x in b.move_stack]
            self.log_operation("Mossa",gid,"",uci)
            service=self.get_engine_service()
            if service is not None:
                service.request_move(gid,board_before,move.uci(),player_id,len(b.move_stack))
            # Only automatic endings are applied here (e.g. fivefold repetition
            # or 75 moves). Threefold repetition and the 50-move rule require a claim.
            outcome=b.outcome(claim_draw=False)
            if outcome is not None:
                clock["started"]=False
                reason=outcome.termination.name.replace("_"," ").lower()
                self._move_save_timer.stop()
                self._move_save_pending=False
                self.set_result(gid,b.result(claim_draw=False),confirm=False,detail=reason,termination="normal")
                self.statusBar().showMessage("Partita terminata automaticamente: "+reason,5000)
                return
            card=next((item for item in getattr(self,"live_cards",[]) if item.game_id==gid),None)
            if card is not None:
                card.refresh_after_move(san,ply_before,mover_color)
            if self.broadcast and self.broadcast.isVisible():
                self.broadcast.refresh_game(gid)
            self.statusBar().showMessage(f"Mossa registrata · {gid} · {san}",1800)
            self.schedule_move_save()
        except Exception as exc:
            self.statusBar().showMessage(f"Mossa non registrata: {exc}",4000)
    def undo(self,gid):
        b=self.get_board(gid)
        if b.move_stack and not self.results.get(gid):
            removed=b.pop(); self.moves[gid]=[x.uci() for x in b.move_stack]
            self.log_operation("Mossa annullata",gid,removed.uci(),"")
            self.save(); self.refresh_all()
    def reset_board(self,gid):
        if QMessageBox.question(self,"Reset","Cancellare tutte le mosse di questa partita?")==QMessageBox.StandardButton.Yes:
            self.boards[gid]=chess.Board(); self.moves[gid]=[]; self.clocks.pop(gid,None)
            self.log_operation("Scacchiera resettata",gid,"","posizione iniziale")
            self.save(); self.refresh_all()
    def on_move_review_failed(self,gid,error):
        self.statusBar().showMessage(f"Game Review non disponibile per {gid}: {error}",5000)
    def on_move_review_ready(self,gid,review):
        reviews=self.move_reviews.setdefault(gid,[])
        reviews[:]=[item for item in reviews if int(item.get("ply",-1))!=int(review.get("ply",-2))]
        reviews.append(review)
        reviews.sort(key=lambda item:int(item.get("ply",0)))
        self.log_operation("Game Review",gid,"",review.get("label",""),f"ply {review.get('ply')} · {review.get('expected_points_loss',0):.3f} EP lost")
        self.save()
        for card in getattr(self,"live_cards",[]):
            if card.game_id==gid:
                card.refresh_move_quality()
    def claim_draw(self,gid):
        if self.results.get(gid):
            return
        board=self.get_board(gid)
        if board.can_claim_threefold_repetition():
            detail="Patta reclamata per triplice ripetizione"
        elif board.can_claim_fifty_moves():
            detail="Patta reclamata per regola delle 50 mosse"
        else:
            self.statusBar().showMessage("Patta non reclamabile: nessuna triplice ripetizione o soglia delle 50 mosse raggiunta.",4000)
            self.refresh_all()
            return
        _,_,white,black=game(gid)
        answer=QMessageBox.question(
            self,"Conferma reclamo di patta",
            f"{detail}. Confermare la patta tra {name(white)} e {name(black)}?",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer==QMessageBox.StandardButton.Yes:
            self.set_result(gid,"1/2-1/2",confirm=False,detail=detail,termination="normal")
            self.statusBar().showMessage(detail+" · risultato registrato.",4500)
    def offer_draw(self,gid):
        if self.results.get(gid): return
        _,_,white,black=game(gid)
        answer=QMessageBox.question(self,"Patta consensuale",
            f"Confermate entrambi i giocatori ({name(white)} e {name(black)}) la patta?",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer==QMessageBox.StandardButton.Yes:
            self.set_result(gid,"1/2-1/2",confirm=True,detail="Patta consensuale",termination="normal")
    def resign_game(self,gid):
        if self.results.get(gid): return
        board=self.get_board(gid)
        _,_,white,black=game(gid)
        resigning=white if board.turn==chess.WHITE else black
        result="0-1" if board.turn==chess.WHITE else "1-0"
        answer=QMessageBox.question(self,"Abbandono",
            f"Confermi l'abbandono di {name(resigning)}? Il risultato sarà {result}.",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer==QMessageBox.StandardButton.Yes:
            self.set_result(gid,result,confirm=True,detail=f"Abbandono di {name(resigning)}",termination="abandoned")
    def force_game_result(self,gid):
        options=["1-0","1/2-1/2","0-1","Annullata / esclusa"]
        choice,ok=QInputDialog.getItem(self,"Forzatura risultato",f"Partita {gid} · risultato deciso dall'arbitro:",options,0,False)
        if not ok: return
        value={"Annullata / esclusa":"VOID"}.get(choice,choice)
        reason,ok=QInputDialog.getText(self,"Motivazione arbitro","Motivo della decisione:",text="Decisione del direttore di gara")
        if not ok: return
        self.set_result(gid,value,confirm=True,detail=reason or "Forzatura arbitrale",termination="adjudication")
    def withdraw_player(self,player_id):
        if player_id in self.withdrawn_players:
            QMessageBox.information(self,"Ritiro già registrato",f"{name(player_id)} risulta già ritirato.")
            return
        matches=[g for g in GAMES if player_id in (g[2],g[3])]
        played=[g for g in matches if self.results.get(g[0]) not in (None,"VOID")]
        answer=QMessageBox.question(self,"Conferma ritiro",
            f"{name(player_id)} ha {len(played)} partite concluse su 4.\n"
            "Art. 11: con almeno 2 partite i risultati già ottenuti restano validi; "
            "con meno di 2 vengono annullati. Le partite restanti saranno assegnate a tavolino agli avversari.\n\n"
            "Confermare il ritiro?",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes: return
        keep_results=len(played)>=2
        for gid,_,white,black in matches:
            old=self.results.get(gid)
            if keep_results:
                if old in (None,"VOID"):
                    opponent=black if white==player_id else white
                    opponent_is_white=(opponent==white)
                    result="1-0" if opponent_is_white else "0-1"
                    self.results[gid]=result
                    self.game_terminations[gid]={"termination":"adjudication","detail":f"Forfait per ritiro di {name(player_id)}"}
                    self.clock_data(gid)["started"]=False
                    self.log_operation("Forfait per ritiro",gid,old or "In corso",result,name(player_id))
            else:
                self.results[gid]="VOID"
                self.game_terminations[gid]={"termination":"adjudication","detail":f"Risultato annullato ai sensi dell'Art. 11 (ritiro prima di 2 partite)"}
                self.clock_data(gid)["started"]=False
                self.log_operation("Partita annullata per ritiro",gid,old or "In corso","VOID",name(player_id))
        self.withdrawn_players[player_id]={"time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "played_at_withdrawal":len(played),"kept_results":keep_results}
        self.log_operation("Giocatore ritirato",player_id,"Attivo","Ritirato",f"{len(played)} partite completate")
        self.save(); self.refresh_all()
        self.statusBar().showMessage(f"Ritiro di {name(player_id)} registrato secondo l'Art. 11.",4500)
    def set_result(self,gid,value,confirm=True,detail="inserimento manuale",termination=None):
        if getattr(self,"state_load_blocked",False):
            QMessageBox.warning(self,"Archivio non disponibile",
                "Non registro risultati finché l'archivio locale non è leggibile. Ripristina un backup JSON valido.")
            return
        old=self.results.get(gid)
        if old==value: return
        if old is not None and confirm:
            answer=QMessageBox.question(self,"Conferma modifica risultato",
                f"La partita {gid} ha già risultato {old}. Vuoi sostituirlo con {value or 'In corso'}?",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:
                self.refresh_all(); return
        if value is None:
            self.results.pop(gid,None)
            self.game_terminations.pop(gid,None)
        else:
            self.results[gid]=value
            self.clock_data(gid)["started"]=False
            self.game_terminations[gid]={"termination":termination or ("adjudication" if value=="VOID" else "normal"),"detail":detail}
        round_key = str(game(gid)[1])
        if round_key in self.round_closures:
            previous_closure = self.round_closures.pop(round_key)
            self.log_operation("Turno riaperto", f"Round {round_key}", previous_closure, "Riaperto",
                               "Un risultato del turno è stato modificato.")
        self.log_operation("Risultato",gid,old or "In corso",value or "In corso",detail)
        if value not in (None,"VOID"):
            timed_out=termination=="time forfeit" or "bandierina" in detail.lower() or "tempo esaurito" in detail.lower()
            title="Tempo esaurito · risultato da validare" if timed_out else "Risultato da verificare"
            self.record_operational_alert(
                title,f"{gid} · esito {value} · {detail}",
                "danger" if timed_out else "warning","calendar",f"result:{gid}:{len(self.audit_log)}"
            )
        self.save(); self.save_recovery(persist=False); self.refresh_all()
        if value not in (None,"VOID") and self.moves.get(gid):
            service=self.get_engine_service()
            if service is not None:
                if self.analysis_running_gid is None:
                    self.analysis_running_gid=gid
                service.request_game(gid,self.moves[gid])
        self.statusBar().showMessage("Risultato salvato · classifica, quote e Game Review aggiornati.",3000)
    def time_control_for_game(self,gid):
        return "30+10" if gid in ("sf1","sf2","final","third") or str(gid).startswith("PO-") else "15+3"
    def clock_data(self,gid):
        control=self.time_control_for_game(gid)
        if gid not in self.clocks:
            base,_=control.split("+"); seconds=int(base)*60
            self.clocks[gid]={"white":seconds,"black":seconds,"started":False,"last_wall":time.time()}
        else:
            base,_=control.split("+"); seconds=int(base)*60
            self.clocks[gid].setdefault("white",seconds)
            self.clocks[gid].setdefault("black",seconds)
            self.clocks[gid].setdefault("started",False)
            self.clocks[gid].setdefault("last_wall",time.time())
            self.clocks[gid].setdefault("started_at",None)
            self.clocks[gid].setdefault("overlong_alerted",False)
        self.clocks[gid].setdefault("started_at",None)
        self.clocks[gid].setdefault("overlong_alerted",False)
        return self.clocks[gid]

    def _advance_clock(self,gid,side=None):
        clock=self.clock_data(gid)
        if side is None:
            side=clock.get("side_to_move","white") if gid in ("sf1","sf2","final","third") else ("white" if self.get_board(gid).turn else "black")
        now_mono=time.monotonic()
        now_wall=time.time()
        previous_mono=self._clock_runtime.get(gid)
        previous_wall=float(clock.get("last_wall",now_wall) or now_wall)
        wall_elapsed=max(0.0,now_wall-previous_wall)
        mono_elapsed=max(0.0,now_mono-previous_mono) if previous_mono is not None else 0.0
        # Wall time includes Windows sleep/hibernation; monotonic protects against clock rollback.
        elapsed=min(43200.0,max(wall_elapsed,mono_elapsed))
        clock[side]=max(0.0,float(clock.get(side,0.0))-elapsed)
        clock["last_wall"]=now_wall
        self._clock_runtime[gid]=now_mono
        return side,clock[side],elapsed

    def increment_seconds(self,gid=None):
        return int(self.time_control_for_game(gid).split("+")[1])
    def clock_text(self,gid):
        c=self.clock_data(gid)
        def fmt(v):
            v=max(0,int(v)); return f"{v//60:02d}:{v%60:02d}"
        return f"BIANCO {fmt(math.ceil(c['white']))}   ·   NERO {fmt(math.ceil(c['black']))}"
    def start_clock(self,gid):
        if self.results.get(gid): return
        clock=self.clock_data(gid)
        clock["started"]=True
        clock["started_at"]=clock.get("started_at") or time.time()
        clock["overlong_alerted"]=bool(clock.get("overlong_alerted",False))
        clock["last_wall"]=time.time(); self._clock_runtime[gid]=time.monotonic()
        self.log_operation("Orologio avviato",gid,"fermo",self.time_control_for_game(gid))
        self.save(); self.save_recovery(); self.refresh_all()
        self.statusBar().showMessage("Cronometro avviato.",2000)
    def set_time_control(self,value):
        # I controlli sono vincolati all'Art. 5: 15+3 in qualificazione, 30+10 nei playoff.
        self.time_control="15+3"
        self.statusBar().showMessage("Cadenze fissate dal regolamento: qualificazione 15+3, playoff 30+10.",3500)
    def check_long_match_alerts(self):
        threshold=max(15,int(getattr(self,"long_match_minutes",120) or 120))*60
        active=[]
        for gid,_,white,black in GAMES:
            if self.results.get(gid) is None:active.append((gid,name(white),name(black),"calendar"))
        for key in ("sf1","sf2","final","third"):
            if self.playoff_results.get(key) is None:
                pair=getattr(self,"playoff_pairs",{}).get(key,(None,None))
                active.append((key,name(pair[0]) if pair[0] else "Da definire",
                               name(pair[1]) if pair[1] else "Da definire","playoffs"))
        now=time.time()
        for gid,white,black,target in active:
            clock=self.clock_data(gid)
            started_at=clock.get("started_at")
            if not clock.get("started") or not started_at or clock.get("overlong_alerted"):
                continue
            duration=max(0.0,now-float(started_at))
            if duration>=threshold:
                clock["overlong_alerted"]=True
                minutes=int(duration//60)
                self.record_operational_alert(
                    "Partita ancora in corso oltre la durata prevista",
                    f"{gid} · {white} vs {black} · attiva da circa {minutes} minuti.",
                    "warning",target,f"overlong:{gid}:{int(float(started_at))}"
                )

    def tick_clocks(self):
        self.check_long_match_alerts()
        changed=False; timed_out=[]
        for gid,_,white,black in GAMES:
            clock=self.clock_data(gid)
            if not clock.get("started") or self.results.get(gid): continue
            side,remaining,elapsed=self._advance_clock(gid)
            if elapsed>0.01: changed=True
            if remaining<=0:
                timed_out.append((gid,"0-1" if side=="white" else "1-0"))
        for key in ("sf1","sf2","final","third"):
            clock=self.clock_data(key)
            if not clock.get("started") or self.playoff_results.get(key): continue
            side,remaining,elapsed=self._advance_clock(key,clock.get("side_to_move","white"))
            if elapsed>0.01: changed=True
            if remaining<=0:
                timed_out.append((key,"0-1" if side=="white" else "1-0"))
        for gid,result in timed_out:
            self.clock_data(gid)["started"]=False
            self._clock_runtime.pop(gid,None)
            if gid in ("sf1","sf2","final","third"):
                self.set_playoff_result(gid,result,detail="Caduta della bandierina · tempo esaurito")
            else:
                board=self.get_board(gid)
                flagged_side=chess.WHITE if result=="0-1" else chess.BLACK
                opponent=not flagged_side
                if board.has_insufficient_material(opponent):
                    result="1/2-1/2"
                self.set_result(gid,result,confirm=False,detail="Caduta della bandierina · tempo esaurito",termination="time forfeit")
        if changed:
            self.clock_ticks+=1
            for card in getattr(self,"live_cards",[]): card.refresh_clock()
            if hasattr(self,"playoff_cards"): self.refresh_playoffs()
            if self.broadcast and self.broadcast.isVisible(): self.broadcast.refresh_from_app()
            if time.monotonic()-self._last_clock_persist>=5.0:
                self._last_clock_persist=time.monotonic()
                self.save_recovery()

    def start_playoff_clock(self,key):
        if self.playoff_results.get(key): return
        clock=self.clock_data(key)
        clock["started"]=True
        clock["started_at"]=clock.get("started_at") or time.time()
        clock.setdefault("overlong_alerted",False)
        clock.setdefault("side_to_move","white")
        clock["last_wall"]=time.time(); self._clock_runtime[key]=time.monotonic()
        self.log_operation("Orologio playoff avviato",key,"fermo","30+10")
        self.save(); self.save_recovery(); self.refresh_playoffs()
    def switch_playoff_clock(self,key):
        if self.playoff_results.get(key): return
        clock=self.clock_data(key)
        if not clock.get("started"): return
        side,remaining,_=self._advance_clock(key,clock.get("side_to_move","white"))
        if remaining<=0:
            self.tick_clocks(); return
        clock[side]=float(clock[side])+10
        clock["side_to_move"]="black" if side=="white" else "white"
        self.log_operation("Mossa playoff",key,side,clock["side_to_move"],"+10 secondi")
        self.save(); self.save_recovery(); self.refresh_playoffs()
    def playoff_clock_text(self,key):
        clock=self.clock_data(key)
        def fmt(seconds):
            seconds=max(0,int(seconds)); return f"{seconds//60:02d}:{seconds%60:02d}"
        return f"BIANCO {fmt(math.ceil(clock['white']))} · NERO {fmt(math.ceil(clock['black']))} · TOCCA A {clock.get('side_to_move','white').upper()}"
    def log_operation(self,action,entity,before,after,detail=""):
        self.audit_log.append({"time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "referee":self.referee,"action":action,"entity":str(entity),
            "before":str(before),"after":str(after),"detail":str(detail)})
        self._odds_cache_key=None
        if hasattr(self, "audit_events_layout"):
            self.refresh_audit()

    def add_match_note(self,gid,text,kind="Nota"):
        text=text.strip()
        if not text: return
        self.match_notes.setdefault(gid,[]).append({"time":datetime.now().strftime("%d/%m/%Y %H:%M"),
            "referee":self.referee,"kind":kind,"text":text})
        self.log_operation(kind,gid,"",text)
        self.save(); self.statusBar().showMessage("Annotazione arbitrale salvata.",2500)
    def show_match_notes(self,gid):
        notes=self.match_notes.get(gid,[])
        if not notes:
            QMessageBox.information(self,"Note partita",f"Nessuna nota o incidente registrato per {gid}."); return
        dialog=QDialog(self); dialog.setWindowTitle(f"Note arbitro · {gid}"); dialog.resize(620,420)
        layout=QVBoxLayout(dialog); content=QListWidget()
        for item in notes:
            content.addItem(f"{item.get('time','')} · {item.get('kind','Nota')} · {item.get('referee','')}\n{item.get('text','')}")
        layout.addWidget(content)
        close=QPushButton("CHIUDI"); close.clicked.connect(dialog.accept)
        layout.addWidget(close,0,Qt.AlignmentFlag.AlignRight); dialog.exec()

    def prompt_match_note(self,gid):
        kind,ok=QInputDialog.getItem(self,"Tipo annotazione","Classifica l'annotazione:",["Nota arbitrale","Incidente"],0,False)
        if not ok: return
        text,ok=QInputDialog.getMultiLineText(self,"Nota / incidente",
            f"Partita {gid} · arbitro: {self.referee or 'non indicato'}","")
        if ok: self.add_match_note(gid,text,kind)
    def raw_stats(self):
        pts={p:0.0 for p in PLAYERS}; played={p:0 for p in PLAYERS}
        wins={p:0 for p in PLAYERS}; draws={p:0 for p in PLAYERS}; losses={p:0 for p in PLAYERS}
        for gid,r,w,b in GAMES:
            result=self.results.get(gid)
            if not result or result=="VOID": continue
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
        """Art. 8: H2H only for two tied players, then Sonneborn-Berger, then wins."""
        raw,_,wins,_,_=self.raw_stats()
        penalties=self.penalty_points()
        group_ids=list(group or PLAYERS.keys())
        direct=0.0
        if len(group_ids)==2:
            opponent=next((x for x in group_ids if x!=p),None)
            for gid,_,white,black in GAMES:
                if {white,black}!={p,opponent}:
                    continue
                result=self.results.get(gid)
                if result in (None,"VOID"):
                    break
                if (result=="1-0" and p==white) or (result=="0-1" and p==black):
                    direct=1.0
                elif result=="1/2-1/2":
                    direct=0.5
                else:
                    direct=0.0
                break
        sonneborn=0.0
        for gid,_,white,black in GAMES:
            result=self.results.get(gid)
            if result in (None,"VOID") or p not in (white,black):
                continue
            opponent=black if p==white else white
            opponent_points=raw[opponent]+penalties[opponent]
            score=1.0 if (result=="1-0" and p==white) or (result=="0-1" and p==black) else (0.5 if result=="1/2-1/2" else 0.0)
            sonneborn += opponent_points*score
        return (direct,sonneborn,wins[p])

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
            group.sort(key=lambda row:(tuple(-v for v in self.tie_break_value(row["id"],group_ids)),ORDER.index(row["id"])))
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
        root = QWidget()
        root.setObjectName("AppRoot")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 16, 18, 12)
        outer.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(14)
        logo = LogoWidget(48, 52)
        header.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        brand = QVBoxLayout()
        brand.setSpacing(1)
        title = QLabel("COPPA DEI 5 RE")
        title.setObjectName("BrandTitle")
        eyebrow = QLabel("TOURNAMENT CONTROL ROOM")
        eyebrow.setObjectName("Eyebrow")
        brand.addWidget(title)
        brand.addWidget(eyebrow)
        header.addLayout(brand)
        header.addStretch(1)

        saved = QLabel("●  OFFLINE  ·  SALVATAGGIO AUTOMATICO")
        saved.setObjectName("SavedBadge")
        header.addWidget(saved)
        timing = QLabel("QUALIFICAZIONE 15+3   ·   PLAYOFF 30+10")
        timing.setObjectName("Muted")
        header.addWidget(timing)
        self.notification_button = QPushButton("AVVISI · 0")
        self.notification_button.setToolTip("Apri il centro notifiche")
        self.notification_button.clicked.connect(self.open_notifications)
        header.addWidget(self.notification_button)
        palette = QPushButton("⌕  CERCA  ·  CTRL K")
        palette.clicked.connect(self.open_command_palette)
        header.addWidget(palette)
        stream = QPushButton("◉  VISTA STREAMING")
        stream.setObjectName("PrimaryButton")
        stream.clicked.connect(self.open_broadcast)
        header.addWidget(stream)
        outer.addLayout(header)

        workspace = QHBoxLayout()
        workspace.setSpacing(14)
        self.nav = SideNav(LogoWidget(42, 46), "Coppa dei 5 Re", "CONTROL ROOM")
        self.nav.add_group("TORNEO")
        nav_items = [
            ("dashboard", "Dashboard", "dashboard"),
            ("live", "Live arena", "board"),
            ("draw", "Estrazione", "shuffle"),
            ("calendar", "Calendario", "calendar"),
            ("standings", "Classifica", "standings"),
            ("odds", "Quote e statistiche", "chart"),
            ("penalties", "Penalità", "flag"),
            ("playoffs", "Playoff", "trophy"),
        ]
        for key, text, icon_name in nav_items:
            self.nav.add_item(key, text, icon_name)
        pro_items = [
            ("players", "Giocatori", "user"),
            ("compare", "Confronto", "versus"),
            ("openings", "Aperture", "chart"),
            ("health", "Health Check", "info"),
            ("communications", "Comunicazioni", "mail"),
        ]
        self.nav.add_group("ANALISI E STRUMENTI")
        for key, text, icon_name in pro_items:
            self.nav.add_item(key, text, icon_name)
        self.nav.add_group("ARCHIVIO E CONTROLLO")
        archive_items = [
            ("history", "Storico edizioni", "trophy"),
            ("archive", "Archivio", "archive"),
            ("h2h", "Testa a testa", "versus"),
            ("incidents", "Verbali incidenti", "file"),
            ("audit", "Registro operazioni", "log"),
            ("settings", "Impostazioni", "settings"),
        ]
        for key, text, icon_name in archive_items:
            self.nav.add_item(key, text, icon_name)
        self.nav.finish()

        self.tabs = QStackedWidget()
        # Keep page construction in exactly the same order as nav_items + pro_items + archive_items.
        # A mismatch here routes "Testa a testa" to incident reports and vice versa.
        pages = [
            self.build_dashboard(), self.build_live(), self.build_draw_page(),
            self.build_calendar(), self.build_standings(), self.build_odds(),
            self.build_penalties(), self.build_playoffs(),
            self.build_players(), self.build_compare(), self.build_openings(), self.build_health(), self.build_communications(),
            self.build_history(), self.build_archive(), self.build_h2h(), self.build_incidents(),
            self.build_audit(), self.build_settings(),
        ]
        self._page_keys = [item[0] for item in nav_items + pro_items + archive_items]
        for page in pages:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            page.setMinimumWidth(0)
            scroll.setWidget(page)
            self.tabs.addWidget(scroll)

        self.nav.currentChanged.connect(self._navigate_to)
        self._page_fades, self._page_animations = {}, {}
        self._card_glow = CardGlowController(root)
        self.nav.set_current("dashboard")
        workspace.addWidget(self.nav)
        workspace.addWidget(self.tabs, 1)
        outer.addLayout(workspace, 1)

        footer = QLabel("COPPA DEI 5 RE   /   DATI LOCALI SU QUESTO PC   ·   CTRL+S SALVA   ·   CTRL+E ESPORTA PGN   ·   CTRL+SHIFT+B BACKUP")
        footer.setObjectName("Footnote")
        outer.addWidget(footer)
        self.setCentralWidget(root)
        self.setMinimumSize(920, 640)
        self.setStatusBar(ToastStatusBar())
        self.header_saved = saved
        self.header_timing = timing
        self.statusBar().showMessage("Pronto · seleziona una sezione per iniziare.")
        self._nav_keys = self._page_keys
        self.setAccessibleName("Coppa dei 5 Re · Control Room")
        self.setAccessibleDescription("Gestione locale del torneo, delle partite, della classifica e del registro arbitrale.")
        for button in self.findChildren(QPushButton):
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            if not button.accessibleName():
                button.setAccessibleName(button.text().replace("&", "").strip() or "Azione")
            if not button.accessibleDescription():
                button.setAccessibleDescription(button.toolTip() or button.accessibleName())
        for field in self.findChildren(QLineEdit):
            if not field.accessibleName():
                field.setAccessibleName(field.placeholderText() or "Campo di testo")
        for table in self.findChildren(QTableWidget):
            table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "nav"):
            return
        compact = self.width() < 1180
        if self.nav._collapsed != compact:
            self.nav.set_collapsed(compact)
        if hasattr(self, "header_timing"):
            self.header_timing.setVisible(self.width() >= 1240)
        if hasattr(self, "header_saved"):
            self.header_saved.setVisible(self.width() >= 1360)

    def _navigate_to(self, key):
        if key in self._nav_keys:
            index = self._nav_keys.index(key)
            self.tabs.setCurrentIndex(index)
            if key == "audit":
                self.refresh_audit()
            page = self.tabs.widget(index)
            effect = self._page_fades.get(page)
            if effect is None:
                effect = QGraphicsOpacityEffect(page)
                effect.setOpacity(1.0)
                page.setGraphicsEffect(effect)
                self._page_fades[page] = effect
            previous = self._page_animations.pop(page, None)
            if previous:
                previous.stop()
            effect.setOpacity(0.0)
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(190)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            self._page_animations[page] = animation
            animation.start()

    def build_dashboard(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(26, 24, 26, 30)
        root.setSpacing(18)

        hero = QFrame()
        hero.setObjectName("CardAccent")
        hero_lay = QHBoxLayout(hero)
        hero_lay.setContentsMargins(22, 18, 22, 18)
        hero_lay.setSpacing(18)
        hero_lay.addWidget(LogoWidget(104, 112))
        hero_text = QVBoxLayout()
        hero_text.setSpacing(5)
        title = ui_label("Il torneo, sotto controllo.", "h1")
        subtitle = ui_label("Panoramica in tempo reale della Coppa dei 5 Re.", "lead")
        hero_text.addWidget(title)
        hero_text.addWidget(subtitle)
        hero_text.addStretch(1)
        hero_lay.addLayout(hero_text, 1)
        root.addWidget(hero)
        self.dashboard_detail = ui_label("Arbitro non impostato", "muted")
        root.addWidget(self.dashboard_detail)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.dashboard_tiles = {
            "done": StatTile("PARTITE CONCLUSE", "check"),
            "live": StatTile("IN CORSO", "clock"),
            "pending": StatTile("DA DISPUTARE", "calendar"),
            "retired": StatTile("RITIRI REGISTRATI", "user"),
        }
        for tile in self.dashboard_tiles.values():
            metrics.addWidget(tile, 1)
        root.addLayout(metrics)

        results_card = Card(
            "Ultimi risultati",
            "Le partite concluse più di recente. Ogni nuovo risultato registrato compare qui automaticamente.",
            padding=16,
            spacing=8
        )
        self.dashboard_results_table=QTableWidget(0,5)
        self.dashboard_results_table.setHorizontalHeaderLabels(["TURNO","PARTITA","BIANCO","NERO","RISULTATO"])
        style_table(self.dashboard_results_table,row_height=38,selectable=False)
        self.dashboard_results_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        for column in (0,2,3,4):
            self.dashboard_results_table.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeMode.ResizeToContents)
        self.dashboard_results_table.setMaximumHeight(238)
        self.dashboard_results_table.cellDoubleClicked.connect(self.open_dashboard_result)
        results_card.body.addWidget(table_card(self.dashboard_results_table))
        self.dashboard_results_empty=ui_label(
            "Nessun risultato registrato. Inserisci un esito dal Calendario o dalla Live Arena: verrà mostrato qui.",
            "muted",
            wrap=True
        )
        self.dashboard_results_empty.setMinimumHeight(42)
        results_card.body.addWidget(self.dashboard_results_empty)
        root.addWidget(results_card)

        progress_card = Card("Avanzamento del girone", "Completamento delle dieci partite di qualificazione.")
        self.dashboard_progress = QProgressBar()
        self.dashboard_progress.setRange(0, 100)
        self.dashboard_progress.setTextVisible(True)
        self.dashboard_progress.setFormat("%p% completato")
        self.dashboard_progress.setFixedHeight(13)
        progress_card.body.addWidget(self.dashboard_progress)
        self.dashboard_progress_detail = ui_label("", "caption")
        progress_card.body.addWidget(self.dashboard_progress_detail)
        root.addWidget(progress_card)

        snapshot = QHBoxLayout()
        snapshot.setSpacing(12)
        upcoming = Card("Prossimi incontri", "Partite attive e prossime da disputare.")
        self.dashboard_next_labels = []
        self.dashboard_next_matches = []
        for _ in range(3):
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 6)
            row_layout.setSpacing(3)
            match = MatchLine()
            status = ui_label("In attesa del calendario.", "caption", wrap=True)
            row_layout.addWidget(match)
            row_layout.addWidget(status)
            self.dashboard_next_matches.append(match)
            self.dashboard_next_labels.append(status)
            upcoming.body.addWidget(row)
        ranking = Card("Podio provvisorio", "Classifica netta aggiornata dopo ogni risultato.")
        self.dashboard_ranking_labels = []
        self.dashboard_ranking_forms = []
        for _ in range(3):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 3, 0, 3)
            row_layout.setSpacing(8)
            item = ui_label("—", "body", wrap=True)
            form = FormStrip()
            row_layout.addWidget(item, 1)
            row_layout.addWidget(form, 0)
            self.dashboard_ranking_labels.append(item)
            self.dashboard_ranking_forms.append(form)
            ranking.body.addWidget(row)
        snapshot.addWidget(upcoming, 3)
        snapshot.addWidget(ranking, 2)
        root.addLayout(snapshot)

        chart_card = Card("Andamento dei punti", "Punti cumulativi per round; le penalità restano separate e sono incluse nella classifica netta.")
        self.dashboard_chart = LineChart()
        self.dashboard_chart.setMinimumHeight(230)
        chart_card.body.addWidget(self.dashboard_chart)
        root.addWidget(chart_card)

        lower = QHBoxLayout()
        lower.setSpacing(12)
        actions = Card("Operazioni rapide", "Esportazione e sicurezza dei dati.")
        action_grid = QGridLayout()
        action_grid.setHorizontalSpacing(8)
        action_grid.setVerticalSpacing(8)
        items = [
            ("ESPORTA PGN TORNEO", self.export_all_pgn),
            ("CLASSIFICA CSV", self.export_standings_csv),
            ("CLASSIFICA PDF", self.export_standings_pdf),
            ("REPORT UFFICIALE PDF", self.export_tournament_report_pdf),
            ("CREA BACKUP", self.export_backup),
            ("RIPRISTINA BACKUP", self.restore_backup),
        ]
        for i, (text, callback) in enumerate(items):
            btn = QPushButton(text)
            btn.setObjectName("PrimaryButton" if i == 0 else "")
            btn.setToolTip("Esporta o salva una copia dei dati del torneo.")
            btn.clicked.connect(callback)
            action_grid.addWidget(btn, i // 2, i % 2)
        actions.body.addLayout(action_grid)
        lower.addWidget(actions, 1)

        referee = Card("Azioni arbitrali", "Seleziona una partita per registrare una patta concordata, un abbandono o una decisione arbitrale.")
        self.dashboard_match_combo = QComboBox()
        for gid, rnd, white, black in GAMES:
            self.dashboard_match_combo.addItem(f"Round {rnd} · {name(white)} – {name(black)}", gid)
        referee.body.addWidget(self.dashboard_match_combo)
        row = QHBoxLayout()
        draw = QPushButton("PATTA CONCORDATA")
        draw.clicked.connect(lambda: self.offer_draw(self.dashboard_match_combo.currentData()))
        resign = QPushButton("ABBANDONO")
        resign.clicked.connect(lambda: self.resign_game(self.dashboard_match_combo.currentData()))
        force = QPushButton("FORZA RISULTATO")
        force.setObjectName("PrimaryButton")
        force.clicked.connect(lambda: self.force_game_result(self.dashboard_match_combo.currentData()))
        row.addWidget(draw)
        row.addWidget(resign)
        row.addWidget(force)
        referee.body.addLayout(row)
        lower.addWidget(referee, 1)
        root.addLayout(lower)
        root.addStretch(1)
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
        style_table(self.archive_table, row_height=46, selectable=True)
        layout.addWidget(table_card(self.archive_table),1)
        row=QHBoxLayout(); allpgn=QPushButton("ESPORTA TUTTO IL TORNEO IN PGN")
        allpgn.setObjectName("PrimaryButton"); allpgn.clicked.connect(self.export_all_pgn); row.addWidget(allpgn)
        one=QPushButton("ESPORTA PARTITA SELEZIONATA")
        one.clicked.connect(self.export_selected_archive_game); row.addWidget(one)
        analyze=QPushButton("ANALIZZA POSIZIONI CON STOCKFISH")
        analyze.clicked.connect(self.analyze_selected_archive_game); row.addWidget(analyze); row.addStretch()
        layout.addLayout(row); return page

    def history_player_names(self):
        return {player:name(player) for player in ORDER}

    def archive_edition_state(self,title,state=None):
        payload=state if state is not None else self.state_payload()
        schedule=payload.get("schedule",[])
        if schedule:
            parsed=[(item["id"],int(item["round"]),item["white"],item["black"]) for item in schedule]
            validate_schedule(parsed)
        return archive_edition(storage_path(),payload,title,ORDER,self.history_player_names())

    def archive_current_edition(self):
        default=f"Coppa dei 5 Re · {datetime.now().strftime('%Y-%m-%d')}"
        title,ok=QInputDialog.getText(self,"Archivia edizione","Nome dell'edizione:",text=default)
        if not ok or not title.strip():
            return
        try:
            target=self.archive_edition_state(title)
            self.log_operation("Edizione archiviata",title,"","Copia storica indipendente",target.name)
            self.save(automatic_snapshot=False)
            self.refresh_history()
            self.statusBar().showMessage(f"Edizione archiviata: {target.name}",4000)
        except Exception as exc:
            QMessageBox.warning(self,"Edizione non archiviata",str(exc))

    def import_historical_edition(self):
        source,_=QFileDialog.getOpenFileName(self,"Importa backup di un'edizione","","Backup torneo (*.json)")
        if not source:
            return
        title,ok=QInputDialog.getText(self,"Nome edizione importata",
            "Come vuoi identificare questa edizione:",text=Path(source).stem)
        if not ok or not title.strip():
            return
        try:
            raw=json.loads(Path(source).read_text(encoding="utf-8"))
            if isinstance(raw,dict) and isinstance(raw.get("state"),dict):
                state=decode_document(raw["state"])
            else:
                state=decode_document(raw)
            schedule=state.get("schedule",[])
            if not schedule:
                raise ValueError("Il backup non contiene un calendario.")
            parsed=[(item["id"],int(item["round"]),item["white"],item["black"]) for item in schedule]
            validate_schedule(parsed)
            target=import_edition_file(storage_path(),source,title,ORDER,self.history_player_names())
            self.log_operation("Edizione storica importata",title,"","Backup importato",Path(source).name)
            self.save(automatic_snapshot=False)
            self.refresh_history()
            self.statusBar().showMessage(f"Edizione importata: {target.name}",4000)
        except Exception as exc:
            QMessageBox.warning(self,"Importazione non riuscita",f"Il backup non è stato aggiunto: {exc}")

    def build_history(self):
        page=QWidget()
        layout=QVBoxLayout(page)
        layout.setContentsMargins(26,24,26,30)
        layout.setSpacing(14)
        layout.addWidget(ui_label("Storico delle edizioni","h1"))
        layout.addWidget(ui_label(
            "Archivia ogni torneo concluso o importa backup precedenti. L'albo d'oro e le statistiche cumulative "
            "si aggiornano usando i risultati conservati nelle singole edizioni.",
            "lead",wrap=True))
        stats=QHBoxLayout()
        self.history_stats=[
            StatTile("EDIZIONI ARCHIVIATE","archive"),
            StatTile("TITOLI ASSEGNATI","trophy"),
            StatTile("PIAZZAMENTI SUL PODIO","medal"),
        ]
        for tile in self.history_stats:
            stats.addWidget(tile,1)
        layout.addLayout(stats)

        archive=Card("Archivio delle edizioni",
            "Ogni edizione viene salvata in un file separato e non modifica il torneo attualmente aperto.")
        toolbar=QHBoxLayout()
        archive_btn=QPushButton("ARCHIVIA TORNEO CORRENTE")
        archive_btn.setObjectName("PrimaryButton")
        archive_btn.clicked.connect(self.archive_current_edition)
        import_btn=QPushButton("IMPORTA BACKUP PRECEDENTE")
        import_btn.clicked.connect(self.import_historical_edition)
        refresh_btn=QPushButton("AGGIORNA")
        refresh_btn.clicked.connect(self.refresh_history)
        toolbar.addWidget(archive_btn); toolbar.addWidget(import_btn)
        toolbar.addStretch(1); toolbar.addWidget(refresh_btn)
        archive.body.addLayout(toolbar)
        self.history_edition_table=QTableWidget(0,6)
        self.history_edition_table.setHorizontalHeaderLabels(
            ["DATA","EDIZIONE","CAMPIONE","PARTITE","GIOCATORI","STATO"])
        self.history_edition_table.verticalHeader().setVisible(False)
        self.history_edition_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_edition_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_edition_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_edition_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        for col in (0,2,3,4,5):
            self.history_edition_table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.ResizeToContents)
        style_table(self.history_edition_table,row_height=44,selectable=True)
        self.history_edition_table.cellClicked.connect(self.show_historical_edition)
        archive.body.addWidget(table_card(self.history_edition_table))
        self.history_detail=ui_label(
            "Seleziona un'edizione per vedere classifica, podio e risultati.",
            "muted",wrap=True)
        archive.body.addWidget(self.history_detail)
        layout.addWidget(archive,2)

        career=Card("Albo d'oro e statistiche cumulative",
            "Ordinamento per titoli, podi, partecipazioni e punti netti accumulati.")
        export=QPushButton("ESPORTA STATISTICHE CSV")
        export.clicked.connect(self.export_career_stats_csv)
        career.body.addWidget(export,0,Qt.AlignmentFlag.AlignRight)
        self.history_career_table=QTableWidget(0,10)
        self.history_career_table.setHorizontalHeaderLabels(
            ["GIOCATORE","EDIZIONI","TITOLI","PODI","MIGLIOR","G","V","X","P","PUNTI NETTI"])
        self.history_career_table.verticalHeader().setVisible(False)
        self.history_career_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_career_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_career_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for col in range(1,10):
            self.history_career_table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.ResizeToContents)
        style_table(self.history_career_table,row_height=42,selectable=True)
        career.body.addWidget(table_card(self.history_career_table))
        layout.addWidget(career,2)
        return page

    def refresh_history(self):
        if not hasattr(self,"history_edition_table"):
            return
        editions=list_editions(storage_path(),ORDER)
        self._history_cache=editions
        self.history_edition_table.setRowCount(len(editions))
        for row,edition in enumerate(editions):
            champion=edition.get("champion")
            status="COMPLETA" if edition.get("is_complete") else "PARZIALE"
            date=str(edition.get("created_at","")).replace("T"," ")
            values=[date,edition.get("title",""),
                    name(champion) if champion else "Non assegnato",
                    f"{edition.get('completed',0)}/10",
                    str(edition.get("players",0)),status]
            for col,value in enumerate(values):
                cell=QTableWidgetItem(str(value))
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setData(Qt.ItemDataRole.UserRole,edition.get("id"))
                self.history_edition_table.setItem(row,col,cell)
        career=career_statistics(editions,ORDER,self.history_player_names())
        self.history_career_table.setRowCount(len(career))
        for row,item in enumerate(career):
            values=[item["name"],item["editions"],item["titles"],item["podiums"],
                    f"{item['best']}°" if item["best"] else "—",
                    item["played"],item["wins"],item["draws"],item["losses"],f"{item['points']:.1f}"]
            for col,value in enumerate(values):
                cell=QTableWidgetItem(str(value))
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.history_career_table.setItem(row,col,cell)
        titles=sum(1 for edition in editions if edition.get("champion"))
        podiums=sum(sum(1 for player in edition.get("podium",[])[:3] if player) for edition in editions)
        self.history_stats[0].set(str(len(editions)),"Edizioni conservate")
        self.history_stats[1].set(str(titles),"Vincitori ufficiali")
        self.history_stats[2].set(str(podiums),"Podi assegnati")
        if not editions:
            self.history_detail.setText(
                "Nessuna edizione archiviata. Puoi archiviare il torneo corrente o importare un backup JSON.")
        elif self.history_edition_table.currentRow()<0:
            self.history_detail.setText("Seleziona un'edizione per visualizzare il dettaglio.")

    def show_historical_edition(self,row,column=0):
        if not 0<=row<len(getattr(self,"_history_cache",[])):
            return
        edition=self._history_cache[row]
        date=str(edition.get("created_at","")).replace("T"," ")
        lines=[f"{edition.get('title','Edizione')} · {date}",
               f"Partite valide: {edition.get('completed',0)} · annullate: {edition.get('voided',0)}"]
        podium=edition.get("podium",[])
        if podium[0]:
            lines.append("Podio ufficiale: "+" · ".join(
                f"{index+1}° {name(player)}" for index,player in enumerate(podium[:3]) if player))
        else:
            lines.append("Podio ufficiale non assegnato: i playoff non risultano conclusi.")
        lines.append("Classifica del girone:")
        for position,item in enumerate(edition.get("standings",[]),1):
            player_name=edition.get("player_rows",{}).get(item["id"],{}).get("name",name(item["id"]))
            lines.append(f"{position}° {player_name} · {item['points']:.1f} punti "
                         f"({item['wins']}V {item['draws']}X {item['losses']}P)")
        self.history_detail.setText("\n".join(lines))

    def export_career_stats_csv(self):
        path,_=QFileDialog.getSaveFileName(self,"Esporta statistiche storiche","Statistiche-Storiche-C5R.csv","CSV (*.csv)")
        if not path:
            return
        editions=list_editions(storage_path(),ORDER)
        rows=career_statistics(editions,ORDER,self.history_player_names())
        with open(path,"w",newline="",encoding="utf-8-sig") as stream:
            writer=csv.writer(stream,delimiter=";")
            writer.writerow(["Giocatore","Edizioni","Titoli","Podi","Miglior piazzamento","Partite","Vittorie","Patte","Sconfitte","Punti netti"])
            for item in rows:
                writer.writerow([item["name"],item["editions"],item["titles"],item["podiums"],item["best"] or "",
                                 item["played"],item["wins"],item["draws"],item["losses"],item["points"]])
        self.statusBar().showMessage("Statistiche storiche esportate in CSV.",3000)

    def build_incidents(self):
        page=QWidget()
        layout=QVBoxLayout(page)
        layout.setContentsMargins(26,24,26,30)
        layout.setSpacing(14)
        layout.addWidget(ui_label("Verbali degli incidenti", "h1"))
        layout.addWidget(ui_label(
            "Registra contestazioni, ritardi, irregolarità, problemi tecnici e decisioni arbitrali. "
            "Ogni verbale conserva autore, cronologia, stato, descrizione, provvedimento e documenti allegati.",
            "lead", wrap=True
        ))

        overview=QHBoxLayout()
        self.incident_stat_open=StatTile("APERTE","alert")
        self.incident_stat_review=StatTile("IN ESAME","clock")
        self.incident_stat_closed=StatTile("RISOLTE / ARCHIVIATE","check")
        for tile in (self.incident_stat_open,self.incident_stat_review,self.incident_stat_closed):
            overview.addWidget(tile,1)
        layout.addLayout(overview)

        filter_card=Card("Ricerca e filtri",padding=14,spacing=10)
        filter_row=QHBoxLayout()
        self.incident_search=QLineEdit()
        self.incident_search.setPlaceholderText("Cerca numero, partita, soggetto, oggetto o descrizione…")
        self.incident_category_filter=QComboBox()
        self.incident_category_filter.addItem("Tutte le categorie",None)
        for value in ("Contestazione","Ritardo","Irregolarità","Decisione arbitrale",
                      "Problema tecnico","Sicurezza / organizzazione","Altro"):
            self.incident_category_filter.addItem(value,value)
        self.incident_status_filter=QComboBox()
        self.incident_status_filter.addItem("Tutti gli stati",None)
        for value in ("Aperto","In esame","Risolto","Archiviato"):
            self.incident_status_filter.addItem(value,value)
        filter_row.addWidget(self.incident_search,2)
        filter_row.addWidget(self.incident_category_filter,1)
        filter_row.addWidget(self.incident_status_filter,1)
        filter_card.body.addLayout(filter_row)
        self.incident_search.textChanged.connect(self.refresh_incidents)
        self.incident_category_filter.currentIndexChanged.connect(self.refresh_incidents)
        self.incident_status_filter.currentIndexChanged.connect(self.refresh_incidents)
        layout.addWidget(filter_card)

        records=Card("Registro verbali","Seleziona una riga per aprire o modificare il verbale completo.")
        toolbar=QHBoxLayout()
        self.incident_count_label=ui_label("0 verbali", "caption")
        toolbar.addWidget(self.incident_count_label)
        toolbar.addStretch(1)
        create=QPushButton("NUOVO VERBALE")
        create.setObjectName("PrimaryButton")
        create.clicked.connect(self.create_incident_report)
        open_report=QPushButton("APRI / MODIFICA")
        open_report.clicked.connect(self.edit_selected_incident)
        export_pdf=QPushButton("ESPORTA VERBALE PDF")
        export_pdf.clicked.connect(self.export_selected_incident_pdf)
        export_csv=QPushButton("ESPORTA REGISTRO CSV")
        export_csv.clicked.connect(self.export_incidents_csv)
        toolbar.addWidget(create)
        toolbar.addWidget(open_report)
        toolbar.addWidget(export_pdf)
        toolbar.addWidget(export_csv)
        records.body.addLayout(toolbar)

        self.incident_table=QTableWidget(0,7)
        self.incident_table.setHorizontalHeaderLabels(
            ["N. / DATA","CATEGORIA","PARTITA / TURNO","SOGGETTI","OGGETTO","STATO","ALLEGATI"])
        self.incident_table.verticalHeader().setVisible(False)
        self.incident_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.incident_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.incident_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.incident_table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch)
        for col in (0,1,2,3,5,6):
            self.incident_table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.ResizeToContents)
        style_table(self.incident_table,row_height=44,selectable=True)
        self.incident_table.cellDoubleClicked.connect(lambda row,column:self.edit_incident_report(self._incident_id_at_row(row)))
        self.incident_table.itemSelectionChanged.connect(self.refresh_incident_detail)
        records.body.addWidget(table_card(self.incident_table))
        self.incident_detail=ui_label("Seleziona un verbale per visualizzarne il riepilogo.", "muted", wrap=True)
        records.body.addWidget(self.incident_detail)
        layout.addWidget(records,1)
        layout.addWidget(ui_label(
            f"Gli allegati sono copiati in {storage_path().parent / 'incidents'} e restano sul PC. "
            "Per trasferire i documenti su un altro computer, copia anche la cartella incidents insieme al backup.",
            "caption", wrap=True
        ))
        return page

    def incident_directory(self,report_id=None):
        root=storage_path().parent/"incidents"
        if report_id is None:
            root.mkdir(parents=True,exist_ok=True)
            return root
        safe_id=re.sub(r"[^A-Za-z0-9_-]","",str(report_id))
        if not safe_id or safe_id!=str(report_id):
            raise ValueError("Identificativo verbale non valido.")
        folder=root/safe_id
        folder.mkdir(parents=True,exist_ok=True)
        return folder

    def incident_attachment_path(self,relative_path):
        root=self.incident_directory().resolve()
        candidate=(storage_path().parent/str(relative_path)).resolve()
        if root not in candidate.parents:
            raise ValueError("Percorso allegato non valido.")
        return candidate

    def _incident_record(self,report_id):
        return next((item for item in self.incident_reports if item.get("id")==report_id),None)

    def _incident_id_at_row(self,row):
        if not hasattr(self,"incident_table") or row<0 or row>=self.incident_table.rowCount():
            return None
        item=self.incident_table.item(row,0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def selected_incident_id(self):
        if not hasattr(self,"incident_table"):
            return None
        rows=self.incident_table.selectionModel().selectedRows()
        return self._incident_id_at_row(rows[0].row()) if rows else None

    def create_incident_report(self):
        self.edit_incident_report(None)

    def edit_selected_incident(self):
        report_id=self.selected_incident_id()
        if not report_id:
            QMessageBox.information(self,"Nessun verbale selezionato","Seleziona prima un verbale dal registro.")
            return
        self.edit_incident_report(report_id)

    def save_incident_report(self,data,attachment_entries):
        report_id=data.get("id") or f"INC-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        old=self._incident_record(report_id)
        created_at=old.get("created_at") if old else datetime.now().isoformat(timespec="seconds")
        copied=[]
        final_attachments=[]
        folder=self.incident_directory(report_id)
        try:
            for entry in attachment_entries:
                source=entry.get("source")
                if source:
                    source_path=Path(source)
                    if not source_path.exists() or not source_path.is_file():
                        raise ValueError(f"Allegato non disponibile: {source_path}")
                    size=source_path.stat().st_size
                    if size>25*1024*1024:
                        raise ValueError(f"Il file {source_path.name} supera il limite di 25 MB per singolo allegato.")
                    base_name=re.sub(r'[<>:"/\\|?*\x00-\x1f]',"_",source_path.name).strip(" .") or "allegato"
                    dest=folder/base_name
                    counter=2
                    while dest.exists():
                        dest=folder/f"{Path(base_name).stem}_{counter}{Path(base_name).suffix}"
                        counter+=1
                    shutil.copy2(source_path,dest)
                    copied.append(dest)
                    relative=Path("incidents")/report_id/dest.name
                    final_attachments.append({"path":relative.as_posix(),"name":dest.name,"size":size})
                else:
                    relative=str(entry.get("path",""))
                    resolved=self.incident_attachment_path(relative)
                    final_attachments.append({
                        "path":relative,
                        "name":entry.get("name") or resolved.name,
                        "size":int(entry.get("size",resolved.stat().st_size if resolved.exists() else 0)),
                    })
            game_id=str(data.get("game_id",""))
            game_label=str(data.get("game_label",""))
            if game_id in ("sf1","sf2","final","third"):
                game_label=game_label or {"sf1":"Playoff · Semifinale 1","sf2":"Playoff · Semifinale 2",
                    "final":"Playoff · Finale","third":"Playoff · 3° / 4° posto"}.get(game_id,game_id)
            elif game_id:
                match=next((item for item in GAMES if item[0]==game_id),None)
                if match:
                    game_label=game_label or f"Round {match[1]} · {game_id} · {name(match[2])} – {name(match[3])}"
            else:
                game_label="Generale / non associato"
            if old and old.get("game_id")==game_id and old.get("game_label"):
                game_label=old["game_label"]
            record={
                "id":report_id,
                "created_at":created_at,
                "updated_at":datetime.now().isoformat(timespec="seconds"),
                "event_at":str(data.get("event_at") or created_at),
                "category":str(data.get("category","Altro")),
                "game_id":game_id,
                "game_label":game_label,
                "participants":str(data.get("participants","")).strip(),
                "summary":str(data.get("summary","")).strip(),
                "description":str(data.get("description","")).strip(),
                "decision":str(data.get("decision","")).strip(),
                "status":str(data.get("status","Aperto")),
                "referee":str(data.get("referee") or self.referee or "Non indicato"),
                "attachments":final_attachments,
            }
            if not record["summary"]:
                raise ValueError("Inserisci un oggetto breve per il verbale.")
            if not record["description"]:
                raise ValueError("Inserisci una descrizione dei fatti.")
            if old:
                index=self.incident_reports.index(old)
                self.incident_reports[index]=record
                action="Verbale incidente aggiornato"
                before=f"{old.get('status','')} · {old.get('summary','')}"
            else:
                self.incident_reports.append(record)
                action="Verbale incidente creato"
                before="—"
            # Evidence files are retained when detached from a report: undo/redo and
            # older snapshots may still reference them. The report stores only its
            # currently linked attachments.
            self.log_operation(action,report_id,before,
                f"{record['status']} · {record['summary']}",
                f"{record['category']} · {record['game_id'] or 'Generale'} · {record['participants']}")
            self.save()
            self.refresh_incidents()
            return record
        except Exception:
            for path in copied:
                path.unlink(missing_ok=True)
            if not old:
                try:
                    if folder.exists() and not any(folder.iterdir()):
                        folder.rmdir()
                except OSError:
                    pass
            raise

    def edit_incident_report(self,report_id=None):
        existing=self._incident_record(report_id) if report_id else None
        dialog=QDialog(self)
        dialog.setWindowTitle("Modifica verbale incidente" if existing else "Nuovo verbale incidente")
        dialog.resize(780,820)
        root=QVBoxLayout(dialog)
        root.setContentsMargins(22,20,22,18)
        root.setSpacing(12)
        header=ui_label(
            f"{existing.get('id')} · creato {existing.get('created_at','').replace('T',' ')}" if existing
            else f"Nuovo verbale · {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            "caption")
        root.addWidget(header)

        grid=QGridLayout()
        category=QComboBox()
        categories=["Contestazione","Ritardo","Irregolarità","Decisione arbitrale",
                    "Problema tecnico","Sicurezza / organizzazione","Altro"]
        category.addItems(categories)
        if existing and existing.get("category") in categories:
            category.setCurrentText(existing["category"])
        event_at=QDateTimeEdit(QDateTime.currentDateTime(),dialog)
        event_at.setCalendarPopup(True)
        event_at.setDisplayFormat("dd/MM/yyyy HH:mm")
        if existing and existing.get("event_at"):
            parsed_event=QDateTime.fromString(existing["event_at"],Qt.DateFormat.ISODate)
            if parsed_event.isValid():
                event_at.setDateTime(parsed_event)
        game_combo=QComboBox()
        game_combo.addItem("Generale / non associato","")
        for gid,rnd,white,black in GAMES:
            game_combo.addItem(f"Round {rnd} · {gid} · {name(white)} – {name(black)}",gid)
        for key,label in (("sf1","Semifinale 1"),("sf2","Semifinale 2"),("third","3° / 4° posto"),("final","Finale")):
            game_combo.addItem(f"Playoff · {label}",key)
        if existing:
            idx=game_combo.findData(existing.get("game_id",""))
            if idx>=0: game_combo.setCurrentIndex(idx)
        status=QComboBox()
        status.addItems(["Aperto","In esame","Risolto","Archiviato"])
        if existing:
            status.setCurrentText(existing.get("status","Aperto"))
        participants=QLineEdit(existing.get("participants","") if existing else "")
        participants.setPlaceholderText("Nomi delle persone coinvolte")
        summary=QLineEdit(existing.get("summary","") if existing else "")
        summary.setPlaceholderText("Es. Contestazione sul risultato della partita")
        grid.addWidget(ui_label("CATEGORIA","field"),0,0)
        grid.addWidget(category,0,1)
        grid.addWidget(ui_label("STATO","field"),0,2)
        grid.addWidget(status,0,3)
        grid.addWidget(ui_label("DATA E ORA DELL'EVENTO","field"),1,0)
        grid.addWidget(event_at,1,1,1,3)
        grid.addWidget(ui_label("PARTITA / TURNO","field"),2,0)
        grid.addWidget(game_combo,2,1,1,3)
        grid.addWidget(ui_label("PERSONE COINVOLTE","field"),3,0)
        grid.addWidget(participants,3,1,1,3)
        grid.addWidget(ui_label("OGGETTO","field"),4,0)
        grid.addWidget(summary,4,1,1,3)
        root.addLayout(grid)

        description=QPlainTextEdit()
        description.setPlaceholderText("Descrivi i fatti in ordine cronologico: luogo, orari, persone presenti, elementi oggettivi e dichiarazioni.")
        description.setPlainText(existing.get("description","") if existing else "")
        description.setMinimumHeight(130)
        root.addWidget(ui_label("DESCRIZIONE DEI FATTI","field"))
        root.addWidget(description)
        decision=QPlainTextEdit()
        decision.setPlaceholderText("Decisione del direttore di gara, motivazione, eventuali sanzioni e azioni successive.")
        decision.setPlainText(existing.get("decision","") if existing else "")
        decision.setMinimumHeight(100)
        root.addWidget(ui_label("DECISIONE / PROVVEDIMENTO ARBITRALE","field"))
        root.addWidget(decision)

        root.addWidget(ui_label("ALLEGATI (PDF, FOTO, DOCUMENTI, FILE)","field"))
        attachments=QListWidget()
        pending=existing.get("attachments",[])[:] if existing else []
        for item in pending:
            try:
                file_path=self.incident_attachment_path(item.get("path",""))
                label=f"{item.get('name',file_path.name)} · {item.get('size',0)/1024:.0f} KB"
                if not file_path.exists(): label+=" · FILE NON TROVATO"
            except Exception:
                label=f"{item.get('name','Allegato')} · PERCORSO NON VALIDO"
            widget_item=QListWidgetItem(label)
            widget_item.setData(Qt.ItemDataRole.UserRole,{"path":item.get("path",""),"name":item.get("name",""),"size":item.get("size",0)})
            attachments.addItem(widget_item)
        root.addWidget(attachments,1)
        attachment_buttons=QHBoxLayout()
        add_file=QPushButton("AGGIUNGI ALLEGATI")
        remove_file=QPushButton("RIMUOVI DAL VERBALE")
        open_file=QPushButton("APRI ALLEGATO")
        attachment_buttons.addWidget(add_file)
        attachment_buttons.addWidget(remove_file)
        attachment_buttons.addWidget(open_file)
        attachment_buttons.addStretch(1)
        root.addLayout(attachment_buttons)

        def add_attachments():
            paths,_=QFileDialog.getOpenFileNames(dialog,"Seleziona allegati","",
                "Tutti i file (*);;PDF (*.pdf);;Immagini (*.png *.jpg *.jpeg)")
            for source in paths:
                path=Path(source)
                if not path.is_file():
                    continue
                if path.stat().st_size>25*1024*1024:
                    QMessageBox.warning(dialog,"Allegato troppo grande",f"{path.name} supera il limite di 25 MB.")
                    continue
                entry={"source":str(path),"name":path.name,"size":path.stat().st_size}
                item=QListWidgetItem(f"{path.name} · {path.stat().st_size/1024:.0f} KB · DA ALLEGARE")
                item.setData(Qt.ItemDataRole.UserRole,entry)
                attachments.addItem(item)
        def remove_attachment():
            row=attachments.currentRow()
            if row>=0:
                attachments.takeItem(row)
        def open_attachment():
            item=attachments.currentItem()
            if item is None:
                return
            entry=item.data(Qt.ItemDataRole.UserRole) or {}
            try:
                path=Path(entry["source"]) if entry.get("source") else self.incident_attachment_path(entry.get("path",""))
                if path.exists():
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
                else:
                    QMessageBox.warning(dialog,"Allegato non trovato",f"File non trovato: {path}")
            except Exception as exc:
                QMessageBox.warning(dialog,"Impossibile aprire l'allegato",str(exc))
        add_file.clicked.connect(add_attachments)
        remove_file.clicked.connect(remove_attachment)
        open_file.clicked.connect(open_attachment)

        root.addWidget(ui_label(
            "Massimo 25 MB per file. I documenti vengono copiati nella cartella locale del verbale. "
            "Rimuovere un allegato lo scollega dal verbale, ma conserva il file per permettere undo e ripristino degli snapshot.",
            "caption", wrap=True))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("SALVA VERBALE")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:
            return
        entries=[]
        for index in range(attachments.count()):
            entries.append(attachments.item(index).data(Qt.ItemDataRole.UserRole) or {})
        data={
            "id":report_id,
            "event_at":event_at.dateTime().toString(Qt.DateFormat.ISODate),
            "category":category.currentText(),
            "game_id":game_combo.currentData() or "",
            "participants":participants.text(),
            "summary":summary.text(),
            "description":description.toPlainText(),
            "decision":decision.toPlainText(),
            "status":status.currentText(),
            "referee":self.referee or (existing or {}).get("referee",""),
        }
        try:
            self.save_incident_report(data,entries)
            self.statusBar().showMessage("Verbale incidente salvato.",3000)
        except Exception as exc:
            QMessageBox.warning(self,"Verbale non salvato",str(exc))

    def open_incident_attachment(self,attachment):
        try:
            path=self.incident_attachment_path(attachment.get("path",""))
            if not path.is_file():
                raise FileNotFoundError(path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except Exception as exc:
            QMessageBox.warning(self,"Allegato non disponibile",str(exc))

    def refresh_incidents(self):
        if not hasattr(self,"incident_table"):
            return
        reports=sorted(self.incident_reports,key=lambda item:item.get("updated_at",item.get("created_at","")),reverse=True)
        query=self.incident_search.text().strip().casefold() if hasattr(self,"incident_search") else ""
        category=self.incident_category_filter.currentData() if hasattr(self,"incident_category_filter") else None
        status=self.incident_status_filter.currentData() if hasattr(self,"incident_status_filter") else None
        visible=[]
        for report in reports:
            haystack=" ".join(str(report.get(key,"")) for key in
                ("id","category","event_at","game_id","participants","summary","description","decision","referee")).casefold()
            if query and query not in haystack: continue
            if category and report.get("category")!=category: continue
            if status and report.get("status")!=status: continue
            visible.append(report)
        self.incident_table.setRowCount(len(visible))
        for row,report in enumerate(visible):
            gid=report.get("game_id","")
            game_label=report.get("game_label") or ("Generale / non associato" if not gid else gid)
            date=str(report.get("event_at") or report.get("created_at","")).replace("T"," ")
            if len(date)>16: date=date[:16]
            values=[f"{report.get('id','')}\n{date}",report.get("category",""),game_label,
                    report.get("participants",""),report.get("summary",""),report.get("status",""),
                    str(len(report.get("attachments",[])))]
            for col,value in enumerate(values):
                item=QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole,report.get("id"))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col in (0,1,2,5,6) else Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
                self.incident_table.setItem(row,col,item)
        open_count=sum(1 for item in self.incident_reports if item.get("status")=="Aperto")
        review_count=sum(1 for item in self.incident_reports if item.get("status")=="In esame")
        closed_count=sum(1 for item in self.incident_reports if item.get("status") in ("Risolto","Archiviato"))
        self.incident_stat_open.set(str(open_count),"Da gestire")
        self.incident_stat_review.set(str(review_count),"In valutazione")
        self.incident_stat_closed.set(str(closed_count),"Conclusi")
        self.incident_count_label.setText(f"{len(visible)} verbali visualizzati · {len(self.incident_reports)} totali")
        self.refresh_incident_detail()

    def refresh_incident_detail(self):
        if not hasattr(self,"incident_detail"):
            return
        report=self._incident_record(self.selected_incident_id())
        if report is None:
            self.incident_detail.setText("Seleziona un verbale per visualizzarne il riepilogo.")
            return
        files=", ".join(item.get("name","Allegato") for item in report.get("attachments",[])) or "Nessun allegato"
        self.incident_detail.setText(
            f"{report.get('id')} · {report.get('category')} · {report.get('status')} · "
            f"Evento: {str(report.get('event_at','')).replace('T',' ')} · Creato: {str(report.get('created_at','')).replace('T',' ')} · "
            f"Arbitro: {report.get('referee','Non indicato')}\n"
            f"{report.get('summary','')}\n"
            f"Fatti: {report.get('description','')}\n"
            f"Decisione: {report.get('decision','Non ancora registrata') or 'Non ancora registrata'}\n"
            f"Allegati: {files}"
        )

    def export_incidents_csv(self):
        path,_=QFileDialog.getSaveFileName(self,"Esporta verbali","Verbali-Incidenti-C5R.csv","CSV (*.csv)")
        if not path:
            return
        with open(path,"w",newline="",encoding="utf-8-sig") as stream:
            writer=csv.writer(stream,delimiter=";")
            writer.writerow(["ID","Data evento","Creato il","Aggiornato il","Categoria","Partita","Riferimento partita","Soggetti","Oggetto",
                             "Descrizione","Decisione","Stato","Arbitro","Allegati"])
            for item in self.incident_reports:
                writer.writerow([item.get(key,"") for key in
                    ("id","event_at","created_at","updated_at","category","game_id","game_label","participants","summary",
                     "description","decision","status","referee")]
                    +[", ".join(a.get("name","") for a in item.get("attachments",[]))])
        self.statusBar().showMessage("Registro verbali esportato in CSV.",3000)

    def export_selected_incident_pdf(self):
        report=self._incident_record(self.selected_incident_id())
        if report is None:
            QMessageBox.information(self,"Nessun verbale selezionato","Seleziona il verbale da esportare.")
            return
        path,_=QFileDialog.getSaveFileName(self,"Esporta verbale PDF",
            f"{report['id']}.pdf","PDF (*.pdf)")
        if not path:
            return
        writer=QPdfWriter(path)
        writer.setTitle(f"Verbale incidente {report['id']}")
        writer.setCreator("Coppa dei 5 Re · Control Room")
        writer.setResolution(150)
        painter=QPainter(writer)
        try:
            margin=170
            width=writer.width()-2*margin
            y=margin
            painter.setPen(QColor(GOLD))
            painter.setFont(QFont("Segoe UI",18,QFont.Weight.Bold))
            painter.drawText(margin,y+30,"COPPA DEI 5 RE · VERBALE ARBITRALE")
            y+=85
            def write_block(label,value):
                nonlocal y
                painter.setPen(QColor("#9A6A18"))
                painter.setFont(QFont("Segoe UI",9,QFont.Weight.Bold))
                painter.drawText(margin,y,label.upper())
                y+=28
                painter.setPen(QColor("#202A35"))
                painter.setFont(QFont("Segoe UI",10))
                rect=painter.fontMetrics().boundingRect(0,0,width,2500,Qt.TextFlag.TextWordWrap,str(value or "—"))
                height=max(28,rect.height()+10)
                if y+height>writer.height()-margin:
                    writer.newPage()
                    y=margin
                painter.drawText(QRect(margin,y,width,height),Qt.TextFlag.TextWordWrap,str(value or "—"))
                y+=height+25
            write_block("Numero e data di registrazione",f"{report.get('id')} · {report.get('created_at','')}")
            write_block("Data e ora dell'evento",report.get("event_at") or report.get("created_at",""))
            write_block("Categoria / stato",f"{report.get('category')} · {report.get('status')}")
            write_block("Partita / turno",report.get("game_label") or report.get("game_id") or "Generale / non associato")
            write_block("Persone coinvolte",report.get("participants"))
            write_block("Oggetto",report.get("summary"))
            write_block("Descrizione dei fatti",report.get("description"))
            write_block("Decisione / provvedimento",report.get("decision"))
            write_block("Direzione di gara",report.get("referee"))
            names=[item.get("name","Allegato") for item in report.get("attachments",[])]
            write_block("Allegati conservati separatamente",", ".join(names) if names else "Nessun allegato")
            write_block("Aggiornato il",report.get("updated_at",""))
            write_block("Firma del direttore di gara","______________________________________________")
        finally:
            painter.end()
        self.statusBar().showMessage("Verbale esportato in PDF.",3000)

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
        style_table(self.h2h_table, row_height=48, selectable=False)
        layout.addWidget(table_card(self.h2h_table),1); return page



    def snapshot_directory(self):
        folder = storage_path().parent / "snapshots"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _store_snapshot(self, reason):
        source = storage_path()
        if not source.exists():
            return None
        state = json.loads(source.read_text(encoding="utf-8"))
        created = datetime.now().isoformat(timespec="seconds")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = self.snapshot_directory() / f"{stamp}.json"
        payload = {"_c5r_snapshot": {"created_at": created, "reason": str(reason)}, "state": state}
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
        snapshots = sorted(self.snapshot_directory().glob("*.json"), key=lambda path: path.name, reverse=True)
        for stale in snapshots[40:]:
            stale.unlink(missing_ok=True)
        return target

    def _maybe_create_auto_snapshot(self):
        try:
            snapshots = sorted(self.snapshot_directory().glob("*.json"), key=lambda path: path.name, reverse=True)
            latest_time = None
            if snapshots:
                latest = json.loads(snapshots[0].read_text(encoding="utf-8"))
                value = latest.get("_c5r_snapshot", {}).get("created_at")
                if value:
                    latest_time = datetime.fromisoformat(value)
            now = datetime.now()
            if latest_time is None or (now - latest_time).total_seconds() >= 900:
                self._store_snapshot("Automatico · intervallo 15 minuti")
        except Exception as exc:
            self.statusBar().showMessage(f"Snapshot automatico non riuscito: {exc}", 4000)

    def create_snapshot(self, reason="Manuale"):
        try:
            self.save(automatic_snapshot=False)
            target = self._store_snapshot(reason)
            if target is None:
                raise RuntimeError("Archivio del torneo non trovato.")
            self.refresh_snapshot_status()
            self.statusBar().showMessage(f"Snapshot creato: {target.name}", 4000)
            return target
        except Exception as exc:
            QMessageBox.warning(self, "Snapshot non creato", str(exc))
            return None

    def snapshot_entries(self):
        entries = []
        for path in sorted(self.snapshot_directory().glob("*.json"), key=lambda item: item.name, reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                metadata = payload.get("_c5r_snapshot", {})
                state = payload.get("state", {})
                if not isinstance(state, dict) or "results" not in state or "schedule" not in state:
                    continue
                created = metadata.get("created_at", path.stem)
                reason = metadata.get("reason", "Snapshot")
                entries.append((path, created, reason))
            except Exception:
                continue
        return entries

    def refresh_snapshot_status(self):
        if not hasattr(self, "snapshot_status"):
            return
        entries = self.snapshot_entries()
        if not entries:
            self.snapshot_status.setText("Nessuno snapshot disponibile. Il primo verrà creato al prossimo salvataggio o manualmente.")
        else:
            path, created, reason = entries[0]
            self.snapshot_status.setText(
                f"{len(entries)} snapshot disponibili · ultimo: {created.replace('T', ' ')} · {reason} · {path.name}"
            )

    def restore_snapshot(self):
        entries = self.snapshot_entries()
        if not entries:
            QMessageBox.information(self, "Ripristino snapshot", "Non ci sono snapshot validi da ripristinare.")
            return False
        labels = [
            f"{created.replace('T', ' ')} · {reason} · {path.name}"
            for path, created, reason in entries
        ]
        selected, ok = QInputDialog.getItem(
            self, "Ripristina snapshot", "Seleziona la versione del torneo:", labels, 0, False
        )
        if not ok or not selected:
            return False
        index = labels.index(selected)
        snapshot_path, _, _ = entries[index]
        answer = QMessageBox.question(
            self, "Conferma ripristino",
            "Lo stato corrente verrà sostituito con lo snapshot selezionato. "
            "Prima del ripristino verrà salvata una copia di sicurezza dello stato attuale. Continuare?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        try:
            self.save(automatic_snapshot=False)
            self._store_snapshot("Sicurezza prima del ripristino")
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            restored = payload["state"]
            schedule = [
                (item["id"], int(item["round"]), item["white"], item["black"])
                for item in restored.get("schedule", [])
            ]
            validate_schedule(schedule)
            temp = storage_path().with_suffix(".restore.tmp")
            temp.write_text(json.dumps(restored, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(storage_path())
            self.load_state()
            self.boards.clear()
            self.log_operation("Ripristino snapshot", snapshot_path.name, "Stato precedente", "Snapshot ripristinato")
            self.save(automatic_snapshot=False)
            self.refresh_all()
            self.refresh_snapshot_status()
            self.statusBar().showMessage("Snapshot ripristinato. È stata conservata anche una copia dello stato precedente.", 5000)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Ripristino non riuscito", str(exc))
            return False

    def record_operational_alert(self,title,detail,severity="warning",target="calendar",source_key=""):
        alerts=getattr(self,"operational_alerts",[])
        if source_key and any(item.get("source_key")==source_key and not item.get("acknowledged") for item in alerts):
            return
        alerts.append({
            "id":uuid.uuid4().hex,
            "time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "title":str(title),"detail":str(detail),"severity":str(severity),
            "target":str(target),"source_key":str(source_key),"acknowledged":False,
        })
        self.operational_alerts=alerts[-150:]
        if not getattr(self,"state_load_blocked",False):
            self.save(automatic_snapshot=False)
        if hasattr(self,"notification_button"):
            self.refresh_notification_badge()

    def acknowledge_operational_alert(self,alert_id):
        changed=False
        for item in self.operational_alerts:
            if item.get("id")==alert_id and not item.get("acknowledged"):
                item["acknowledged"]=True
                item["acknowledged_at"]=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                changed=True
        if changed:
            self.log_operation("Avviso arbitrale verificato",alert_id,"Da verificare","Verificato")
            self.save()
            self.refresh_notification_badge()

    def maybe_probe_public_connection(self):
        if not self.public_base_url or self.match_http_server is None:
            return
        worker=getattr(self,"_public_probe_thread",None)
        if worker is not None and worker.isRunning():
            return
        if time.monotonic()-self._last_public_probe<60:
            return
        self._last_public_probe=time.monotonic()
        worker=PublicReachabilityProbe(self.public_base_url+"/health",self)
        worker.probeFinished.connect(self.on_public_connection_probe)
        self._public_probe_thread=worker
        worker.start()

    def on_public_connection_probe(self,ok,detail):
        previous=self._public_connection_state
        self._public_connection_state=bool(ok)
        if not ok and previous is not False:
            self.record_operational_alert(
                "Connessione al portale pubblico non disponibile",
                f"{self.public_base_url} · {detail}. Verifica tunnel HTTPS, rete e porta locale.",
                "danger","settings","public-connection-down"
            )
            self.statusBar().showMessage("Portale pubblico non raggiungibile: controlla tunnel e rete.",6000)
        elif ok and previous is False:
            self.record_operational_alert(
                "Connessione al portale pubblico ripristinata",
                f"{self.public_base_url} risponde correttamente.",
                "success","settings","public-connection-restored"
            )
            self.statusBar().showMessage("Portale pubblico nuovamente raggiungibile.",4000)
        self.refresh_notification_badge()

    def collect_notifications(self):
        notices=[]
        self.maybe_probe_public_connection()
        for alert in reversed(getattr(self,"operational_alerts",[])):
            if alert.get("acknowledged"):
                continue
            notices.append((
                alert.get("severity","warning"),alert.get("title","Avviso"),
                alert.get("detail",""),alert.get("target","calendar"),alert.get("id")
            ))
        for gid,_,white,black in GAMES:
            clock=self.clock_data(gid)
            if clock.get("started") and self.results.get(gid) is None:
                low=min(int(clock.get("white",0)),int(clock.get("black",0)))
                if low<=60:
                    notices.append((
                        "warning",f"Tempo quasi esaurito · {gid}",
                        f"{name(white)} vs {name(black)} · almeno un orologio è a {max(0,low)} secondi.",
                        "live",None
                    ))
        for key in ("sf1","sf2","final","third"):
            if self.playoff_results.get(key)=="1/2-1/2" and not self.playoff_winners.get(key):
                notices.append((
                    "warning",f"Armageddon da registrare · {key.upper()}",
                    "La partita playoff è patta: seleziona il vincitore dell'Armageddon.",
                    "playoffs",None
                ))
        for round_key,closed_at in self.round_closures.items():
            try:
                rnd=int(round_key)
                pending=[gid for gid,game_round,_,_ in GAMES if game_round==rnd and self.results.get(gid) is None]
                if pending:
                    notices.append((
                        "danger",f"Round {rnd} da riaprire",
                        "Sono stati rilevati risultati mancanti dopo la chiusura: "+", ".join(pending),
                        "calendar",None
                    ))
            except (TypeError,ValueError):
                notices.append(("danger","Chiusura round non valida",str(round_key),"health",None))
        findings=getattr(self,"_health_findings",None)
        if findings:
            errors=sum(1 for severity,_,_ in findings if severity=="ERRORE")
            if errors:
                notices.append((
                    "danger","Health Check: anomalie da risolvere",
                    f"L'ultimo controllo ha rilevato {errors} errori. Apri Tournament Health Check.",
                    "health",None
                ))
        return notices

    def refresh_notification_badge(self):
        if not hasattr(self,"notification_button"):
            return
        notices=self.collect_notifications()
        self.notification_button.setText(f"AVVISI · {len(notices)}")
        self.notification_button.setToolTip(
            "Nessuna notifica operativa." if not notices else
            "\n".join(item[1] for item in notices[:8])
        )

    def open_notifications(self):
        notices=self.collect_notifications()
        dialog=QDialog(self)
        dialog.setWindowTitle("Centro notifiche C5R")
        dialog.resize(760,520)
        root=QVBoxLayout(dialog)
        root.addWidget(ui_label("Centro notifiche arbitri","h1"))
        root.addWidget(ui_label(
            "Eventi registrati e controlli operativi. Gli avvisi persistenti restano in elenco finché non vengono verificati.",
            "muted",wrap=True
        ))
        items=QListWidget()
        for severity,title,detail,target,alert_id in notices:
            items.addItem(f"[{severity.upper()}]  {title}\n{detail}")
            items.item(items.count()-1).setData(Qt.ItemDataRole.UserRole,{"target":target,"alert_id":alert_id})
        if not notices:
            items.addItem("Tutto regolare · nessun avviso operativo.")
        root.addWidget(items,1)
        actions=QHBoxLayout()
        verify=QPushButton("SEGNA COME VERIFICATO")
        verify.setObjectName("PrimaryButton")
        open_section=QPushButton("APRI SEZIONE COLLEGATA")
        close=QPushButton("CHIUDI")
        def selected_payload():
            selected=items.selectedItems()
            return selected[0].data(Qt.ItemDataRole.UserRole) if selected else None
        def mark_verified():
            payload=selected_payload()
            if payload and payload.get("alert_id"):
                self.acknowledge_operational_alert(payload["alert_id"])
                dialog.accept()
                self.open_notifications()
            else:
                self.statusBar().showMessage("Seleziona prima un avviso persistente da verificare.",2500)
        def navigate_selected():
            payload=selected_payload()
            if payload and payload.get("target"):
                self.navigate_to_page(payload["target"])
                dialog.accept()
        verify.clicked.connect(mark_verified)
        open_section.clicked.connect(navigate_selected)
        close.clicked.connect(dialog.accept)
        actions.addWidget(verify);actions.addWidget(open_section);actions.addStretch(1);actions.addWidget(close)
        root.addLayout(actions)
        dialog.exec()

    def open_command_palette(self):
        commands = [
            ("Apri Dashboard", "dashboard", "Panoramica e prossimi incontri"),
            ("Apri Live Arena", "live", "Scacchiere e cronometri"),
            ("Apri Calendario", "calendar", "Risultati, turni e assistente round"),
            ("Apri Classifica", "standings", "Podio e punteggi"),
            ("Apri Profilo giocatori", "players", "Statistiche individuali"),
            ("Confronta due giocatori", "compare", "Confronto diretto e rendimento"),
            ("Apri Opening Explorer", "openings", "Aperture delle partite registrate"),
            ("Esegui Tournament Health Check", "health_run", "Controllo di coerenza dei dati"),
            ("Apri Centro notifiche", "notifications", "Cronometri e attività da completare"),
            ("Apri Assistente Round", "round_wizard", "Procedura guidata per chiudere i turni"),
            ("Crea snapshot manuale", "snapshot", "Salva una versione ripristinabile"),
            ("Ripristina snapshot", "restore_snapshot", "Scegli una versione precedente"),
            ("Esporta torneo PGN", "export_pgn", "Esporta tutte le partite e annotazioni"),
            ("Crea backup JSON", "backup", "Salva una copia esterna dei dati"),
            ("Apri Impostazioni", "settings", "Regolamento, arbitro e dati locali"),
        ]
        dialog = QDialog(self)
        dialog.setWindowTitle("Command Palette · Coppa dei 5 Re")
        dialog.resize(680, 560)
        root = QVBoxLayout(dialog)
        search = QLineEdit()
        search.setPlaceholderText("Cerca un'azione, una pagina o uno strumento…")
        search.setAccessibleName("Cerca comando")
        root.addWidget(search)
        listing = QListWidget()
        root.addWidget(listing, 1)
        for title, key, description in commands:
            listing.addItem(f"{title}\n{description}")
            listing.item(listing.count() - 1).setData(Qt.ItemDataRole.UserRole, key)
        def filter_commands(value):
            query = value.casefold().strip()
            for index in range(listing.count()):
                listing.item(index).setHidden(query not in listing.item(index).text().casefold())
            for index in range(listing.count()):
                if not listing.item(index).isHidden():
                    listing.setCurrentRow(index)
                    break
        def activate(item=None):
            item = item or listing.currentItem()
            if item is None or item.isHidden():
                return
            key = item.data(Qt.ItemDataRole.UserRole)
            dialog.accept()
            self.execute_palette_command(key)
        search.textChanged.connect(filter_commands)
        search.returnPressed.connect(activate)
        listing.itemActivated.connect(activate)
        listing.setCurrentRow(0)
        search.setFocus()
        dialog.exec()

    def execute_palette_command(self, key):
        commands = {
            "dashboard": lambda: self.navigate_to_page("dashboard"),
            "live": lambda: self.navigate_to_page("live"),
            "calendar": lambda: self.navigate_to_page("calendar"),
            "standings": lambda: self.navigate_to_page("standings"),
            "players": lambda: self.navigate_to_page("players"),
            "compare": lambda: self.navigate_to_page("compare"),
            "openings": lambda: self.navigate_to_page("openings"),
            "health": lambda: self.navigate_to_page("health"),
            "health_run": lambda: (self.navigate_to_page("health"), self.run_health_check()),
            "notifications": self.open_notifications,
            "round_wizard": self.open_round_wizard,
            "snapshot": lambda: self.create_snapshot("Manuale · Command Palette"),
            "restore_snapshot": self.restore_snapshot,
            "export_pgn": self.export_all_pgn,
            "backup": self.export_backup,
            "settings": lambda: self.navigate_to_page("settings"),
        }
        action = commands.get(key)
        if action:
            action()

    def navigate_to_page(self, key):
        if key in self._page_keys:
            self.nav.set_current(key, emit=True)
        elif key in self._nav_keys:
            self.nav.set_current(key, emit=True)

    def open_round_wizard(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Assistente operativo round")
        dialog.resize(680, 520)
        root = QVBoxLayout(dialog)
        root.addWidget(ui_label("Assistente operativo round", "h1"))
        root.addWidget(ui_label(
            "Seleziona il turno, controlla gli incontri e chiudilo solo quando ogni partita ha un risultato o risulta annullata.",
            "muted", wrap=True
        ))
        round_box = QComboBox()
        for rnd in range(1, 6):
            round_box.addItem(f"ROUND {rnd}", rnd)
        root.addWidget(ui_label("TURNO", "field"))
        root.addWidget(round_box)
        status = ui_label("", "body", wrap=True)
        root.addWidget(status)
        game_list = QListWidget()
        root.addWidget(game_list, 1)
        actions = QHBoxLayout()
        open_live = QPushButton("APRI PARTITE IN LIVE ARENA")
        close_round = QPushButton("CHIUDI TURNO")
        close_round.setObjectName("PrimaryButton")
        actions.addWidget(open_live)
        actions.addStretch(1)
        actions.addWidget(close_round)
        root.addLayout(actions)
        def update_round():
            rnd = round_box.currentData()
            rows = [item for item in GAMES if item[1] == rnd]
            game_list.clear()
            unresolved = []
            for gid, _, white, black in rows:
                result = self.results.get(gid)
                if result is None:
                    unresolved.append(gid)
                    if self.clock_data(gid).get("started") or self.moves.get(gid):
                        label = "IN CORSO"
                    else:
                        label = "DA DISPUTARE"
                elif result == "VOID":
                    label = "ANNULLATA"
                else:
                    label = f"CONCLUSA · {result}"
                game_list.addItem(f"{gid}   ·   {name(white)} vs {name(black)}   ·   {label}")
            closure = self.round_closures.get(str(rnd))
            if unresolved:
                status.setText(
                    f"{len(unresolved)} partite ancora da definire: {', '.join(unresolved)}. "
                    "La chiusura è disabilitata."
                )
            else:
                status.setText(
                    f"Entrambe le partite sono risolte. "
                    + (f"Turno già chiuso il {closure}." if closure else "Il turno può essere chiuso.")
                )
            close_round.setEnabled(not unresolved and not bool(closure))
            close_round.setText("TURNO GIÀ CHIUSO" if closure else "CHIUDI TURNO")
        def open_live_games():
            rnd = round_box.currentData()
            game_rows = [item for item in GAMES if item[1] == rnd]
            if not game_rows:
                return
            for slot, row in enumerate(game_rows[:2]):
                combo = self.live_cards[slot].selector
                index = combo.findData(row[0])
                if index >= 0:
                    combo.setCurrentIndex(index)
            self.navigate_to_page("live")
            dialog.accept()
        def close_selected_round():
            rnd = round_box.currentData()
            game_rows = [item for item in GAMES if item[1] == rnd]
            unresolved = [gid for gid, _, _, _ in game_rows if self.results.get(gid) is None]
            if unresolved:
                update_round()
                return
            if self.round_closures.get(str(rnd)):
                QMessageBox.information(dialog, "Turno già chiuso", "Questo turno risulta già chiuso.")
                return
            stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
            self.round_closures[str(rnd)] = stamp
            self.log_operation("Turno chiuso", f"Round {rnd}", "In corso", stamp)
            self.save()
            self.refresh_all()
            update_round()
        round_box.currentIndexChanged.connect(update_round)
        open_live.clicked.connect(open_live_games)
        close_round.clicked.connect(close_selected_round)
        update_round()
        dialog.exec()

    def player_profile_data(self, player_id):
        if player_id not in PLAYERS:
            raise ValueError("Giocatore non riconosciuto.")
        standings_row = next(row for row in self.standings() if row["id"] == player_id)
        raw, played, wins, draws, losses = self.raw_stats()
        penalties = self.penalty_points()
        move_losses = [
            float(item.get("expected_points_loss", 0))
            for reviews in self.move_reviews.values()
            for item in reviews
            if item.get("player") == player_id
        ]
        accuracy = None if not move_losses else max(
            0.0, min(100.0, 100.0 * (1.0 - sum(move_losses) / len(move_losses)))
        )
        history = []
        colors = {"white": {"wins": 0, "draws": 0, "losses": 0},
                  "black": {"wins": 0, "draws": 0, "losses": 0}}
        opening_counts = {}
        for gid, rnd, white, black in GAMES:
            if player_id not in (white, black):
                continue
            color = "white" if player_id == white else "black"
            opponent = black if color == "white" else white
            result = self.results.get(gid)
            if result == "VOID":
                outcome = "ANNULLATA"
            elif result is None:
                outcome = "DA DISPUTARE"
            elif result == "1/2-1/2":
                outcome = "PATTA"
                colors[color]["draws"] += 1
            else:
                player_won = (result == "1-0" and color == "white") or (result == "0-1" and color == "black")
                outcome = "VITTORIA" if player_won else "SCONFITTA"
                colors[color]["wins" if player_won else "losses"] += 1
            opening = self.opening_name(gid)
            opening_counts[opening] = opening_counts.get(opening, 0) + 1
            history.append({
                "round": rnd, "gid": gid, "opponent": opponent, "color": color,
                "result": result, "outcome": outcome, "opening": opening,
                "accuracy": self.accuracy_for_player(gid, player_id)
            })
        return {
            "id": player_id, "name": name(player_id), "points": standings_row["points"],
            "played": played[player_id], "wins": wins[player_id], "draws": draws[player_id],
            "losses": losses[player_id], "penalty": penalties[player_id],
            "accuracy": accuracy, "reviewed_moves": len(move_losses),
            "colors": colors, "history": history, "openings": opening_counts,
        }

    def player_photo_pixmap(self,player_id,size,photo_data=None):
        size=max(24,int(size))
        profile=self.player_bios.get(player_id,{})
        encoded=photo_data if photo_data is not None else profile.get("photo_data","")
        source=QPixmap()
        if encoded:
            try:
                source.loadFromData(base64.b64decode(encoded,validate=True))
            except Exception:
                source=QPixmap()
        canvas=QPixmap(size,size)
        canvas.fill(Qt.GlobalColor.transparent)
        painter=QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing,True)
        path=QPainterPath()
        path.addEllipse(0,0,size,size)
        painter.setClipPath(path)
        if not source.isNull():
            scaled=source.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.SmoothTransformation)
            crop=scaled.copy(max(0,(scaled.width()-size)//2),max(0,(scaled.height()-size)//2),size,size)
            painter.drawPixmap(0,0,crop)
        else:
            color=QColor(T.player_tint(ORDER.index(player_id)))
            painter.fillRect(0,0,size,size,color)
            initials="".join(part[0] for part in name(player_id).split()[:2]).upper() or "?"
            painter.setPen(QColor("#FFFFFF"))
            painter.setFont(QFont("Segoe UI",max(10,int(size*0.34)),QFont.Weight.Bold))
            painter.drawText(QRect(0,0,size,size),Qt.AlignmentFlag.AlignCenter,initials)
        painter.end()
        return canvas

    def set_player_avatar_label(self,label,player_id,size):
        label.setFixedSize(size,size)
        label.setPixmap(self.player_photo_pixmap(player_id,size))
        label.setText("")
        label.setToolTip(name(player_id))
        label.setStyleSheet("border: 2px solid #C9A15B; border-radius: %dpx;" % (size//2))

    def player_rating_summary(self,player_id):
        profile=self.player_profile_info(player_id)
        ratings=profile.get("ratings",{})
        values=[("B",ratings.get("bullet")),("BL",ratings.get("blitz")),("R",ratings.get("rapid"))]
        present=[f"{key} {int(value)}" for key,value in values if value is not None]
        return "Chess.com · "+" · ".join(present) if present else "Chess.com · rating non inseriti"

    def player_profile_info(self,player_id):
        profile=dict(self.player_bios.get(player_id,{}) or {})
        profile.setdefault("age","")
        profile.setdefault("bio","")
        profile.setdefault("chesscom_username",PLAYERS[player_id][1])
        ratings=profile.get("ratings",{}) or {}
        profile["ratings"]={kind:ratings.get(kind) for kind in ("bullet","blitz","rapid")}
        profile.setdefault("photo_data","")
        return profile

    def _encode_player_photo(self,path):
        source=QPixmap(path)
        if source.isNull():
            raise ValueError("Il file selezionato non è un'immagine supportata.")
        scaled=source.scaled(640,640,Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        buffer=QBuffer()
        if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
            raise ValueError("Impossibile preparare la foto selezionata.")
        try:
            if not scaled.save(buffer,"JPG",88):
                raise ValueError("Impossibile convertire la foto in JPEG.")
            payload=bytes(buffer.data())
        finally:
            buffer.close()
        if len(payload)>512*1024:
            raise ValueError("La foto compressa supera 512 KB.")
        return base64.b64encode(payload).decode("ascii")

    def edit_player_bio(self,player_id):
        if player_id not in PLAYERS:
            return
        current=self.player_profile_info(player_id)
        dialog=QDialog(self)
        dialog.setWindowTitle(f"Anagrafica giocatore · {name(player_id)}")
        dialog.resize(680,650)
        root=QVBoxLayout(dialog)
        root.setContentsMargins(22,20,22,18)
        root.setSpacing(12)
        photo_row=QHBoxLayout()
        preview=QLabel()
        preview.setFixedSize(112,112)
        preview.setPixmap(self.player_photo_pixmap(player_id,112,current.get("photo_data","")))
        preview.setStyleSheet("border: 2px solid #C9A15B; border-radius: 56px;")
        photo_row.addWidget(preview)
        photo_help=QVBoxLayout()
        photo_help.addWidget(ui_label("FOTO PROFILO","field"))
        photo_help.addWidget(ui_label(
            "La foto viene ridimensionata e salvata nei dati locali del torneo, così resta inclusa nei backup e negli snapshot.",
            "muted",wrap=True))
        photo_button=QPushButton("SCEGLI / CAMBIA FOTO")
        remove_photo=QPushButton("RIMUOVI FOTO")
        photo_actions=QHBoxLayout()
        photo_actions.addWidget(photo_button)
        photo_actions.addWidget(remove_photo)
        photo_help.addLayout(photo_actions)
        photo_row.addLayout(photo_help,1)
        root.addLayout(photo_row)
        photo_data=current.get("photo_data","")

        fields=QGridLayout()
        age=QLineEdit(str(current.get("age","") or ""))
        age.setPlaceholderText("Età in anni")
        age.setValidator(QIntValidator(1,120,dialog))
        chesscom=QLineEdit(str(current.get("chesscom_username") or ""))
        chesscom.setPlaceholderText("Username Chess.com")
        email=QLineEdit(str(current.get("email") or ""))
        email.setPlaceholderText("email@esempio.it")
        whatsapp=QLineEdit(str(current.get("whatsapp") or ""))
        whatsapp.setPlaceholderText("+39 3xx xxx xxxx · prefisso internazionale")
        fields.addWidget(ui_label("ETÀ","field"),0,0)
        fields.addWidget(age,0,1)
        fields.addWidget(ui_label("USERNAME CHESS.COM","field"),0,2)
        fields.addWidget(chesscom,0,3)
        fields.addWidget(ui_label("EMAIL","field"),1,0)
        fields.addWidget(email,1,1)
        fields.addWidget(ui_label("WHATSAPP","field"),1,2)
        fields.addWidget(whatsapp,1,3)
        root.addLayout(fields)

        ratings_card=Card("Rating Chess.com","Inserisci i rating attuali del profilo online. I campi possono restare vuoti finché non mi comunichi i valori.")
        rating_grid=QGridLayout()
        rating_edits={}
        for col,(kind,label) in enumerate((("bullet","BULLET"),("blitz","BLITZ"),("rapid","RAPID"))):
            edit=QLineEdit("" if current["ratings"][kind] is None else str(current["ratings"][kind]))
            edit.setPlaceholderText("—")
            edit.setValidator(QIntValidator(100,4000,dialog))
            rating_edits[kind]=edit
            rating_grid.addWidget(ui_label(label,"field"),0,col)
            rating_grid.addWidget(edit,1,col)
        ratings_card.body.addLayout(rating_grid)
        root.addWidget(ratings_card)

        biography=QPlainTextEdit()
        biography.setPlaceholderText("Breve biografia: stile di gioco, percorso scacchistico, club, curiosità…")
        biography.setPlainText(str(current.get("bio","")))
        biography.setMaximumHeight(130)
        root.addWidget(ui_label("BIOGRAFIA","field"))
        root.addWidget(biography)

        def choose_photo():
            nonlocal photo_data
            path,_=QFileDialog.getOpenFileName(dialog,"Scegli foto profilo","","Immagini (*.png *.jpg *.jpeg *.webp *.bmp)")
            if not path:
                return
            try:
                photo_data=self._encode_player_photo(path)
                preview.setPixmap(self.player_photo_pixmap(player_id,112,photo_data))
            except Exception as exc:
                QMessageBox.warning(dialog,"Foto non caricata",str(exc))
        def clear_photo():
            nonlocal photo_data
            photo_data=""
            preview.setPixmap(self.player_photo_pixmap(player_id,112,""))
        photo_button.clicked.connect(choose_photo)
        remove_photo.clicked.connect(clear_photo)
        root.addWidget(ui_label(
            "Fonte dei rating: Chess.com. Non vengono mostrati rating FIDE/OTB. Il valore inserito è quello che vuoi usare come riferimento.",
            "caption",wrap=True))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("SALVA SCHEDA")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:
            return
        if age.text().strip() and not 1<=int(age.text())<=120:
            QMessageBox.warning(self,"Età non valida","Inserisci un'età compresa tra 1 e 120 anni.")
            return
        rating_values={}
        for kind,edit in rating_edits.items():
            raw=edit.text().strip()
            if raw and not 100<=int(raw)<=4000:
                QMessageBox.warning(self,"Rating non valido",f"Il rating {kind.title()} deve essere tra 100 e 4000.")
                return
            rating_values[kind]=int(raw) if raw else None
        email_value=email.text().strip()
        if email_value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email_value):
            QMessageBox.warning(self,"Email non valida","Inserisci un indirizzo email valido oppure lascia il campo vuoto.")
            return
        whatsapp_value=whatsapp.text().strip()
        if whatsapp_value and not re.fullmatch(r"\+?[0-9][0-9 ()-]{6,22}",whatsapp_value):
            QMessageBox.warning(self,"Numero WhatsApp non valido","Usa il prefisso internazionale, ad esempio +39 3331234567.")
            return
        self.player_bios[player_id]={
            "age":int(age.text()) if age.text().strip() else "",
            "bio":biography.toPlainText().strip(),
            "email":email_value,
            "whatsapp":whatsapp_value,
            "chesscom_username":chesscom.text().strip(),
            "ratings":rating_values,
            "photo_data":photo_data,
            "ratings_updated_at":datetime.now().isoformat(timespec="seconds") if any(value is not None for value in rating_values.values()) else "",
        }
        self.log_operation("Scheda giocatore aggiornata",player_id,"","Anagrafica, foto e rating Chess.com aggiornati")
        self.save()
        self.refresh_all()
        self.statusBar().showMessage(f"Scheda di {name(player_id)} salvata.",3000)

    def refresh_player_identity(self,player_id):
        if not hasattr(self,"profile_identity_name"):
            return
        profile=self.player_profile_info(player_id)
        self.profile_identity_photo.setPixmap(self.player_photo_pixmap(player_id,116))
        self.profile_identity_name.setText(name(player_id))
        age=f"{profile['age']} anni" if profile.get("age") else "Età non inserita"
        username=profile.get("chesscom_username") or "username non inserito"
        self.profile_identity_meta.setText(f"{age}   ·   Chess.com: {username}")
        self.profile_identity_bio.setText(profile.get("bio") or "Biografia non ancora inserita.")
        for kind,tile in self.profile_rating_tiles.items():
            value=profile["ratings"].get(kind)
            tile.set("—" if value is None else f"{value:,}".replace(",","."),
                     f"Rating Chess.com · {kind.title()}")
        updated=profile.get("ratings_updated_at","") if any(value is not None for value in profile["ratings"].values()) else ""
        self.profile_rating_date.setText(
            f"Valori aggiornati: {updated[:10]}" if updated else "Rating non ancora verificati")

    def make_qr_pixmap(self,data,size=240):
        code=qrcode.QRCode(version=None,error_correction=qrcode.constants.ERROR_CORRECT_M,
                           box_size=6,border=3)
        code.add_data(str(data))
        code.make(fit=True)
        image=code.make_image(fill_color="black",back_color="white").convert("RGB")
        buffer=io.BytesIO()
        image.save(buffer,format="PNG")
        pixmap=QPixmap()
        pixmap.loadFromData(buffer.getvalue(),"PNG")
        return pixmap.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)

    def local_network_ip(self):
        probe=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            probe.connect(("192.0.2.1",80))
            address=probe.getsockname()[0]
            return address if address and not address.startswith("127.") else ""
        except OSError:
            return ""
        finally:
            probe.close()

    def match_web_state(self,gid):
        match=next((item for item in GAMES if item[0]==gid),None)
        is_playoff=gid in ("sf1","sf2","third","final")
        if match:
            _,rnd,white,black=match
            round_label=f"Round {rnd}"
            result=self.results.get(gid) or "Da disputare"
        elif is_playoff:
            label={"sf1":"Semifinale 1","sf2":"Semifinale 2","third":"3° / 4° posto","final":"Finale"}[gid]
            white,black=getattr(self,"playoff_pairs",{}).get(gid,(None,None))
            round_label="Playoff · "+label
            result=self.playoff_results.get(gid) or "Da disputare"
        else:
            return None

        moves_key=tuple(self.moves.get(gid,[]))
        cached=self._web_match_cache.get(gid)
        if cached is None or cached[0]!=moves_key:
            board=chess.Board()
            move_text=[]
            valid_uci=[]
            for index,uci in enumerate(moves_key,1):
                try:
                    move=chess.Move.from_uci(uci)
                    if move not in board.legal_moves:
                        break
                    san=board.san(move)
                    move_text.append((f"{(index+1)//2}. " if index%2 else "")+san)
                    board.push(move)
                    valid_uci.append(move.uci())
                except Exception:
                    break
            snapshot={"fen":board.fen(),"last_move":valid_uci[-1] if valid_uci else "",
                      "move_text":" ".join(move_text) or "Nessuna mossa registrata",
                      "turn":"Bianco" if board.turn==chess.WHITE else "Nero","ply":len(valid_uci)}
            self._web_match_cache[gid]=(moves_key,snapshot)
        else:
            snapshot=cached[1]

        clock=self.clocks.get(gid,{})
        base_seconds=30*60 if is_playoff else 15*60
        white_seconds=max(0.0,float(clock.get("white",base_seconds)))
        black_seconds=max(0.0,float(clock.get("black",base_seconds)))
        running=bool(clock.get("started") and result=="Da disputare")
        clock_turn=clock.get("side_to_move","white") if is_playoff else ("white" if snapshot["turn"]=="Bianco" else "black")
        if running:
            try:
                elapsed=min(43200.0,max(0.0,time.time()-float(clock.get("last_wall",time.time()))))
            except (TypeError,ValueError):
                elapsed=0.0
            if clock_turn=="white":
                white_seconds=max(0.0,white_seconds-elapsed)
            else:
                black_seconds=max(0.0,black_seconds-elapsed)
        def fmt_clock(seconds):
            value=max(0,int(math.ceil(seconds)))
            return f"{value//60:02d}:{value%60:02d}"
        clock_text=f"Bianco {fmt_clock(white_seconds)} · Nero {fmt_clock(black_seconds)}"
        if running:
            clock_text+=" · IN CORSO"
        elif result!="Da disputare":
            clock_text+=" · CONCLUSO"
        else:
            clock_text+=" · FERMO"
        return {
            "game_id":gid,
            "round":round_label,
            "white":name(white) if white else "Giocatore da definire",
            "black":name(black) if black else "Giocatore da definire",
            "result":str(result),
            "fen":snapshot["fen"],
            "last_move":snapshot["last_move"],
            "move_text":snapshot["move_text"],
            "turn":snapshot["turn"],
            "clock_text":clock_text,
            "clock_white":int(math.ceil(white_seconds)),
            "clock_black":int(math.ceil(black_seconds)),
            "clock_running":running,
            "clock_turn":clock_turn,
            "ply":snapshot["ply"],
            "status":"CONCLUSA" if result!="Da disputare" else ("IN CORSO" if running or snapshot["ply"] else "DA GIOCARE"),
            "is_playoff":is_playoff,
        }

    def public_portal_state(self):
        states=[]
        for gid,_,_,_ in GAMES:
            state=self.match_web_state(gid)
            if state:states.append(state)
        for gid in ("sf1","sf2","third","final"):
            state=self.match_web_state(gid)
            if state:states.append(state)
        rows=[]
        for position,row in enumerate(self.standings(),1):
            rows.append({
                "position":position,"player":name(row["id"]),
                "played":row["played"],"wins":row["wins"],"draws":row["draws"],
                "losses":row["losses"],"penalty":row["penalty"],"points":row["points"],
            })
        return {
            "tournament":"Coppa dei 5 Re",
            "as_of":datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "matches":states,
            "standings":rows,
            "completed":sum(1 for item in states if item["result"] not in ("Da disputare","VOID")),
            "live":sum(1 for item in states if item["status"]=="IN CORSO"),
        }

    def valid_spectator_token(self,token):
        candidate=str(token or "")
        expected=str(getattr(self,"spectator_token",""))
        return bool(candidate and expected and hmac.compare_digest(candidate,expected))

    def match_web_html(self,gid):
        state=self.match_web_state(gid)
        if state is None:
            return None
        match=next((item for item in GAMES if item[0]==gid),None)
        if match:
            white,black=match[2],match[3]
        else:
            white,black=getattr(self,"playoff_pairs",{}).get(gid,(None,None))

        def player_box(player_id,side):
            if not player_id:
                return f"<div class='player'><div class='avatar initials'>?</div><div><strong>{html.escape(state[side])}</strong><span>Da definire</span></div></div>"
            profile=self.player_profile_info(player_id)
            photo=profile.get("photo_data","")
            avatar=(f"<img class='avatar' src='data:image/jpeg;base64,{photo}' alt=''>" if photo
                    else f"<div class='avatar initials'>{html.escape(name(player_id)[:1])}</div>")
            ratings=profile.get("ratings",{})
            rating_text=" · ".join(f"{label} {ratings[kind]}" for label,kind in
                (("Bullet","bullet"),("Blitz","blitz"),("Rapid","rapid")) if ratings.get(kind) is not None)
            username=profile.get("chesscom_username") or PLAYERS[player_id][1]
            chess_link=f"https://www.chess.com/member/{urllib.parse.quote(username,safe='')}"
            return (f"<div class='player'>{avatar}<div><strong>{html.escape(name(player_id))}</strong>"
                f"<span>{html.escape(rating_text or 'Rating non inseriti')}</span>"
                f"<a href='{chess_link}'>Chess.com · {html.escape(username)}</a></div></div>")

        title=f"{html.escape(state['round'])} · {html.escape(gid)}"
        state_json=json.dumps(state,ensure_ascii=True).replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
        state_path="/api/match/"+urllib.parse.quote(gid,safe="")+"?token="+urllib.parse.quote(self.spectator_token,safe="")
        return f"""<!doctype html><html lang='it'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<meta name='theme-color' content='#101720'>
<title>Coppa dei 5 Re · {title}</title><style>
:root{{color-scheme:dark;--bg:#101720;--panel:#1b2633;--line:#344252;--gold:#e3c07f;--muted:#aab5c2}}
*{{box-sizing:border-box}}body{{margin:0;padding:clamp(12px,3vw,28px);background:var(--bg);color:#edf1f5;font-family:Segoe UI,Arial,sans-serif}}
main{{max-width:1080px;margin:auto}}header{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:18px;flex-wrap:wrap}}
.brand{{color:#c9a15b;font-weight:900;letter-spacing:2px}}.live{{color:#78d6a0;font-size:13px;font-weight:800;letter-spacing:1px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:clamp(14px,2.5vw,22px);margin:14px 0}}
.match{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:16px}}
.player{{display:flex;gap:14px;align-items:center;min-width:0}}.avatar{{width:64px;height:64px;border-radius:50%;object-fit:cover;flex:none}}
.initials{{display:grid;place-items:center;background:#40566e;font-size:28px;font-weight:800}}
.player strong{{display:block;font-size:clamp(15px,2vw,19px);overflow-wrap:anywhere}}
.player span,.player a{{display:block;color:#b9c4d0;margin-top:5px;font-size:13px;overflow-wrap:anywhere}}a{{color:var(--gold)}}
.score{{text-align:center;color:var(--gold);font-size:clamp(18px,3vw,24px);font-weight:900;white-space:nowrap}}
.match-meta{{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:14px;color:var(--muted);font-size:13px}}
.live-layout{{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(250px,.8fr);gap:16px;align-items:start}}
.board-card{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:clamp(12px,2vw,20px)}}
.board-top{{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:12px}}
.board-top strong{{font-size:14px;letter-spacing:.6px}}.turn{{color:var(--gold);font-weight:800;font-size:13px}}
.board{{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));width:100%;aspect-ratio:1;border:4px solid #263648;border-radius:7px;overflow:hidden}}
.square{{position:relative;display:grid;place-items:center;aspect-ratio:1;min-width:0;min-height:0}}
.light{{background:#f0d9b5}}.dark{{background:#b58863}}
.square.last-from,.square.last-to{{box-shadow:inset 0 0 0 4px rgba(250,204,21,.72)}}
.piece{{font-family:'Segoe UI Symbol','DejaVu Sans',serif;font-size:clamp(22px,5.7vw,62px);line-height:1;user-select:none}}
.piece.white{{color:#fffdf4;text-shadow:1px 1px 2px #282828,-1px -1px 1px #282828,1px -1px 1px #282828,-1px 1px 1px #282828}}
.piece.black{{color:#171717;text-shadow:0 1px 1px rgba(255,255,255,.25)}}
.coord{{position:absolute;font-size:clamp(8px,1.15vw,11px);font-weight:800;opacity:.72;line-height:1}}
.coord.rank{{top:3px;left:4px}}.coord.file{{right:4px;bottom:3px}}
.moves-card{{min-width:0}}.moves-title{{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}}
.move-count{{color:var(--muted);font-size:12px}}.move-list{{max-height:min(66vw,620px);overflow:auto;line-height:1.9;overflow-wrap:anywhere;font-family:ui-monospace,Consolas,monospace;font-size:14px;color:#edf1f5;white-space:normal}}
.moves-empty{{color:var(--muted)}}.footer{{text-align:center;color:var(--muted);font-size:12px;padding:12px}}
@media(max-width:680px){{.live-layout{{grid-template-columns:1fr}}.match{{grid-template-columns:1fr auto 1fr;gap:8px}}.avatar{{width:44px;height:44px}}.player{{gap:8px}}.player span,.player a{{font-size:11px}}.score{{font-size:17px}}.move-list{{max-height:240px}}}}
</style></head><body><main>
<header><div class='brand'>COPPA DEI 5 RE · LIVE</div><div class='live'>● AGGIORNAMENTO IN DIRETTA</div></header>
<section class='card'>
<div class='muted'>{title}</div>
<div class='match'>{player_box(white,'white')}<div class='score'>VS<br><span id='result'>{html.escape(state['result'])}</span></div>{player_box(black,'black')}</div>
<div class='match-meta'><span id='clock'>{html.escape(state['clock_text'] or 'Orologio non avviato')}</span><span id='turn'>Muove il {html.escape(state['turn'])}</span></div>
</section>
<section class='live-layout'>
<div class='board-card'><div class='board-top'><strong>SCACCHIERA LIVE</strong><span class='turn' id='board-status'>Partita in corso</span></div>
<div id='board' class='board' role='img' aria-label='Scacchiera aggiornata in tempo reale'></div>
<div class='footer'>Vista spettatore · Bianco in basso · Ultima mossa evidenziata</div></div>
<aside class='card moves-card'><div class='moves-title'><strong>CRONOLOGIA MOSSE</strong><span id='move-count' class='move-count'>{state['ply']} ply</span></div>
<div id='move-list' class='move-list'>{html.escape(state['move_text'])}</div>
<div class='footer'>La pagina controlla automaticamente le nuove mosse.</div></aside>
</section>
<div class='footer'>Coppa dei 5 Re · Pagina informativa in sola lettura sulla rete locale del torneo.</div>
</main><script>
const INITIAL_STATE={state_json};
const STATE_URL={json.dumps(state_path)};
const GLYPHS={{K:'♔',Q:'♕',R:'♖',B:'♗',N:'♘',P:'♙',k:'♚',q:'♛',r:'♜',b:'♝',n:'♞',p:'♟'}};
const files='abcdefgh';
let lastRenderedFen=null;
function renderBoard(state){{
  const parts=String(state.fen||'').split(' ');
  const ranks=(parts[0]||'').split('/');
  if(ranks.length!==8)return;
  const last=String(state.last_move||'');
  const from=last.length>=4?last.slice(0,2):'';
  const to=last.length>=4?last.slice(2,4):'';
  const board=document.getElementById('board');
  const fragment=document.createDocumentFragment();
  ranks.forEach((rank,row)=>{{
    const cells=[];
    for(const token of rank){{
      if(/[1-8]/.test(token)){{
        for(let n=0;n<Number(token);n++)cells.push('');
      }}else{{
        cells.push(token);
      }}
    }}
    while(cells.length<8)cells.push('');
    cells.slice(0,8).forEach((token,file)=>{{
      const squareName=files[file]+String(8-row);
      const square=document.createElement('div');
      square.className='square '+(((row+file)%2===1)?'dark':'light');
      if(squareName===from)square.classList.add('last-from');
      if(squareName===to)square.classList.add('last-to');
      if(token){{
        const piece=document.createElement('span');
        piece.className='piece '+(token===token.toUpperCase()?'white':'black');
        piece.textContent=GLYPHS[token]||'';
        square.appendChild(piece);
      }}
      if(file===0){{const coord=document.createElement('span');coord.className='coord rank';coord.textContent=String(8-row);square.appendChild(coord);}}
      if(row===7){{const coord=document.createElement('span');coord.className='coord file';coord.textContent=files[file];square.appendChild(coord);}}
      fragment.appendChild(square);
    }});
  }});
  board.replaceChildren(fragment);
}}
function renderState(state){{
  if(state.fen!==lastRenderedFen){{
    renderBoard(state);
    lastRenderedFen=state.fen;
  }}
  document.getElementById('result').textContent=state.result||'Da disputare';
  document.getElementById('clock').textContent=state.clock_text||'Orologio non avviato';
  document.getElementById('turn').textContent='Muove il '+(state.turn||'—');
  document.getElementById('move-list').textContent=state.move_text||'Nessuna mossa registrata';
  document.getElementById('move-count').textContent=String(state.ply||0)+' ply';
  document.getElementById('board-status').textContent=state.result&&state.result!=='Da disputare'?'Partita conclusa':'Partita in corso';
}}
renderState(INITIAL_STATE);
let pollBusy=false;
async function poll(){{
  if(pollBusy||document.hidden)return;
  pollBusy=true;
  try{{
    const response=await fetch(STATE_URL+'&t='+Date.now(),{{cache:'no-store'}});
    if(response.ok)renderState(await response.json());
  }}catch(error){{}}
  finally{{pollBusy=false;}}
}}
window.setInterval(poll,350);
document.addEventListener('visibilitychange',()=>{{if(!document.hidden)poll();}});
</script></body></html>"""

    def portal_web_html(self):
        initial=self.public_portal_state()
        state_json=json.dumps(initial,ensure_ascii=True).replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
        api_path="/api/portal?token="+urllib.parse.quote(self.spectator_token,safe="")
        return f"""<!doctype html><html lang='it'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><meta name='theme-color' content='#101720'>
<title>Coppa dei 5 Re · Portale LIVE</title><style>
:root{{color-scheme:dark;--bg:#101720;--panel:#1b2633;--line:#344252;--gold:#e3c07f;--muted:#aab5c2}}
*{{box-sizing:border-box}}body{{margin:0;padding:clamp(12px,3vw,28px);background:var(--bg);color:#edf1f5;font-family:Segoe UI,Arial,sans-serif}}
main{{max-width:1500px;margin:auto}}header{{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:18px}}
.brand{{color:#c9a15b;font-weight:900;letter-spacing:2px}}.live{{color:#78d6a0;font-weight:900;font-size:13px}}
.summary{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:14px 0}}
.metric,.card{{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:16px}}
.metric b{{display:block;color:var(--gold);font-size:24px}}.metric span{{color:var(--muted);font-size:11px;letter-spacing:1px}}
.section-title{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:24px 0 12px}}
.games{{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:14px}}
.game{{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:14px;text-decoration:none;color:inherit;display:block;transition:border-color .15s,transform .15s}}
.game:hover{{border-color:var(--gold);transform:translateY(-2px)}}.game-head{{display:flex;justify-content:space-between;gap:8px;align-items:center;color:var(--muted);font-size:12px}}
.status{{font-weight:800;font-size:10px;letter-spacing:.7px;color:#9bd8b3}}.status.done{{color:var(--gold)}}.status.wait{{color:var(--muted)}}
.names{{display:flex;justify-content:space-between;gap:8px;margin:10px 0 6px;font-weight:800;font-size:14px}}.score{{color:var(--gold);text-align:center;font-weight:900;margin-bottom:8px}}
.mini{{width:min(100%,180px);margin:8px auto 10px;display:grid;grid-template-columns:repeat(8,1fr);aspect-ratio:1;overflow:hidden;border:2px solid #35465a;border-radius:5px}}
.sq{{display:grid;place-items:center;font:clamp(13px,2vw,21px) 'Segoe UI Symbol','DejaVu Sans',serif;line-height:1}}.light{{background:#f0d9b5;color:#fff}}.dark{{background:#b58863;color:#171717}}
.clock{{display:flex;justify-content:space-between;gap:8px;color:#d4dce4;font:12px ui-monospace,Consolas,monospace;margin-top:8px}}
.move{{font-size:11px;color:var(--muted);margin-top:7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.standings{{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
.standings th,.standings td{{padding:11px 9px;border-bottom:1px solid var(--line);text-align:left;font-size:13px}}
.standings th{{color:var(--gold);font-size:10px;letter-spacing:.8px}}.standings td:last-child,.standings th:last-child{{text-align:right;font-weight:900}}
.muted{{color:var(--muted);font-size:12px}}.footer{{text-align:center;color:var(--muted);font-size:11px;padding:22px}}
@media(max-width:560px){{.summary{{gap:7px}}.metric{{padding:10px}}.metric b{{font-size:19px}}.metric span{{font-size:9px}}.standings th,.standings td{{padding:9px 5px;font-size:11px}}}}
</style></head><body><main>
<header><div><div class='brand'>COPPA DEI 5 RE</div><div class='muted'>Portale pubblico · Tutti i tavoli</div></div><div class='live'>● LIVE · AGGIORNAMENTO AUTOMATICO</div></header>
<div class='summary'><div class='metric'><b id='live-count'>{initial['live']}</b><span>PARTITE IN CORSO</span></div><div class='metric'><b id='done-count'>{initial['completed']}</b><span>PARTITE CONCLUSE</span></div><div class='metric'><b id='updated'>{html.escape(initial['as_of'])}</b><span>ULTIMO AGGIORNAMENTO</span></div></div>
<div class='section-title'><strong>TUTTI I TAVOLI</strong><span class='muted'>Apri una partita per la scacchiera grande</span></div>
<div id='games' class='games'></div>
<div class='section-title'><strong>CLASSIFICA LIVE</strong><span class='muted'>Punti netti e risultati registrati</span></div>
<div class='card' style='padding:0;overflow:auto'><table class='standings'><thead><tr><th>POS</th><th>GIOCATORE</th><th>G</th><th>V</th><th>X</th><th>P</th><th>PUNTI</th></tr></thead><tbody id='ranking'></tbody></table></div>
<div class='footer'>Vista spettatore in sola lettura · Orologi e mosse provengono dalla Control Room Windows.</div>
</main><script>
const INITIAL={state_json};
const API={json.dumps(api_path)};
const GLYPHS={{K:'♔',Q:'♕',R:'♖',B:'♗',N:'♘',P:'♙',k:'♚',q:'♛',r:'♜',b:'♝',n:'♞',p:'♟'}};
const tokenQuery={json.dumps("?token="+urllib.parse.quote(self.spectator_token,safe=""))};
function miniBoard(fen){{
 const ranks=String(fen||'').split(' ')[0].split('/');
 const board=document.createElement('div');board.className='mini';
 ranks.forEach((rank,row)=>{{
  const cells=[];
  for(const token of rank){{
   if(/[1-8]/.test(token))for(let n=0;n<Number(token);n++)cells.push('');
   else cells.push(token);
  }}
  while(cells.length<8)cells.push('');
  cells.slice(0,8).forEach((token,col)=>{{
   const cell=document.createElement('div');cell.className='sq '+(((row+col)%2===1)?'dark':'light');
   cell.textContent=GLYPHS[token]||'';board.appendChild(cell);
  }});
 }});
 return board;
}}
function render(data){{
 document.getElementById('live-count').textContent=data.live||0;
 document.getElementById('done-count').textContent=data.completed||0;
 document.getElementById('updated').textContent=data.as_of||'—';
 const games=document.getElementById('games');games.replaceChildren();
 (data.matches||[]).forEach(match=>{{
  const link=document.createElement('a');link.className='game';
  link.href='/match/'+encodeURIComponent(match.game_id)+tokenQuery;
  const head=document.createElement('div');head.className='game-head';
  const round=document.createElement('span');round.textContent=match.round+' · '+match.game_id;
  const status=document.createElement('span');status.className='status '+(match.status==='CONCLUSA'?'done':(match.status==='DA GIOCARE'?'wait':''));
  status.textContent=match.status;
  head.append(round,status);link.append(head);
  const names=document.createElement('div');names.className='names';
  const white=document.createElement('span');white.textContent=match.white;
  const black=document.createElement('span');black.textContent=match.black;
  names.append(white,black);link.append(names);
  const score=document.createElement('div');score.className='score';score.textContent=match.result;
  link.append(score,miniBoard(match.fen));
  const clock=document.createElement('div');clock.className='clock';
  const wc=document.createElement('span');wc.textContent='B '+formatTime(match.clock_white);
  const bc=document.createElement('span');bc.textContent='N '+formatTime(match.clock_black);
  clock.append(wc,bc);link.append(clock);
  const moves=document.createElement('div');moves.className='move';moves.textContent=match.move_text;
  link.append(moves);games.append(link);
 }});
 const ranking=document.getElementById('ranking');ranking.replaceChildren();
 (data.standings||[]).forEach(row=>{{
  const tr=document.createElement('tr');
  [row.position,row.player,row.played,row.wins,row.draws,row.losses,Number(row.points).toFixed(1)].forEach((value,index)=>{{
   const td=document.createElement('td');td.textContent=String(value);tr.append(td);
  }});
  ranking.append(tr);
 }});
}}
function formatTime(seconds){{
 const n=Math.max(0,Math.ceil(Number(seconds)||0));
 return String(Math.floor(n/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0');
}}
render(INITIAL);
let busy=false;
async function poll(){{
 if(busy||document.hidden)return;busy=true;
 try{{const response=await fetch(API+'&t='+Date.now(),{{cache:'no-store'}});if(response.ok)render(await response.json());}}
 catch(error){{}}
 finally{{busy=false;}}
}}
setInterval(poll,1000);
document.addEventListener('visibilitychange',()=>{{if(!document.hidden)poll();}});
</script></body></html>"""

    def start_match_web_server(self,host_hint=None):
        if self.match_http_server is not None:
            return self.match_http_host,self.match_http_port
        app=self
        class MatchHandler(BaseHTTPRequestHandler):
            def send_content(self,status,content,content_type):
                body=content.encode("utf-8") if isinstance(content,str) else content
                self.send_response(status)
                self.send_header("Content-Type",content_type)
                self.send_header("Content-Length",str(len(body)))
                self.send_header("Cache-Control","no-store, max-age=0")
                self.send_header("X-Content-Type-Options","nosniff")
                self.end_headers()
                self.wfile.write(body)
            def do_GET(self):
                parsed=urllib.parse.urlparse(self.path)
                if parsed.path=="/health":
                    self.send_content(200,b"C5R local match server OK","text/plain; charset=utf-8")
                    return
                query=urllib.parse.parse_qs(parsed.query)
                token=query.get("token",[""])[0]
                if not app.valid_spectator_token(token):
                    self.send_error(403,"Link spettatore non valido o scaduto")
                    return
                if parsed.path=="/portal":
                    self.send_content(200,app.portal_web_html(),"text/html; charset=utf-8")
                    return
                if parsed.path=="/api/portal":
                    self.send_content(200,json.dumps(app.public_portal_state(),ensure_ascii=True),"application/json; charset=utf-8")
                    return
                if parsed.path.startswith("/api/match/"):
                    gid=urllib.parse.unquote(parsed.path[len("/api/match/"):])
                    state=app.match_web_state(gid)
                    if state is None:
                        self.send_error(404,"Partita non trovata")
                        return
                    self.send_content(200,json.dumps(state,ensure_ascii=True),"application/json; charset=utf-8")
                    return
                if parsed.path.startswith("/match/"):
                    gid=urllib.parse.unquote(parsed.path[len("/match/"):])
                    page=app.match_web_html(gid)
                    if page is None:
                        self.send_error(404,"Partita non trovata")
                        return
                    self.send_content(200,page,"text/html; charset=utf-8")
                    return
                self.send_error(404,"Not found")
            def log_message(self,format,*args):
                return
        last_error=None
        for port in range(8765,8775):
            try:
                server=ThreadingHTTPServer(("0.0.0.0",port),MatchHandler)
                server.daemon_threads=True
                self.match_http_server=server
                self.match_http_port=server.server_address[1]
                self.match_http_host=host_hint or self.local_network_ip()
                self.match_http_thread=threading.Thread(target=server.serve_forever,
                    name="C5R-Match-LAN",daemon=True)
                self.match_http_thread.start()
                if not self.match_http_host:
                    server.shutdown(); server.server_close()
                    self.match_http_server=None
                    raise RuntimeError("Non riesco a individuare un indirizzo della rete locale. Collega il PC al Wi-Fi/LAN e riprova.")
                return self.match_http_host,self.match_http_port
            except OSError as exc:
                last_error=exc
        message=f"Non è stato possibile avviare il server locale sulle porte 8765–8774: {last_error}"
        self.record_operational_alert("Server spettatori non disponibile",message,"danger","settings","local-server-bind-failed")
        raise RuntimeError(message)

    def match_web_url(self,gid,host_override=None,public=False):
        host,port=self.start_match_web_server(host_override)
        path="/match/"+urllib.parse.quote(gid,safe="")
        if public:
            if not self.public_base_url:
                raise ValueError("Configura prima un indirizzo pubblico HTTPS nelle Impostazioni.")
            base=self.public_base_url
        else:
            base=f"http://{host}:{port}"
        return base+path+"?token="+urllib.parse.quote(self.spectator_token,safe="")

    def portal_web_url(self,host_override=None,public=False):
        host,port=self.start_match_web_server(host_override)
        if public:
            if not self.public_base_url:
                raise ValueError("Configura prima un indirizzo pubblico HTTPS nelle Impostazioni.")
            base=self.public_base_url
        else:
            base=f"http://{host}:{port}"
        return base+"/portal?token="+urllib.parse.quote(self.spectator_token,safe="")

    def show_match_qr_dialog(self,gid):
        try:
            dialog=QDialog(self)
            dialog.setWindowTitle(f"QR · {gid}")
            dialog.resize(440,560)
            layout=QVBoxLayout(dialog)
            layout.addWidget(ui_label(f"QR TAVOLO · {gid}","h2",align=Qt.AlignmentFlag.AlignCenter))
            mode=QComboBox()
            mode.addItem("Rete Wi-Fi / LAN","local")
            if self.public_base_url:
                mode.addItem("Internet · HTTPS protetto","public")
                mode.setCurrentIndex(1)
            layout.addWidget(mode)
            image=QLabel(); image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(image)
            link=QLineEdit(); link.setReadOnly(True); link.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(link)
            hint=ui_label("Accesso da Internet disponibile solo quando il tunnel HTTPS è attivo e inoltra alla porta locale indicata nelle Impostazioni.","muted",wrap=True)
            layout.addWidget(hint)
            def update_link():
                try:
                    is_public=mode.currentData()=="public"
                    url=self.match_web_url(gid,public=is_public)
                    link.setText(url);image.setPixmap(self.make_qr_pixmap(url,270))
                    hint.setText(
                        f"Link pubblico HTTPS · token privato. Inoltra la porta locale {self.match_http_port} al PC arbitro."
                        if is_public else "Il telefono deve essere collegato alla stessa rete Wi-Fi/LAN del PC Windows."
                    )
                except Exception as exc:
                    link.clear();image.clear();hint.setText(str(exc))
            mode.currentIndexChanged.connect(update_link)
            update_link()
            buttons=QHBoxLayout()
            copy=QPushButton("COPIA LINK")
            copy.clicked.connect(lambda:QApplication.clipboard().setText(link.text()))
            open_local=QPushButton("APRI SUL PC")
            open_local.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(link.text())) if link.text() else None)
            close=QPushButton("CHIUDI");close.clicked.connect(dialog.accept)
            buttons.addWidget(copy);buttons.addWidget(open_local);buttons.addWidget(close)
            layout.addLayout(buttons)
            dialog.exec()
        except Exception as exc:
            QMessageBox.warning(self,"QR non disponibile",str(exc))

    def show_portal_qr_dialog(self):
        try:
            dialog=QDialog(self)
            dialog.setWindowTitle("QR · Portale di tutti i tavoli")
            dialog.resize(440,560)
            layout=QVBoxLayout(dialog)
            layout.addWidget(ui_label("PORTALE SPETTATORI","h2",align=Qt.AlignmentFlag.AlignCenter))
            layout.addWidget(ui_label("Un solo link per tutte le scacchiere, i cronometri e la classifica live.","muted",wrap=True))
            mode=QComboBox()
            mode.addItem("Rete Wi-Fi / LAN","local")
            if self.public_base_url:
                mode.addItem("Internet · HTTPS protetto","public")
                mode.setCurrentIndex(1)
            layout.addWidget(mode)
            image=QLabel();image.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(image)
            link=QLineEdit();link.setReadOnly(True);layout.addWidget(link)
            hint=ui_label("L'accesso remoto richiede un tunnel o reverse proxy HTTPS attivo verso il PC Windows.","muted",wrap=True)
            layout.addWidget(hint)
            def update_link():
                try:
                    is_public=mode.currentData()=="public"
                    url=self.portal_web_url(public=is_public)
                    link.setText(url);image.setPixmap(self.make_qr_pixmap(url,280))
                    hint.setText(
                        f"Portale HTTPS pubblico · inoltra la porta locale {self.match_http_port}; ogni accesso richiede il token privato."
                        if is_public else "Scansiona dalla stessa rete Wi-Fi/LAN del PC Windows."
                    )
                except Exception as exc:
                    link.clear();image.clear();hint.setText(str(exc))
            mode.currentIndexChanged.connect(update_link)
            update_link()
            buttons=QHBoxLayout()
            copy=QPushButton("COPIA LINK");copy.clicked.connect(lambda:QApplication.clipboard().setText(link.text()))
            open_btn=QPushButton("APRI SUL PC");open_btn.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(link.text())) if link.text() else None)
            close=QPushButton("CHIUDI");close.clicked.connect(dialog.accept)
            buttons.addWidget(copy);buttons.addWidget(open_btn);buttons.addWidget(close);layout.addLayout(buttons)
            dialog.exec()
        except Exception as exc:
            QMessageBox.warning(self,"Portale non disponibile",str(exc))

    def export_all_match_qr_pdf(self):
        try:
            host,port=self.start_match_web_server()
        except Exception as exc:
            QMessageBox.warning(self,"QR non disponibili",str(exc)); return
        path,_=QFileDialog.getSaveFileName(self,"Stampa QR dei tavoli","QR-Tavoli-C5R.pdf","PDF (*.pdf)")
        if not path:
            return
        writer=QPdfWriter(path); writer.setTitle("QR tavoli · Coppa dei 5 Re")
        writer.setCreator("Coppa dei 5 Re"); writer.setResolution(150)
        painter=QPainter(writer)
        try:
            margin=90; gap=35; columns=2; rows_per_page=3
            cell_w=(writer.width()-2*margin-gap)//columns
            cell_h=(writer.height()-2*margin-gap*(rows_per_page-1))//rows_per_page
            for index,(gid,rnd,white,black) in enumerate(GAMES):
                if index and index%(columns*rows_per_page)==0:
                    writer.newPage()
                local=index%(columns*rows_per_page)
                col=local%columns; row=local//columns
                x=margin+col*(cell_w+gap); y=margin+row*(cell_h+gap)
                painter.setPen(QPen(QColor("#C9A15B"),3))
                painter.setBrush(QColor("#FFFFFF"))
                painter.drawRoundedRect(QRect(x,y,cell_w,cell_h),18,18)
                url=f"http://{host}:{port}/match/{urllib.parse.quote(gid,safe='')}?token={urllib.parse.quote(self.spectator_token,safe='')}"
                pix=self.make_qr_pixmap(url,260)
                qr_size=min(300,cell_h-90)
                painter.drawPixmap(QRect(x+18,y+22,qr_size,qr_size),pix)
                tx=x+qr_size+36; tw=cell_w-qr_size-54
                painter.setPen(QColor("#17212B"))
                painter.setFont(QFont("Segoe UI",13,QFont.Weight.Bold))
                painter.drawText(QRect(tx,y+32,tw,50),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,
                                 f"ROUND {rnd} · {gid}")
                painter.setFont(QFont("Segoe UI",11))
                painter.drawText(QRect(tx,y+86,tw,100),Qt.TextFlag.TextWordWrap,
                                 f"{name(white)} – {name(black)}")
                painter.setFont(QFont("Segoe UI",8))
                painter.drawText(QRect(tx,y+cell_h-70,tw,54),Qt.TextFlag.TextWordWrap,
                                 "Scansiona dalla stessa rete Wi-Fi/LAN per aprire la pagina partita.")
        finally:
            painter.end()
        self.statusBar().showMessage("PDF con i QR dei 10 tavoli esportato.",3000)

    def _pdf_player_card(self,painter,rect,player_id):
        profile=self.player_profile_info(player_id)
        painter.setPen(QPen(QColor("#C9A15B"),3))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(rect,18,18)
        x,y,w,h=rect.x(),rect.y(),rect.width(),rect.height()
        painter.setPen(QColor("#9A6A18"))
        painter.setFont(QFont("Segoe UI",10,QFont.Weight.Bold))
        painter.drawText(QRect(x+24,y+18,w-48,35),"COPPA DEI 5 RE · PLAYER CARD")
        photo=self.player_photo_pixmap(player_id,210)
        painter.drawPixmap(QRect(x+25,y+65,150,150),photo)
        text_x=x+200
        painter.setPen(QColor("#17212B"))
        painter.setFont(QFont("Segoe UI",18,QFont.Weight.Bold))
        painter.drawText(QRect(text_x,y+65,w-230,42),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,name(player_id))
        painter.setFont(QFont("Segoe UI",10))
        age=f"{profile['age']} anni" if profile.get("age") else "Età non indicata"
        painter.drawText(QRect(text_x,y+112,w-230,26),age)
        username=profile.get("chesscom_username") or PLAYERS[player_id][1]
        painter.drawText(QRect(text_x,y+145,w-230,26),f"Chess.com · {username}")
        ratings=profile.get("ratings",{})
        painter.setFont(QFont("Segoe UI",10,QFont.Weight.Bold))
        rating_text="   ".join(f"{label} {ratings[kind] if ratings.get(kind) is not None else '—'}"
                              for label,kind in (("BULLET","bullet"),("BLITZ","blitz"),("RAPID","rapid")))
        painter.drawText(QRect(text_x,y+180,w-230,36),rating_text)
        bio=profile.get("bio","") or "Giocatore · Coppa dei 5 Re"
        painter.setFont(QFont("Segoe UI",9))
        painter.drawText(QRect(x+25,y+235,w-50,65),Qt.TextFlag.TextWordWrap,bio[:220])
        painter.setPen(QColor("#8793A1"))
        painter.setFont(QFont("Segoe UI",8))
        painter.drawText(QRect(x+25,y+h-38,w-50,22),
                         f"ID giocatore: {player_id} · Edizione: {datetime.now().strftime('%Y')}")

    def export_player_badges_pdf(self,player_ids=None):
        selected=list(player_ids or ORDER)
        path,_=QFileDialog.getSaveFileName(self,"Stampa tesserini giocatori","Tesserini-C5R.pdf","PDF (*.pdf)")
        if not path:
            return
        writer=QPdfWriter(path); writer.setTitle("Tesserini giocatori · Coppa dei 5 Re")
        writer.setCreator("Coppa dei 5 Re"); writer.setResolution(150)
        painter=QPainter(writer)
        try:
            margin=110; gap=45; cols=2; rows=2
            cell_w=(writer.width()-2*margin-gap)//cols
            cell_h=(writer.height()-2*margin-gap)//rows
            for index,player_id in enumerate(selected):
                if index and index%(cols*rows)==0:
                    writer.newPage()
                local=index%(cols*rows)
                col=local%cols; row=local//cols
                rect=QRect(margin+col*(cell_w+gap),margin+row*(cell_h+gap),cell_w,cell_h)
                self._pdf_player_card(painter,rect,player_id)
        finally:
            painter.end()
        self.statusBar().showMessage(f"Tesserini esportati: {len(selected)} giocatori.",3000)

    def export_current_player_badge(self):
        player_id=self.profile_combo.currentData()
        if player_id:
            self.export_player_badges_pdf([player_id])

    def export_match_sheet_pdf(self,gid,path=None,painter=None,writer=None):
        match=next((item for item in GAMES if item[0]==gid),None)
        if match:
            _,rnd,white,black=match
            round_label=f"Round {rnd}"
            result=self.results.get(gid) or "Da disputare"
        elif gid in ("sf1","sf2","third","final"):
            round_label="Playoff"
            white,black=getattr(self,"playoff_pairs",{}).get(gid,(None,None))
            result=self.playoff_results.get(gid) or "Da disputare"
        else:
            raise ValueError("Partita non riconosciuta.")
        own_painter=painter is None
        if own_painter:
            path,_=QFileDialog.getSaveFileName(self,"Stampa scheda partita",f"Scheda-{gid}.pdf","PDF (*.pdf)")
            if not path:
                return
            writer=QPdfWriter(path); writer.setTitle(f"Scheda partita {gid}")
            writer.setCreator("Coppa dei 5 Re"); writer.setResolution(150)
            painter=QPainter(writer)
        try:
            width=writer.width(); height=writer.height(); margin=145
            painter.setPen(QColor("#9A6A18"))
            painter.setFont(QFont("Segoe UI",20,QFont.Weight.Bold))
            painter.drawText(QRect(margin,margin,width-2*margin,55),"COPPA DEI 5 RE · SCHEDA PARTITA")
            painter.setPen(QColor("#5E6B79"))
            painter.setFont(QFont("Segoe UI",11))
            painter.drawText(QRect(margin,margin+60,width-2*margin,32),f"{round_label} · {gid}")
            player_y=margin+125
            card_w=(width-2*margin-40)//2
            for index,(label,player) in enumerate((("BIANCO",white),("NERO",black))):
                x=margin+index*(card_w+40)
                painter.setPen(QPen(QColor("#C9A15B"),2))
                painter.setBrush(QColor("#FFFFFF"))
                painter.drawRoundedRect(QRect(x,player_y,card_w,260),15,15)
                if player:
                    painter.drawPixmap(QRect(x+24,player_y+30,130,130),self.player_photo_pixmap(player,130))
                    painter.setPen(QColor("#17212B"))
                    painter.setFont(QFont("Segoe UI",16,QFont.Weight.Bold))
                    painter.drawText(QRect(x+170,player_y+25,card_w-190,45),name(player))
                    profile=self.player_profile_info(player); ratings=profile.get("ratings",{})
                    painter.setFont(QFont("Segoe UI",9))
                    painter.drawText(QRect(x+170,player_y+76,card_w-190,65),
                        f"Chess.com · {profile.get('chesscom_username') or PLAYERS[player][1]}\n"
                        f"Bullet {ratings.get('bullet') or '—'} · Blitz {ratings.get('blitz') or '—'} · Rapid {ratings.get('rapid') or '—'}")
                else:
                    painter.setPen(QColor("#8793A1"))
                    painter.setFont(QFont("Segoe UI",14,QFont.Weight.Bold))
                    painter.drawText(QRect(x+20,player_y+50,card_w-40,80),"Da definire")
                painter.setPen(QColor("#9A6A18"))
                painter.setFont(QFont("Segoe UI",10,QFont.Weight.Bold))
                painter.drawText(QRect(x+24,player_y+195,card_w-48,32),label)
            result_y=player_y+295
            painter.setPen(QColor("#17212B"))
            painter.setFont(QFont("Segoe UI",14,QFont.Weight.Bold))
            painter.drawText(QRect(margin,result_y,width-2*margin,38),f"RISULTATO: {result}")
            painter.setFont(QFont("Segoe UI",10))
            painter.drawText(QRect(margin,result_y+55,width-2*margin,34),
                             "Data: __________________________    Ora inizio: __________    Ora fine: __________")
            painter.drawText(QRect(margin,result_y+112,width-2*margin,34),
                             "Note / decisioni arbitrali: ________________________________________________")
            painter.drawText(QRect(margin,result_y+210,width-2*margin,38),
                             "Firma Bianco: ____________________     Firma Nero: ____________________")
            painter.drawText(QRect(margin,result_y+270,width-2*margin,38),
                             "Arbitro: _________________________________________________________________")
            painter.setPen(QColor("#8793A1"))
            painter.setFont(QFont("Segoe UI",8))
            painter.drawText(QRect(margin,height-95,width-2*margin,25),
                             f"Stampato il {datetime.now().strftime('%d/%m/%Y %H:%M')} · {self.referee or 'Direzione di gara'}")
        finally:
            if own_painter:
                painter.end()
        if own_painter:
            self.statusBar().showMessage(f"Scheda partita {gid} esportata.",3000)

    def export_all_match_sheets_pdf(self):
        path,_=QFileDialog.getSaveFileName(self,"Stampa schede di tutte le partite","Schede-Partita-C5R.pdf","PDF (*.pdf)")
        if not path:
            return
        writer=QPdfWriter(path); writer.setTitle("Schede partite · Coppa dei 5 Re")
        writer.setCreator("Coppa dei 5 Re"); writer.setResolution(150)
        painter=QPainter(writer)
        try:
            ids=[item[0] for item in GAMES]+["sf1","sf2","third","final"]
            for index,gid in enumerate(ids):
                if index:
                    writer.newPage()
                self.export_match_sheet_pdf(gid,painter=painter,writer=writer)
        finally:
            painter.end()
        self.statusBar().showMessage("Schede partite e playoff esportate in PDF.",3000)

    def build_players(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 30)
        layout.setSpacing(14)
        layout.addWidget(ui_label("Profili giocatori", "h1"))
        layout.addWidget(ui_label(
            "Schede individuali con rendimento, colori, precisione Stockfish, aperture e storico degli incontri.",
            "lead", wrap=True
        ))
        selector = Card("Seleziona partecipante", padding=14, spacing=8)
        self.profile_combo = QComboBox()
        for player_id in ORDER:
            self.profile_combo.addItem(name(player_id), player_id)
        selector.body.addWidget(self.profile_combo)
        layout.addWidget(selector)

        identity=Card("Scheda biografica","Foto profilo, informazioni personali e rating del profilo Chess.com.")
        identity_row=QHBoxLayout()
        self.profile_identity_photo=QLabel()
        self.profile_identity_photo.setFixedSize(116,116)
        self.profile_identity_photo.setStyleSheet("border: 2px solid #C9A15B; border-radius: 58px;")
        identity_row.addWidget(self.profile_identity_photo)
        identity_details=QVBoxLayout()
        self.profile_identity_name=ui_label("—","h2")
        self.profile_identity_meta=ui_label("Età e username Chess.com","muted")
        self.profile_identity_bio=ui_label("Biografia non ancora inserita.","body",wrap=True)
        identity_details.addWidget(self.profile_identity_name)
        identity_details.addWidget(self.profile_identity_meta)
        identity_details.addWidget(self.profile_identity_bio,1)
        edit_bio=QPushButton("MODIFICA SCHEDA")
        edit_bio.setObjectName("PrimaryButton")
        edit_bio.clicked.connect(lambda:self.edit_player_bio(self.profile_combo.currentData()))
        identity_details.addWidget(edit_bio,0,Qt.AlignmentFlag.AlignLeft)
        badge_actions=QHBoxLayout()
        print_badge=QPushButton("STAMPA TESSERINO")
        print_badge.clicked.connect(self.export_current_player_badge)
        print_all_badges=QPushButton("STAMPA TUTTI I TESSERINI")
        print_all_badges.clicked.connect(self.export_player_badges_pdf)
        badge_actions.addWidget(print_badge); badge_actions.addWidget(print_all_badges)
        identity_details.addLayout(badge_actions)
        identity_row.addLayout(identity_details,1)
        identity.body.addLayout(identity_row)
        rating_row=QHBoxLayout()
        self.profile_rating_tiles={
            "bullet":StatTile("BULLET","clock"),
            "blitz":StatTile("BLITZ","clock"),
            "rapid":StatTile("RAPID","clock"),
        }
        for tile in self.profile_rating_tiles.values():
            rating_row.addWidget(tile,1)
        identity.body.addLayout(rating_row)
        self.profile_rating_date=ui_label("Valori Chess.com non ancora inseriti.","caption")
        identity.body.addWidget(self.profile_rating_date)
        layout.addWidget(identity)

        metrics = QHBoxLayout()
        self.profile_tiles = {
            "points": StatTile("PUNTI NETTI", "trophy"),
            "record": StatTile("VITTORIE · PATTE · SCONFITTE", "chart"),
            "accuracy": StatTile("PRECISIONE STOCKFISH", "info"),
            "penalty": StatTile("PENALITÀ", "flag"),
        }
        for tile in self.profile_tiles.values():
            metrics.addWidget(tile, 1)
        layout.addLayout(metrics)
        color_card = Card("Rendimento per colore", "Risultati separati con i pezzi bianchi e neri.")
        self.profile_color_label = ui_label("—", "body", wrap=True)
        self.profile_opening_label = ui_label("Aperture più giocate: —", "muted", wrap=True)
        color_card.body.addWidget(self.profile_color_label)
        color_card.body.addWidget(self.profile_opening_label)
        layout.addWidget(color_card)
        history_card = Card("Storico partite", "Risultati e analisi disponibili per il partecipante selezionato.")
        self.profile_table = QTableWidget(0, 7)
        self.profile_table.setHorizontalHeaderLabels(
            ["ROUND", "PARTITA", "AVVERSARIO", "COLORE", "ESITO", "APERTURA", "PRECISIONE"]
        )
        self.profile_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        style_table(self.profile_table, row_height=40, selectable=False)
        history_card.body.addWidget(self.profile_table)
        layout.addWidget(history_card, 1)
        self.profile_combo.currentIndexChanged.connect(self.refresh_player_profile)
        return page

    def refresh_player_profile(self):
        if not hasattr(self, "profile_combo"):
            return
        player_id = self.profile_combo.currentData()
        if player_id not in PLAYERS:
            return
        data = self.player_profile_data(player_id)
        self.refresh_player_identity(player_id)
        self.profile_tiles["points"].set(f"{data['points']:.1f}", f"{data['played']}/5 partite conteggiate")
        self.profile_tiles["record"].set(
            f"{data['wins']} · {data['draws']} · {data['losses']}",
            "Vittorie · patte · sconfitte"
        )
        self.profile_tiles["accuracy"].set(
            "—" if data["accuracy"] is None else f"{data['accuracy']:.1f}%",
            f"{data['reviewed_moves']} mosse valutate" if data["reviewed_moves"] else "Nessuna analisi disponibile"
        )
        self.profile_tiles["penalty"].set(f"{data['penalty']:+.1f}", "Detrazioni registrate")
        white = data["colors"]["white"]
        black = data["colors"]["black"]
        self.profile_color_label.setText(
            f"BIANCO  ·  {white['wins']} vittorie / {white['draws']} patte / {white['losses']} sconfitte"
            f"        NERO  ·  {black['wins']} vittorie / {black['draws']} patte / {black['losses']} sconfitte"
        )
        popular = sorted(data["openings"].items(), key=lambda item: (-item[1], item[0]))[:3]
        self.profile_opening_label.setText(
            "Aperture più giocate: " + (" · ".join(f"{opening} ({count})" for opening, count in popular) if popular else "—")
        )
        self.profile_table.setRowCount(len(data["history"]))
        for row, item in enumerate(data["history"]):
            values = [
                f"R{item['round']}", item["gid"], name(item["opponent"]),
                "Bianco" if item["color"] == "white" else "Nero",
                item["outcome"], item["opening"],
                "—" if item["accuracy"] is None else f"{item['accuracy']:.1f}%"
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if col in (0, 1, 3, 4, 6):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.profile_table.setItem(row, col, cell)

    def build_communications(self):
        page=QWidget()
        layout=QVBoxLayout(page)
        layout.setContentsMargins(26,24,26,30)
        layout.setSpacing(14)
        layout.addWidget(ui_label("Comunicazioni ai giocatori","h1"))
        layout.addWidget(ui_label(
            "Prepara convocazioni, variazioni e risultati con testi personalizzati per ogni giocatore. "
            "L'app apre il compositore WhatsApp o email: l'invio resta sempre sotto il tuo controllo.",
            "lead",wrap=True))
        setup=Card("1 · Destinatari e contenuto","Compila i recapiti nelle schede giocatore. Seleziona uno o più destinatari.")
        columns=QHBoxLayout()
        left=QVBoxLayout()
        left.addWidget(ui_label("DESTINATARI","field"))
        self.notify_recipients=QListWidget()
        for player_id in ORDER:
            item=QListWidgetItem(name(player_id))
            item.setData(Qt.ItemDataRole.UserRole,player_id)
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            contact=self.player_profile_info(player_id)
            item.setToolTip(f"Email: {contact.get('email') or 'non inserita'} · WhatsApp: {contact.get('whatsapp') or 'non inserito'}")
            self.notify_recipients.addItem(item)
        left.addWidget(self.notify_recipients)
        pick_buttons=QHBoxLayout()
        all_btn=QPushButton("TUTTI")
        none_btn=QPushButton("NESSUNO")
        all_btn.clicked.connect(lambda:self.set_notification_recipients(True))
        none_btn.clicked.connect(lambda:self.set_notification_recipients(False))
        pick_buttons.addWidget(all_btn); pick_buttons.addWidget(none_btn)
        left.addLayout(pick_buttons)
        columns.addLayout(left,1)
        right=QVBoxLayout()
        self.notify_template=QComboBox()
        self.notify_template.addItem("Convocazione partita","convocation")
        self.notify_template.addItem("Variazione calendario","schedule")
        self.notify_template.addItem("Risultato partita","result")
        self.notify_template.addItem("Messaggio personalizzato","custom")
        self.notify_game=QComboBox()
        self.notify_game.addItem("Comunicazione generale","")
        for gid,rnd,white,black in GAMES:
            self.notify_game.addItem(f"Round {rnd} · {gid} · {name(white)} – {name(black)}",gid)
        self.notify_game.addItem("Playoff · Semifinale 1","sf1")
        self.notify_game.addItem("Playoff · Semifinale 2","sf2")
        self.notify_game.addItem("Playoff · 3° / 4° posto","third")
        self.notify_game.addItem("Playoff · Finale","final")
        self.notify_datetime=QDateTimeEdit(QDateTime.currentDateTime())
        self.notify_datetime.setCalendarPopup(True)
        self.notify_datetime.setDisplayFormat("dd/MM/yyyy HH:mm")
        right.addWidget(ui_label("TIPO DI COMUNICAZIONE","field"))
        right.addWidget(self.notify_template)
        right.addWidget(ui_label("PARTITA / TAVOLO","field"))
        right.addWidget(self.notify_game)
        right.addWidget(ui_label("DATA E ORA CONVOCAZIONE (SE PREVISTA)","field"))
        right.addWidget(self.notify_datetime)
        right.addWidget(ui_label("TESTO DEL MESSAGGIO","field"))
        self.notify_message=QPlainTextEdit()
        self.notify_message.setMinimumHeight(180)
        self.notify_message.setPlaceholderText("Scrivi qui il messaggio da inviare ai giocatori…")
        right.addWidget(self.notify_message,1)
        generate=QPushButton("GENERA MESSAGGI PERSONALIZZATI")
        generate.setObjectName("PrimaryButton")
        generate.clicked.connect(self.generate_player_notifications)
        right.addWidget(generate)
        columns.addLayout(right,2)
        setup.body.addLayout(columns)
        layout.addWidget(setup)

        outbox=Card("2 · Coda comunicazioni","Ogni messaggio viene preparato separatamente per il destinatario selezionato.")
        self.notify_outbox_table=QTableWidget(0,5)
        self.notify_outbox_table.setHorizontalHeaderLabels(["DESTINATARIO","TITOLO","EMAIL","WHATSAPP","STATO"])
        self.notify_outbox_table.verticalHeader().setVisible(False)
        self.notify_outbox_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.notify_outbox_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.notify_outbox_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.notify_outbox_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        for col in (0,2,3,4):
            self.notify_outbox_table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.ResizeToContents)
        style_table(self.notify_outbox_table,row_height=42,selectable=True)
        self.notify_outbox_table.itemSelectionChanged.connect(self.refresh_notification_preview)
        outbox.body.addWidget(table_card(self.notify_outbox_table))
        actions=QHBoxLayout()
        self.notify_preview=ui_label("Seleziona un messaggio generato per visualizzarne il contenuto.", "muted",wrap=True)
        preview_wrap=QVBoxLayout(); preview_wrap.addWidget(self.notify_preview)
        actions.addLayout(preview_wrap,1)
        copy_btn=QPushButton("COPIA TESTO")
        copy_btn.clicked.connect(self.copy_selected_notification)
        email_btn=QPushButton("APRI EMAIL")
        email_btn.clicked.connect(lambda:self.open_selected_notification("email"))
        whats_btn=QPushButton("APRI WHATSAPP")
        whats_btn.setObjectName("PrimaryButton")
        whats_btn.clicked.connect(lambda:self.open_selected_notification("whatsapp"))
        actions.addWidget(copy_btn); actions.addWidget(email_btn); actions.addWidget(whats_btn)
        outbox.body.addLayout(actions)
        layout.addWidget(outbox,1)
        self.notify_template.currentIndexChanged.connect(self.update_notification_template)
        self.notify_game.currentIndexChanged.connect(self.update_notification_template)
        self.update_notification_template()
        return page

    def set_notification_recipients(self,checked):
        if not hasattr(self,"notify_recipients"):
            return
        state=Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in range(self.notify_recipients.count()):
            self.notify_recipients.item(index).setCheckState(state)

    def notification_context(self,gid):
        if not gid:
            return {"game":"","round":"","table":"","white":"","black":"","result":"","datetime":self.notify_datetime.dateTime().toString("dd/MM/yyyy HH:mm")}
        if gid in ("sf1","sf2","third","final"):
            labels={"sf1":"Semifinale 1","sf2":"Semifinale 2","third":"3° / 4° posto","final":"Finale"}
            pair=getattr(self,"playoff_pairs",{}).get(gid,(None,None))
            white,black=pair
            return {"game":labels[gid],"round":"Playoff","table":labels[gid],
                    "white":name(white) if white else "Da definire",
                    "black":name(black) if black else "Da definire",
                    "result":self.playoff_results.get(gid) or "Da disputare",
                    "datetime":self.notify_datetime.dateTime().toString("dd/MM/yyyy HH:mm")}
        match=next((item for item in GAMES if item[0]==gid),None)
        if not match:
            return {"game":gid,"round":"","table":gid,"white":"","black":"","result":"","datetime":""}
        _gid,rnd,white,black=match
        return {"game":gid,"round":f"Round {rnd}","table":gid,
                "white":name(white),"black":name(black),
                "result":self.results.get(gid) or "Da disputare",
                "datetime":self.notify_datetime.dateTime().toString("dd/MM/yyyy HH:mm")}

    def notification_message_for(self,player_id,template,gid,custom_text=""):
        ctx=self.notification_context(gid)
        opponent=""
        if gid and gid not in ("sf1","sf2","third","final"):
            match=next((item for item in GAMES if item[0]==gid),None)
            if match:
                opponent=name(match[3] if match[2]==player_id else match[2])
        if template=="convocation":
            if gid and ctx["white"] and ctx["black"]:
                return (f"Ciao {name(player_id)}!\n"
                    f"Sei convocato per {ctx['round']} · {ctx['table']}.\n"
                    f"Partita: {ctx['white']} – {ctx['black']}.\n"
                    f"Orario: {ctx['datetime']}.\n"
                    f"Ricordati di essere pronto qualche minuto prima.\n"
                    "Coppa dei 5 Re")
            return f"Ciao {name(player_id)}! Ti ricordiamo la prossima attività della Coppa dei 5 Re. A presto!"
        if template=="schedule":
            return (f"Ciao {name(player_id)}, aggiornamento calendario Coppa dei 5 Re.\n"
                f"{ctx['round']} · {ctx['table']} · {ctx['white']} – {ctx['black']}.\n"
                f"Orario indicato: {ctx['datetime']}.\nControlla il calendario aggiornato.")
        if template=="result":
            return (f"Ciao {name(player_id)}!\nAggiornamento risultato {ctx['game']}: "
                f"{ctx['white']} – {ctx['black']} · {ctx['result']}.\n"
                f"Coppa dei 5 Re")
        tokens={"nome":name(player_id),"avversario":opponent,"partita":ctx["game"],
                "tavolo":ctx["table"],"orario":ctx["datetime"],"bianco":ctx["white"],
                "nero":ctx["black"],"risultato":ctx["result"]}
        message=str(custom_text or "")
        for token,value in tokens.items():
            message=message.replace("{"+token+"}",str(value))
        return message

    def update_notification_template(self):
        if not hasattr(self,"notify_message"):
            return
        template=self.notify_template.currentData()
        gid=self.notify_game.currentData()
        self.notify_message.setPlainText(
            self.notification_message_for(ORDER[0],template,gid,
                "Ciao {nome}, ti scriviamo per {partita}. Tavolo: {tavolo}. Orario: {orario}.")
        )

    def generate_player_notifications(self):
        if not hasattr(self,"notify_recipients"):
            return
        recipients=[self.notify_recipients.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.notify_recipients.count())
            if self.notify_recipients.item(i).checkState()==Qt.CheckState.Checked]
        if not recipients:
            QMessageBox.information(self,"Nessun destinatario","Seleziona almeno un giocatore.")
            return
        custom=self.notify_message.toPlainText().strip()
        template=self.notify_template.currentData()
        gid=self.notify_game.currentData() or ""
        if not custom:
            QMessageBox.warning(self,"Messaggio vuoto","Inserisci un testo prima di generare le comunicazioni.")
            return
        title=self.notify_template.currentText()
        batch_id=uuid.uuid4().hex[:10]
        created=datetime.now().isoformat(timespec="seconds")
        generated=[]
        context=self.notification_context(gid)
        match=next((item for item in GAMES if item[0]==gid),None)
        playoff_pair=getattr(self,"playoff_pairs",{}).get(gid,(None,None)) if gid in ("sf1","sf2","third","final") else (None,None)
        for player_id in recipients:
            if template in ("convocation","result") and gid:
                participants=(match[2],match[3]) if match else playoff_pair
                if participants and player_id not in participants:
                    continue
            profile=self.player_profile_info(player_id)
            body=self.notification_message_for(player_id,template,gid,custom if template=="custom" else "")
            if template=="custom" and not body.strip():
                continue
            draft={"id":uuid.uuid4().hex[:12],"batch":batch_id,"player_id":player_id,
                   "title":title,"body":body,"email":profile.get("email",""),
                   "whatsapp":profile.get("whatsapp",""),"created_at":created,"status":"Bozza"}
            generated.append(draft)
        if not generated:
            QMessageBox.warning(self,"Nessun messaggio","Non è stato possibile generare i messaggi selezionati.")
            return
        self.notification_drafts.extend(generated)
        self.log_operation("Comunicazioni preparate","", "—",f"{len(generated)} messaggi",title)
        self.save()
        self.refresh_communications()
        self.notify_outbox_table.selectRow(0)
        self.statusBar().showMessage(f"Preparati {len(generated)} messaggi: scegli email o WhatsApp per aprire il compositore.",4500)

    def refresh_communications(self):
        if not hasattr(self,"notify_outbox_table"):
            return
        drafts=self.notification_drafts[-250:][::-1]
        self._visible_notification_drafts=drafts
        self.notify_outbox_table.setRowCount(len(drafts))
        for row,draft in enumerate(drafts):
            values=[name(draft.get("player_id","")),draft.get("title",""),
                    "Sì" if draft.get("email") else "No",
                    "Sì" if draft.get("whatsapp") else "No",draft.get("status","Bozza")]
            for col,value in enumerate(values):
                item=QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole,draft.get("id"))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.notify_outbox_table.setItem(row,col,item)
        self.refresh_notification_preview()

    def selected_notification_draft(self):
        if not hasattr(self,"notify_outbox_table"):
            return None
        rows=self.notify_outbox_table.selectionModel().selectedRows()
        if not rows:
            return None
        row=rows[0].row()
        if 0<=row<len(self._visible_notification_drafts):
            return self._visible_notification_drafts[row]
        return None

    def refresh_notification_preview(self):
        if not hasattr(self,"notify_preview"):
            return
        draft=self.selected_notification_draft()
        self.notify_preview.setText(
            f"{name(draft['player_id'])} · {draft['title']}\n\n{draft['body']}"
            if draft else "Seleziona un messaggio generato per visualizzarne il contenuto."
        )

    def copy_selected_notification(self):
        draft=self.selected_notification_draft()
        if not draft:
            QMessageBox.information(self,"Nessun messaggio","Seleziona una comunicazione generata.")
            return
        QApplication.clipboard().setText(draft["body"])
        self.statusBar().showMessage("Testo copiato negli appunti.",2500)

    def notification_compose_url(self,draft,channel):
        if channel=="email":
            address=draft.get("email","")
            if not address:
                raise ValueError("Nella scheda del giocatore non è stato inserito un indirizzo email.")
            return QUrl("mailto:"+quote(address,safe="@.")+"?"+urlencode({
                "subject":"Coppa dei 5 Re · "+draft.get("title","Comunicazione"),
                "body":draft.get("body","")}))
        if channel=="whatsapp":
            number=re.sub(r"\D","",draft.get("whatsapp",""))
            if not number:
                raise ValueError("Nella scheda del giocatore non è stato inserito un numero WhatsApp.")
            return QUrl("https://wa.me/"+number+"?"+urlencode({"text":draft.get("body","")}))
        raise ValueError("Canale di comunicazione non riconosciuto.")

    def open_selected_notification(self,channel):
        draft=self.selected_notification_draft()
        if not draft:
            QMessageBox.information(self,"Nessun messaggio","Seleziona una comunicazione generata.")
            return
        try:
            url=self.notification_compose_url(draft,channel)
        except ValueError as exc:
            QMessageBox.warning(self,"Recapito mancante",str(exc))
            return
        QDesktopServices.openUrl(url)
        draft["status"]="Compositore aperto"
        self.save()
        self.refresh_communications()

    def build_compare(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 30)
        layout.setSpacing(14)
        layout.addWidget(ui_label("Confronto giocatori", "h1"))
        layout.addWidget(ui_label(
            "Confronta rendimento, risultati con ciascun colore, precisione analitica e scontro diretto.",
            "lead", wrap=True
        ))
        selectors = Card("Partecipanti", padding=14)
        row = QHBoxLayout()
        self.compare_left = QComboBox()
        self.compare_right = QComboBox()
        for player_id in ORDER:
            self.compare_left.addItem(name(player_id), player_id)
            self.compare_right.addItem(name(player_id), player_id)
        self.compare_right.setCurrentIndex(1 if len(ORDER) > 1 else 0)
        row.addWidget(ui_label("GIOCATORE A", "field"))
        row.addWidget(self.compare_left, 1)
        row.addWidget(ui_label("GIOCATORE B", "field"))
        row.addWidget(self.compare_right, 1)
        selectors.body.addLayout(row)
        layout.addWidget(selectors)
        panels = QHBoxLayout()
        self.compare_tiles = []
        for heading in ("GIOCATORE A", "GIOCATORE B"):
            panel = Card(heading, padding=14)
            tiles = {
                "points": StatTile("PUNTI NETTI", "trophy"),
                "record": StatTile("V · X · P", "chart"),
                "accuracy": StatTile("PRECISIONE", "info"),
            }
            for tile in tiles.values():
                panel.body.addWidget(tile)
            self.compare_tiles.append(tiles)
            panels.addWidget(panel, 1)
        layout.addLayout(panels)
        self.compare_direct = Card("Scontro diretto", padding=14)
        self.compare_direct_label = ui_label("Seleziona due giocatori diversi.", "h3", wrap=True)
        self.compare_direct.body.addWidget(self.compare_direct_label)
        self.compare_direct_detail = ui_label("", "muted", wrap=True)
        self.compare_direct.body.addWidget(self.compare_direct_detail)
        layout.addWidget(self.compare_direct)
        self.compare_table_card = Card("Partite tra i due giocatori", "Storico ufficiale degli scontri diretti del girone.")
        self.compare_table = QTableWidget(0, 5)
        self.compare_table.setHorizontalHeaderLabels(["ROUND", "BIANCO", "NERO", "RISULTATO", "APERTURA"])
        self.compare_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.compare_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        style_table(self.compare_table, row_height=42, selectable=False)
        self.compare_table_card.body.addWidget(self.compare_table)
        layout.addWidget(self.compare_table_card, 1)
        self.compare_left.currentIndexChanged.connect(self.refresh_compare)
        self.compare_right.currentIndexChanged.connect(self.refresh_compare)
        return page

    def refresh_compare(self):
        if not hasattr(self, "compare_left"):
            return
        left_id, right_id = self.compare_left.currentData(), self.compare_right.currentData()
        for index, player_id in enumerate((left_id, right_id)):
            data = self.player_profile_data(player_id)
            tiles = self.compare_tiles[index]
            tiles["points"].set(f"{data['points']:.1f}", f"{data['played']}/5 partite")
            tiles["record"].set(f"{data['wins']} · {data['draws']} · {data['losses']}", "Vittorie · patte · sconfitte")
            tiles["accuracy"].set(
                "—" if data["accuracy"] is None else f"{data['accuracy']:.1f}%",
                f"{data['reviewed_moves']} mosse valutate"
            )
        if left_id == right_id:
            self.compare_direct_label.setText("Scegli due giocatori diversi per il confronto diretto.")
            self.compare_direct_detail.setText("")
            self.compare_table.setRowCount(0)
            return
        direct = []
        for gid, rnd, white, black in GAMES:
            if frozenset((white, black)) == frozenset((left_id, right_id)):
                direct.append((gid, rnd, white, black, self.results.get(gid)))
        self.compare_table.setRowCount(len(direct))
        for row, (gid, rnd, white, black, result) in enumerate(direct):
            values = [f"R{rnd}", name(white), name(black), result or "—", self.opening_name(gid)]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if col in (0, 3):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.compare_table.setItem(row, col, cell)
        if not direct or direct[0][4] in (None, "VOID"):
            self.compare_direct_label.setText("Scontro diretto non ancora disputato.")
            self.compare_direct_detail.setText("Il risultato verrà mostrato automaticamente quando sarà registrato.")
        else:
            gid, rnd, white, black, result = direct[0]
            winner = "Patta" if result == "1/2-1/2" else name(white if result == "1-0" else black)
            self.compare_direct_label.setText(f"{name(left_id)}  vs  {name(right_id)}  ·  {winner}")
            self.compare_direct_detail.setText(
                f"Round {rnd} · {gid} · {result} · {self.opening_name(gid)}"
            )

    def opening_name(self, game_id):
        board = chess.Board()
        san_moves = []
        for uci in self.moves.get(game_id, []):
            try:
                move = chess.Move.from_uci(uci)
                if move not in board.legal_moves:
                    break
                san_moves.append(board.san(move))
                board.push(move)
            except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError):
                break
        moves = tuple(san_moves)
        patterns = [
            (("e4", "e5", "Nf3", "Nc6", "Bb5"), "Spagnola · Ruy Lopez"),
            (("e4", "e5", "Nf3", "Nc6", "Bc4"), "Italiana"),
            (("e4", "e5", "Nf3", "Nc6", "d4"), "Scozzese"),
            (("e4", "e5", "Nf3", "Nf6"), "Petrov"),
            (("e4", "c5"), "Siciliana"),
            (("e4", "e6"), "Francese"),
            (("e4", "c6"), "Caro-Kann"),
            (("d4", "d5", "c4"), "Gambetto di Donna"),
            (("d4", "Nf6", "c4", "g6"), "Indiana di Re"),
            (("d4", "Nf6", "Bf4"), "Sistema Londra"),
            (("c4",), "Apertura Inglese"),
            (("Nf3",), "Apertura Réti"),
            (("e4",), "Apertura Re"),
            (("d4",), "Apertura Donna"),
        ]
        for prefix, label in patterns:
            if len(moves) >= len(prefix) and moves[:len(prefix)] == prefix:
                return label
        return "Non classificata"

    def build_openings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 30)
        layout.setSpacing(14)
        layout.addWidget(ui_label("Opening Explorer", "h1"))
        layout.addWidget(ui_label(
            "Raggruppa le partite registrate per apertura riconosciuta dalla sequenza iniziale di mosse. "
            "Il catalogo locale copre le linee più comuni; le altre restano non classificate.",
            "lead", wrap=True
        ))
        summary = Card("Distribuzione aperture", "Conteggi calcolati dai PGN e dalle mosse salvate localmente.")
        self.opening_summary = ui_label("Nessuna apertura ancora disponibile.", "body", wrap=True)
        summary.body.addWidget(self.opening_summary)
        layout.addWidget(summary)
        filters = Card("Filtra per apertura", padding=14)
        row = QHBoxLayout()
        self.opening_filter = QComboBox()
        self.opening_filter.addItem("Tutte le aperture", None)
        row.addWidget(self.opening_filter, 1)
        filters.body.addLayout(row)
        self.opening_filter.currentIndexChanged.connect(self.refresh_openings)
        layout.addWidget(filters)
        table_card_widget = Card("Partite riconosciute", "La classificazione si basa sulle prime mosse effettivamente registrate.")
        self.opening_table = QTableWidget(0, 6)
        self.opening_table.setHorizontalHeaderLabels(["PARTITA", "ROUND", "BIANCO", "NERO", "APERTURA", "RISULTATO"])
        self.opening_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        style_table(self.opening_table, row_height=42, selectable=False)
        table_card_widget.body.addWidget(self.opening_table)
        layout.addWidget(table_card_widget, 1)
        return page

    def refresh_openings(self):
        if not hasattr(self, "opening_filter"):
            return
        all_rows = []
        counts = {}
        for gid, rnd, white, black in GAMES:
            opening = self.opening_name(gid)
            counts[opening] = counts.get(opening, 0) + 1
            all_rows.append((gid, rnd, white, black, opening, self.results.get(gid)))
        selected = self.opening_filter.currentData()
        self.opening_filter.blockSignals(True)
        self.opening_filter.clear()
        self.opening_filter.addItem("Tutte le aperture", None)
        for opening in sorted(counts):
            self.opening_filter.addItem(f"{opening} · {counts[opening]}", opening)
        index = self.opening_filter.findData(selected)
        self.opening_filter.setCurrentIndex(max(0, index))
        self.opening_filter.blockSignals(False)
        self.opening_summary.setText(
            "   ·   ".join(f"{opening}: {count}" for opening, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])))
        )
        visible = [row for row in all_rows if selected is None or row[4] == selected]
        self.opening_table.setRowCount(len(visible))
        for row_index, (gid, rnd, white, black, opening, result) in enumerate(visible):
            values = [gid, f"R{rnd}", name(white), name(black), opening, result or "—"]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if col in (0, 1, 5):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.opening_table.setItem(row_index, col, cell)

    def health_check(self):
        findings = []
        def add(severity, title, detail):
            findings.append((severity, title, detail))
        try:
            validate_schedule(GAMES)
        except Exception as exc:
            add("ERRORE", "Calendario non valido", str(exc))
        allowed_results = {None, "1-0", "0-1", "1/2-1/2", "VOID"}
        valid_ids = {gid for gid, _, _, _ in GAMES}
        for gid, result in self.results.items():
            if gid not in valid_ids and gid not in ("sf1", "sf2", "final", "third"):
                add("ERRORE", "Risultato orfano", f"{gid}: la partita non esiste nel calendario attuale.")
            elif result not in allowed_results:
                add("ERRORE", "Risultato non riconosciuto", f"{gid}: valore {result!r}.")
        for gid, moves in self.moves.items():
            if gid not in valid_ids:
                add("AVVISO", "Mosse senza partita", f"{gid}: sono presenti mosse ma non una partita del girone.")
                continue
            board = chess.Board()
            try:
                for ply, uci in enumerate(moves, 1):
                    move = chess.Move.from_uci(uci)
                    if move not in board.legal_moves:
                        raise ValueError(f"mossa {ply} non legale ({uci})")
                    board.push(move)
            except Exception as exc:
                add("ERRORE", "Sequenza mosse non valida", f"{gid}: {exc}")
        for gid, clock in self.clocks.items():
            for side in ("white", "black"):
                try:
                    if int(clock.get(side, 0)) < 0:
                        add("ERRORE", "Cronometro negativo", f"{gid}: tempo {side} sotto zero.")
                except (TypeError, ValueError):
                    add("ERRORE", "Cronometro non valido", f"{gid}: tempo {side} non numerico.")
        for player_id in self.withdrawn_players:
            if player_id not in PLAYERS:
                add("ERRORE", "Ritiro sconosciuto", f"ID giocatore non valido: {player_id}.")
        for round_key in self.round_closures:
            try:
                round_number = int(round_key)
                games = [gid for gid, rnd, _, _ in GAMES if rnd == round_number]
                unresolved = [gid for gid in games if self.results.get(gid) is None]
                if unresolved:
                    add("ERRORE", "Turno chiuso ma incompleto",
                        f"Round {round_number}: risultati mancanti per {', '.join(unresolved)}.")
            except (TypeError, ValueError):
                add("ERRORE", "Chiusura turno non valida", f"Chiave round non valida: {round_key}.")
        for gid, plies in self.move_annotations.items():
            if gid not in valid_ids:
                add("AVVISO", "Annotazioni orfane", f"{gid}: annotazioni collegate a una partita non presente.")
                continue
            for ply, annotation in plies.items():
                if not str(ply).isdigit() or int(ply) < 1 or not isinstance(annotation, dict):
                    add("AVVISO", "Annotazione non valida", f"{gid}: annotazione della mossa {ply} non leggibile.")
        incident_ids=set()
        for report in getattr(self,"incident_reports",[]):
            if not isinstance(report,dict):
                add("ERRORE","Verbale non valido","È presente un elemento verbale non leggibile.")
                continue
            report_id=str(report.get("id",""))
            if not report_id or report_id in incident_ids:
                add("ERRORE","Identificativo verbale non valido",f"Identificativo mancante o duplicato: {report_id or '—'}.")
            incident_ids.add(report_id)
            for field in ("category","summary","description","status","created_at"):
                if not str(report.get(field,"")).strip():
                    add("AVVISO","Verbale incompleto",f"{report_id}: campo obbligatorio '{field}' mancante.")
            game_id=report.get("game_id","")
            if game_id and game_id not in valid_ids and game_id not in ("sf1","sf2","final","third"):
                add("AVVISO","Riferimento verbale non riconosciuto",
                    f"{report_id}: la partita {game_id} non è nel calendario attuale; il testo storico è comunque conservato.")
            for attachment in report.get("attachments",[]):
                try:
                    evidence=self.incident_attachment_path(attachment.get("path",""))
                    if not evidence.is_file():
                        add("AVVISO","Allegato verbale mancante",
                            f"{report_id}: non è disponibile il file {attachment.get('name',evidence.name)}.")
                except Exception as exc:
                    add("ERRORE","Percorso allegato non valido",f"{report_id}: {exc}.")
        try:
            for gid in valid_ids:
                node = self.build_pgn_game(gid)
                if node.errors:
                    add("ERRORE", "PGN non valido", f"{gid}: {node.errors[0]}")
        except Exception as exc:
            add("ERRORE", "Errore durante la verifica PGN", str(exc))
        if not findings:
            add("OK", "Nessuna anomalia rilevata", "Calendario, risultati, mosse, cronometri e PGN sono coerenti.")
        return findings

    def run_health_check(self):
        findings = self.health_check()
        self._health_findings = findings
        errors = sum(1 for severity, _, _ in findings if severity == "ERRORE")
        warnings = sum(1 for severity, _, _ in findings if severity == "AVVISO")
        if hasattr(self, "health_summary"):
            self.health_summary.setText(
                f"{errors} errori · {warnings} avvisi · {len(findings) - errors - warnings} controlli positivi"
            )
            self.health_list.clear()
            for severity, title, detail in findings:
                self.health_list.addItem(f"[{severity}]  {title}\n{detail}")
        self.statusBar().showMessage(
            "Health Check completato: " + (f"{errors} errori, {warnings} avvisi." if errors or warnings else "nessuna anomalia."),
            5000
        )
        self.refresh_notification_badge()
        return findings

    def build_health(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 30)
        layout.setSpacing(14)
        layout.addWidget(ui_label("Tournament Health Check", "h1"))
        layout.addWidget(ui_label(
            "Verifica coerenza di calendario, risultati, mosse, cronometri, PGN, verbali e relativi allegati.",
            "lead", wrap=True
        ))
        health_card = Card("Integrità del torneo", "Esegui la verifica prima di chiudere un round o esportare il torneo.")
        actions = QHBoxLayout()
        run = QPushButton("ESEGUI CONTROLLO")
        run.setObjectName("PrimaryButton")
        run.clicked.connect(self.run_health_check)
        actions.addWidget(run)
        actions.addStretch(1)
        self.health_summary = ui_label("Controllo non ancora eseguito.", "caption")
        actions.addWidget(self.health_summary)
        health_card.body.addLayout(actions)
        self.health_list = QListWidget()
        self.health_list.setMinimumHeight(180)
        health_card.body.addWidget(self.health_list)
        layout.addWidget(health_card, 1)

        snapshots = Card("Cronologia e ripristino", "Snapshot locali automatici e manuali. Il ripristino sostituisce lo stato corrente dopo una conferma.")
        self.snapshot_status = ui_label("Nessuno snapshot disponibile.", "muted", wrap=True)
        snapshots.body.addWidget(self.snapshot_status)
        snapshot_actions = QHBoxLayout()
        create = QPushButton("CREA SNAPSHOT")
        create.clicked.connect(lambda: self.create_snapshot("Manuale"))
        restore = QPushButton("VISUALIZZA E RIPRISTINA")
        restore.setObjectName("PrimaryButton")
        restore.clicked.connect(self.restore_snapshot)
        snapshot_actions.addWidget(create)
        snapshot_actions.addWidget(restore)
        snapshot_actions.addStretch(1)
        snapshots.body.addLayout(snapshot_actions)
        layout.addWidget(snapshots)
        self.refresh_snapshot_status()
        return page

    def build_audit(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 30)
        layout.setSpacing(14)
        layout.addWidget(ui_label("Registro arbitrale", "h1"))
        layout.addWidget(ui_label(
            "Cronologia delle modifiche e delle decisioni. Ogni voce conserva autore, oggetto e valore precedente/successivo.",
            "lead", wrap=True
        ))
        filters = Card("Cerca nel registro", padding=14, spacing=10)
        row = QHBoxLayout()
        self.audit_search = QLineEdit()
        self.audit_search.setPlaceholderText("Cerca giocatore, partita, motivazione o operazione…")
        self.audit_action_filter = QComboBox()
        self.audit_action_filter.addItem("Tutte le operazioni", None)
        for value, text in [
            ("Risultato", "Risultati"), ("Mossa", "Mosse"), ("Penalità", "Penalità"),
            ("ritir", "Ritiri"), ("Stockfish", "Stockfish / Game Review"),
            ("Orologio", "Orologi"), ("Backup", "Backup e impostazioni"),
        ]:
            self.audit_action_filter.addItem(text, value)
        row.addWidget(self.audit_search, 2)
        row.addWidget(self.audit_action_filter, 1)
        filters.body.addLayout(row)
        self.audit_search.textChanged.connect(self.refresh_audit)
        self.audit_action_filter.currentIndexChanged.connect(self.refresh_audit)
        layout.addWidget(filters)

        toolbar = QHBoxLayout()
        self.audit_count_label = ui_label("0 operazioni", "caption")
        toolbar.addWidget(self.audit_count_label)
        toolbar.addStretch(1)
        export = QPushButton("ESPORTA REGISTRO CSV")
        export.setObjectName("PrimaryButton")
        export.setToolTip("Esporta tutte le operazioni, non soltanto quelle filtrate.")
        export.clicked.connect(self.export_audit_csv)
        toolbar.addWidget(export)
        layout.addLayout(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self.audit_events_layout = QVBoxLayout(content)
        self.audit_events_layout.setContentsMargins(0, 0, 8, 0)
        self.audit_events_layout.setSpacing(8)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page

    def build_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 30)
        layout.setSpacing(16)
        layout.addWidget(ui_label("Impostazioni e strumenti", "h1"))
        layout.addWidget(ui_label(
            "Configurazione della direzione di gara, regolamento e gestione dei dati locali.",
            "lead", wrap=True
        ))

        appearance = Card("Personalizzazione", "Tema, leggibilità e densità delle tabelle. Salva profili riutilizzabili tra gli arbitri.")
        appearance_grid = QGridLayout()
        self.ui_theme_combo = QComboBox()
        self.ui_theme_combo.addItem("Scuro", "dark")
        self.ui_theme_combo.addItem("Chiaro", "light")
        self.ui_font_combo = QComboBox()
        for scale, label in [(0.9,"90%"),(1.0,"100%"),(1.1,"110%"),(1.2,"120%")]:
            self.ui_font_combo.addItem(label, scale)
        self.ui_density_combo = QComboBox()
        self.ui_density_combo.addItem("Standard", "comfortable")
        self.ui_density_combo.addItem("Compatta", "compact")
        self.ui_density_combo.addItem("Ampia", "spacious")
        appearance_grid.addWidget(ui_label("TEMA", "field"),0,0)
        appearance_grid.addWidget(self.ui_theme_combo,0,1)
        appearance_grid.addWidget(ui_label("DIMENSIONE TESTO", "field"),0,2)
        appearance_grid.addWidget(self.ui_font_combo,0,3)
        appearance_grid.addWidget(ui_label("DENSITÀ TABELLE", "field"),1,0)
        appearance_grid.addWidget(self.ui_density_combo,1,1)
        appearance.body.addLayout(appearance_grid)
        profile_row=QHBoxLayout()
        self.ui_profile_combo=QComboBox()
        profile_row.addWidget(self.ui_profile_combo,1)
        save_profile=QPushButton("SALVA PROFILO")
        save_profile.clicked.connect(self.save_ui_profile)
        apply_profile=QPushButton("APPLICA PROFILO")
        apply_profile.clicked.connect(self.apply_ui_profile)
        apply_ui=QPushButton("APPLICA PREFERENZE")
        apply_ui.setObjectName("PrimaryButton")
        apply_ui.clicked.connect(self.save_ui_preferences)
        profile_row.addWidget(save_profile)
        profile_row.addWidget(apply_profile)
        profile_row.addWidget(apply_ui)
        appearance.body.addLayout(profile_row)
        layout.addWidget(appearance)

        referee = Card("Direzione di gara", "Il nome dell'arbitro viene associato alle nuove operazioni del registro.")
        self.referee_input = QLineEdit(self.referee)
        self.referee_input.setPlaceholderText("Nome arbitro / direttore di gara")
        referee.body.addWidget(ui_label("ARBITRO RESPONSABILE", "field"))
        referee.body.addWidget(self.referee_input)
        layout.addWidget(referee)

        spectator = Card(
            "Portale spettatori · rete locale e Internet",
            "Il portale pubblica tavoli, scacchiere, orologi e classifica. Per l'accesso da Internet configura un tunnel o reverse proxy HTTPS verso la porta locale indicata; l'EXE non apre porte sul router."
        )
        self.public_base_url_input=QLineEdit(self.public_base_url)
        self.public_base_url_input.setPlaceholderText("https://live.tuodominio.it")
        spectator.body.addWidget(ui_label("INDIRIZZO PUBBLICO HTTPS (OPZIONALE)", "field"))
        spectator.body.addWidget(self.public_base_url_input)
        self.long_match_combo=QComboBox()
        for minutes,label in ((60,"60 minuti"),(90,"90 minuti"),(120,"120 minuti"),(180,"180 minuti"),(240,"4 ore")):
            self.long_match_combo.addItem(label,minutes)
        current_long=self.long_match_combo.findData(self.long_match_minutes)
        if current_long>=0:self.long_match_combo.setCurrentIndex(current_long)
        spectator.body.addWidget(ui_label("AVVISO PARTITA OLTRE DURATA", "field"))
        spectator.body.addWidget(self.long_match_combo)
        remote_actions=QHBoxLayout()
        portal_qr=QPushButton("QR PORTALE · TUTTI I TAVOLI")
        portal_qr.setObjectName("PrimaryButton")
        portal_qr.clicked.connect(self.show_portal_qr_dialog)
        rotate_token=QPushButton("RINNOVA TOKEN DI ACCESSO")
        rotate_token.clicked.connect(self.rotate_spectator_token)
        remote_actions.addWidget(portal_qr)
        remote_actions.addWidget(rotate_token)
        remote_actions.addStretch(1)
        spectator.body.addLayout(remote_actions)
        self.spectator_config_hint=ui_label(
            f"Token privato attivo · server non avviato · {self.public_base_url or 'accesso Internet non configurato'}. "
            "Il link pubblico richiede HTTPS e un tunnel attivo verso il PC arbitro.",
            "muted",wrap=True
        )
        spectator.body.addWidget(self.spectator_config_hint)
        layout.addWidget(spectator)

        regulation = Card("Regolamento applicato", "Le cadenze sono vincolate alle regole della competizione.")
        timing = QHBoxLayout()
        for heading, value in [("QUALIFICAZIONE", "15 + 3"), ("SEMIFINALI E FINALI", "30 + 10")]:
            tile = QFrame()
            tile.setObjectName("CardRaised")
            v = QVBoxLayout(tile)
            v.setContentsMargins(14, 12, 14, 12)
            v.addWidget(ui_label(heading, "field"))
            v.addWidget(ui_label(value, "numsm"))
            timing.addWidget(tile, 1)
        regulation.body.addLayout(timing)
        regulation.body.addWidget(ui_label(
            "Art. 8 · Punti, scontro diretto soltanto tra due giocatori, Sonneborn–Berger e numero di vittorie. "
            "Se permane la parità: Armageddon o mini-girone secondo il numero di giocatori.",
            "muted", wrap=True
        ))
        regulation.body.addWidget(ui_label(
            "Art. 10 · In caso di patta nei playoff si registra il pareggio e si annota il vincitore dell'Armageddon. "
            "Tempi, colori e condizioni devono essere definiti dal direttore di gara.",
            "muted", wrap=True
        ))
        regulation.body.addWidget(ui_label(
            "Art. 11 · Il ritiro applica la soglia delle due partite concluse per conservare o annullare i risultati precedenti.",
            "muted", wrap=True
        ))
        layout.addWidget(regulation)

        guidance = Card("Accessibilità e scorciatoie", "Le azioni principali sono raggiungibili da tastiera; i controlli mantengono il focus visibile.")
        shortcuts_grid = QGridLayout()
        shortcuts_grid.setHorizontalSpacing(18)
        shortcuts_grid.setVerticalSpacing(8)
        shortcut_items = [
            ("CTRL + S", "Salva lo stato del torneo"),
            ("CTRL + E", "Esporta tutte le partite in PGN"),
            ("CTRL + SHIFT + B", "Crea un backup"),
            ("CTRL + 1 / 2 / 3", "Apri Live, Estrazione o Calendario"),
            ("ALT + ← / →", "Scorri la cronologia della prima scacchiera"),
            ("F2 / F3", "Ruota la scacchiera del tavolo 1 / 2"),
        ]
        for index, (key, description) in enumerate(shortcut_items):
            shortcuts_grid.addWidget(ui_label(key, "mono"), index // 2, (index % 2) * 2)
            shortcuts_grid.addWidget(ui_label(description, "muted", wrap=True), index // 2, (index % 2) * 2 + 1)
        guidance.body.addLayout(shortcuts_grid)
        layout.addWidget(guidance)

        roster = Card("Gestione giocatori", "Registra un ritiro secondo l'Art. 11. L'operazione modifica risultati e classifica.")
        self.withdraw_combo = QComboBox()
        for pid in ORDER:
            self.withdraw_combo.addItem(name(pid), pid)
        roster.body.addWidget(ui_label("GIOCATORE", "field"))
        roster.body.addWidget(self.withdraw_combo)
        withdraw = QPushButton("REGISTRA RITIRO · ART. 11")
        withdraw.setProperty("kind", "danger")
        withdraw.setToolTip("L'app chiederà conferma prima di applicare le conseguenze previste dal regolamento.")
        withdraw.clicked.connect(lambda: self.withdraw_player(self.withdraw_combo.currentData()))
        roster.body.addWidget(withdraw, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(roster)

        data_card = Card("Dati, backup ed esportazioni", "I dati del torneo sono salvati localmente su questo PC.")
        self.settings_storage_label = ui_label(
            f"Salvataggio automatico locale attivo · archivio: {storage_path().name} · nessuna sincronizzazione cloud.",
            "muted", wrap=True
        )
        data_card.body.addWidget(self.settings_storage_label)
        actions = QGridLayout()
        actions.setHorizontalSpacing(10)
        actions.setVerticalSpacing(10)
        operations = [
            ("BACKUP DATI", self.export_backup), ("RIPRISTINA BACKUP", self.restore_backup),
            ("ESPORTA PGN TORNEO", self.export_all_pgn), ("CLASSIFICA CSV", self.export_standings_csv),
            ("CLASSIFICA PDF", self.export_standings_pdf), ("REPORT UFFICIALE PDF", self.export_tournament_report_pdf),
            ("PACCHETTO FINALE · PDF + PGN + DATI", self.export_final_report_package),
            ("REGISTRO CSV", self.export_audit_csv),
        ]
        for index, (text, callback) in enumerate(operations):
            btn = QPushButton(text)
            btn.setToolTip("L'operazione richiede la scelta del file o della destinazione.")
            btn.clicked.connect(callback)
            actions.addWidget(btn, index // 3, index % 3)
        data_card.body.addLayout(actions)
        layout.addWidget(data_card)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save = QPushButton("SALVA IMPOSTAZIONI")
        save.setObjectName("PrimaryButton")
        save.setToolTip("Salva il nome del direttore di gara e aggiorna il registro.")
        save.clicked.connect(self.save_settings)
        save_row.addWidget(save)
        layout.addLayout(save_row)
        return page

    def _read_ui_preferences(self):
        if not hasattr(self,"ui_theme_combo"):
            return
        self.ui_preferences={
            "theme":self.ui_theme_combo.currentData() or "dark",
            "font_scale":float(self.ui_font_combo.currentData() or 1.0),
            "density":self.ui_density_combo.currentData() or "comfortable",
        }

    def apply_ui_preferences(self):
        prefs=getattr(self,"ui_preferences",{}) or {}
        theme=prefs.get("theme","dark")
        scale=max(0.85,min(1.25,float(prefs.get("font_scale",1.0))))
        density=prefs.get("density","comfortable")
        app=QApplication.instance()
        if app is not None:
            qss=T.build_qss()
            if theme=="light":
                substitutions={
                    "#0A0F15":"#F2F5F8","#0D131A":"#FFFFFF","#121A23":"#FFFFFF",
                    "#18222D":"#EDF1F5","#202D3B":"#E2E8EE","#0C1219":"#F7F9FB",
                    "#263444":"#CFD8E1","#1A2530":"#E1E7ED","#EDE7DA":"#17212B",
                    "#AAB2BD":"#526170","#7C8899":"#738190","#C9A15B":"#9A6A18",
                    "#E3C07F":"#80520D","#8F7240":"#A77A2B",
                }
                for old,new in substitutions.items():
                    qss=qss.replace(old,new)
            if abs(scale-1.0)>0.001:
                qss=re.sub(r"font-size: *([0-9]+)px",
                    lambda match:f"font-size:{max(9,round(int(match.group(1))*scale))}px",qss)
            app.setStyleSheet(qss)
            app.setFont(T.font(T.SANS,round(14*scale)))
        density_px={"compact":36,"comfortable":48,"spacious":60}.get(density,48)
        for table in self.findChildren(QTableWidget):
            table.verticalHeader().setDefaultSectionSize(density_px)
            for row in range(table.rowCount()):
                table.setRowHeight(row,density_px)
        theme_widget=getattr(self,"ui_theme_combo",None)
        if theme_widget is not None:
            idx=theme_widget.findData(theme)
            if idx>=0: theme_widget.setCurrentIndex(idx)
        font_widget=getattr(self,"ui_font_combo",None)
        if font_widget is not None:
            idx=font_widget.findData(scale)
            if idx>=0: font_widget.setCurrentIndex(idx)
        density_widget=getattr(self,"ui_density_combo",None)
        if density_widget is not None:
            idx=density_widget.findData(density)
            if idx>=0: density_widget.setCurrentIndex(idx)
        self.refresh_ui_profiles()

    def refresh_ui_profiles(self):
        combo=getattr(self,"ui_profile_combo",None)
        if combo is None:
            return
        current=combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Seleziona un profilo…","")
        for profile_name in sorted(self.ui_profiles,key=str.casefold):
            combo.addItem(profile_name,profile_name)
        idx=combo.findData(current)
        if idx>=0: combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def save_ui_preferences(self):
        self._read_ui_preferences()
        self.apply_ui_preferences()
        self.save()
        self.statusBar().showMessage("Preferenze di visualizzazione salvate.",2500)

    def save_ui_profile(self):
        self._read_ui_preferences()
        profile_name,ok=QInputDialog.getText(self,"Salva profilo di visualizzazione",
            "Nome del profilo (es. Arbitro principale):",text=self.referee or "Arbitro")
        profile_name=profile_name.strip()
        if not ok or not profile_name:
            return
        self.ui_profiles[profile_name]=dict(self.ui_preferences)
        self.refresh_ui_profiles()
        idx=self.ui_profile_combo.findData(profile_name)
        if idx>=0: self.ui_profile_combo.setCurrentIndex(idx)
        self.save()
        self.statusBar().showMessage(f"Profilo '{profile_name}' salvato.",2500)

    def apply_ui_profile(self):
        profile_name=self.ui_profile_combo.currentData()
        if not profile_name or profile_name not in self.ui_profiles:
            return
        self.ui_preferences=dict(self.ui_profiles[profile_name])
        self.apply_ui_preferences()
        self.save()
        self.statusBar().showMessage(f"Profilo '{profile_name}' applicato.",2500)

    def save_settings(self):
        public_url=self.public_base_url_input.text().strip().rstrip("/")
        if public_url:
            parsed=urlparse(public_url)
            if parsed.scheme!="https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("","/"):
                QMessageBox.warning(
                    self,"Indirizzo pubblico non valido",
                    "Inserisci un'origine HTTPS senza credenziali, query o percorso, ad esempio https://live.tuodominio.it. "
                    "Il dominio deve essere instradato al server locale tramite tunnel o reverse proxy."
                )
                return
        self.referee=self.referee_input.text().strip()
        self.public_base_url=public_url
        self.long_match_minutes=int(self.long_match_combo.currentData() or 120)
        self._read_ui_preferences()
        self.tie_break="Regolamento Art. 8"
        self.log_operation("Impostazioni torneo","","",f"arbitro={self.referee}; spareggio={self.tie_break}; portale={self.public_base_url or 'solo LAN'}")
        self.save(); self.refresh_all()
        if self.public_base_url:
            try:
                self.start_match_web_server()
            except Exception as exc:
                self.record_operational_alert("Server spettatori non avviato",str(exc),"danger","settings","local-server-start")
                QMessageBox.warning(self,"Portale non avviato",str(exc))
        self.refresh_spectator_config_hint()
        self.refresh_notification_badge()
        self.statusBar().showMessage("Impostazioni torneo salvate.",2500)

    def refresh_spectator_config_hint(self):
        label=getattr(self,"spectator_config_hint",None)
        if label is None:return
        local=f"Server attivo su {self.match_http_host}:{self.match_http_port}" if self.match_http_server is not None else "Server in attesa del primo QR"
        remote=self.public_base_url or "accesso Internet non configurato"
        label.setText(
            f"Token di accesso privato attivo · {local} · {remote}. "
            "Per l'accesso remoto il tunnel HTTPS deve inoltrare la porta locale del server e restare attivo."
        )

    def rotate_spectator_token(self):
        answer=QMessageBox.question(
            self,"Rinnovare il token spettatori?",
            "Tutti i QR e i link già distribuiti smetteranno di funzionare. I nuovi link useranno una chiave casuale diversa.",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if answer!=QMessageBox.StandardButton.Yes:return
        self.spectator_token=secrets.token_urlsafe(32)
        self.log_operation("Token spettatori rinnovato","","","Link precedenti revocati")
        self.save()
        self.statusBar().showMessage("Token rinnovato: ristampa o ridistribuisci i QR.",4500)

    def install_shortcuts(self):
        shortcuts=[("Ctrl+S",self.save),("Ctrl+E",self.export_all_pgn),
                   ("Ctrl+Shift+B",self.export_backup),("Ctrl+K",self.open_command_palette),
                   ("Ctrl+1",lambda:self.tabs.setCurrentIndex(1)),
                   ("Ctrl+2",lambda:self.tabs.setCurrentIndex(2)),("Ctrl+3",lambda:self.tabs.setCurrentIndex(3)),
                   ("Ctrl+Z",self.undo_history),("Ctrl+Y",self.redo_history),
                    ("Ctrl+Alt+Z",lambda:self.undo(self.live_cards[0].game_id)),
                   ("Alt+Left",lambda:self.live_cards[0].previous_move()),
                   ("Alt+Right",lambda:self.live_cards[0].next_move()),
                   ("F2",lambda:self.live_cards[0].board.toggle_orientation()),
                   ("F3",lambda:self.live_cards[1].board.toggle_orientation())]
        self.shortcuts=[]
        for key,callback in shortcuts:
            shortcut=QShortcut(QKeySequence(key),self)
            shortcut.activated.connect(callback); self.shortcuts.append(shortcut)

    def open_dashboard_result(self,row,column):
        item=self.dashboard_results_table.item(row,0)
        gid=item.data(Qt.ItemDataRole.UserRole) if item else None
        if not gid:
            return
        self.nav.set_current("live")
        if self.live_cards:
            selector=self.live_cards[0].selector
            index=selector.findData(gid)
            if index>=0:
                selector.setCurrentIndex(index)

    def refresh_dashboard_results(self):
        if not hasattr(self,"dashboard_results_table"):
            return
        schedule_order={gid:index for index,(gid,_,_,_) in enumerate(GAMES)}
        last_result_event={}
        for index,entry in enumerate(self.audit_log):
            if entry.get("action")=="Risultato":
                gid=str(entry.get("entity",""))
                last_result_event[gid]=index
        completed=[g for g in GAMES if self.results.get(g[0]) is not None]
        completed.sort(
            key=lambda g:(last_result_event.get(g[0],-1),schedule_order.get(g[0],-1)),
            reverse=True
        )
        latest=completed[:6]
        self.dashboard_results_table.setRowCount(len(latest))
        labels={"1-0":"1  –  0","1/2-1/2":"½  –  ½","0-1":"0  –  1","VOID":"ANNULLATA"}
        for row,(gid,round_no,white,black) in enumerate(latest):
            result=self.results.get(gid)
            values=(f"ROUND {round_no:02d}",gid,name(white),name(black),labels.get(result,str(result or "")))
            for column,value in enumerate(values):
                item=QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole,gid)
                if column in (0,1,4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.dashboard_results_table.setItem(row,column,item)
        has_results=bool(latest)
        self.dashboard_results_table.setVisible(has_results)
        self.dashboard_results_empty.setVisible(not has_results)

    def refresh_dashboard(self):
        if not hasattr(self, "dashboard_tiles"):
            return
        self.refresh_dashboard_results()
        done = sum(1 for gid, _, _, _ in GAMES if self.results.get(gid) not in (None, "VOID"))
        voided = sum(1 for gid, _, _, _ in GAMES if self.results.get(gid) == "VOID")
        active_games = [
            gid for gid, _, _, _ in GAMES
            if self.results.get(gid) is None
            and (self.clock_data(gid).get("started") or bool(self.moves.get(gid)))
        ]
        running = len(active_games)
        pending = max(0, len(GAMES) - done - voided - running)
        retired = sum(1 for player in ORDER if player in self.withdrawn_players)
        self.dashboard_tiles["done"].set(str(done), f"{done}/10 risultati validi")
        self.dashboard_tiles["live"].set(str(running), "Con cronometro o mosse registrate")
        self.dashboard_tiles["pending"].set(str(pending), "Ancora da iniziare")
        self.dashboard_tiles["retired"].set(str(retired), "Ritiri registrati")
        closed = done + voided
        target_progress = round(closed * 100 / max(1, len(GAMES)))
        if not hasattr(self, "_dashboard_progress_animation"):
            self._dashboard_progress_animation = QPropertyAnimation(self.dashboard_progress, b"value", self)
            self._dashboard_progress_animation.setDuration(340)
            self._dashboard_progress_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._dashboard_progress_animation.stop()
        if self.dashboard_progress.value() < 0:
            self.dashboard_progress.setValue(0)
        self._dashboard_progress_animation.setStartValue(self.dashboard_progress.value())
        self._dashboard_progress_animation.setEndValue(target_progress)
        if self.dashboard_progress.value() == target_progress:
            self.dashboard_progress.setValue(target_progress)
        else:
            self._dashboard_progress_animation.start()
        self.dashboard_progress_detail.setText(
            f"{done} concluse · {voided} annullate · {pending} da iniziare · {running} in corso"
        )
        leader = self.standings()[0]
        self.dashboard_detail.setText(
            f"LEADER ATTUALE  ·  {name(leader['id'])}  ·  {leader['points']:.1f} punti netti"
            f"     |     ARBITRO  ·  {self.referee or 'non impostato'}"
        )
        upcoming_ids = active_games + [
            gid for gid, _, _, _ in GAMES
            if self.results.get(gid) is None and gid not in active_games
        ]
        for index, label in enumerate(self.dashboard_next_labels):
            match_line = self.dashboard_next_matches[index]
            if index < len(upcoming_ids):
                gid = upcoming_ids[index]
                _, rnd, white, black = game(gid)
                state = "IN CORSO" if gid in active_games else "DA DISPUTARE"
                match_line.set_players(name(white), name(black))
                label.setText(f"ROUND {rnd} · {gid} · {state}")
            elif index == 0 and not upcoming_ids:
                match_line.set_players("", "")
                label.setText("Girone completato: non ci sono altre partite da disputare.")
            else:
                match_line.set_players("", "")
                label.setText("—")
        ranking_rows = self.standings()[:3]
        for index, label in enumerate(self.dashboard_ranking_labels):
            form_widget = self.dashboard_ranking_forms[index]
            if index < len(ranking_rows):
                row = ranking_rows[index]
                player_id = row["id"]
                label.setText(
                    f"{index + 1}.  {name(player_id)}     {row['points']:.1f} pt"
                    f"     ·     {row['played']}/5 giocate"
                )
                recent = []
                for match in sorted(GAMES, key=lambda item: (item[1], item[0])):
                    gid, _, white, black = match
                    if player_id not in (white, black):
                        continue
                    result = self.results.get(gid)
                    if result not in ("1-0", "0-1", "1/2-1/2"):
                        continue
                    if result == "1/2-1/2":
                        recent.append("X")
                    elif (result == "1-0" and player_id == white) or (result == "0-1" and player_id == black):
                        recent.append("V")
                    else:
                        recent.append("P")
                form_widget.set_items(recent)
            else:
                label.setText("—")
                form_widget.set_items([])
        cumulative = {player: [] for player in ORDER}
        running_points = {player: 0.0 for player in ORDER}
        for rnd in range(1, 6):
            for gid, game_round, white, black in GAMES:
                if game_round != rnd:
                    continue
                result = self.results.get(gid)
                if result == "1-0":
                    running_points[white] += 1.0
                elif result == "0-1":
                    running_points[black] += 1.0
                elif result == "1/2-1/2":
                    running_points[white] += 0.5
                    running_points[black] += 0.5
            for player in ORDER:
                cumulative[player].append(running_points[player])
        self.dashboard_chart.set_data(
            [f"R{rnd}" for rnd in range(1, 6)],
            [(name(player), T.player_tint(ORDER.index(player)), cumulative[player]) for player in ORDER]
        )

    def archive_entries(self):
        entries=[("qualification",g[0],g[1],g[2],g[3]) for g in GAMES if self.results.get(g[0])]
        if hasattr(self,"playoff_pairs"):
            labels={"sf1":"Semifinale 1","sf2":"Semifinale 2","third":"Finale 3°–4°","final":"Finale"}
            for key in ("sf1","sf2","third","final"):
                pair=self.playoff_pairs.get(key,(None,None))
                if self.playoff_results.get(key) and all(pair):
                    entries.append(("playoff",key,labels[key],pair[0],pair[1]))
        return entries

    def refresh_archive(self):
        if not hasattr(self,"archive_table"): return
        entries=self.archive_entries()
        self.archive_table.setRowCount(len(entries))
        for row,(kind,gid,round_label,white,black) in enumerate(entries):
            if kind=="qualification":
                precision,_=self.game_precision_summary(gid)
                term=self.game_terminations.get(gid,{})
                detail=term.get("detail","") if isinstance(term,dict) else str(term or "")
                status="RITIRO / ANNULLATA" if self.results[gid]=="VOID" else (detail or f"{len(self.moves.get(gid,[]))} mosse · {len(self.match_notes.get(gid,[]))} note")
                result=self.results[gid]
                precision_status=f"{precision} · {status}" if self.move_reviews.get(gid) else status
                values=[f"ROUND {round_label}",gid,name(white),name(black),result,precision_status]
            else:
                term=self.game_terminations.get(gid,{})
                detail=term.get("detail","") if isinstance(term,dict) else str(term or "")
                result=self.playoff_results[gid]
                winner=self.playoff_winners.get(gid)
                extra=f" · Armageddon: {name(winner)}" if winner else ""
                values=[round_label,gid,name(white),name(black),result,(detail or "Risultato playoff")+extra]
            for col,value in enumerate(values):
                item=QTableWidgetItem(str(value)); item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setData(Qt.ItemDataRole.UserRole,(kind,gid))
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
                    if not result or result=="VOID": continue
                    score=1 if (result=="1-0" and p==w) or (result=="0-1" and p==b) else (.5 if result=="1/2-1/2" else 0)
                    if score==1: wins+=1
                    elif score==.5: draws+=1
                    else: losses+=1
                self.h2h_table.setItem(row,col,QTableWidgetItem(f"{wins}–{draws}–{losses}"))

    def refresh_audit(self):
        if not hasattr(self, "audit_events_layout"):
            return
        # Recreating every audit card for each chess move caused avoidable UI stalls,
        # even while the operator was on the Live Arena. Render lazily on page entry.
        if hasattr(self, "tabs") and hasattr(self, "_page_keys") and "audit" in self._page_keys:
            if self.tabs.currentIndex() != self._page_keys.index("audit"):
                self._audit_dirty = True
                return
        self._audit_dirty = False
        while self.audit_events_layout.count():
            item = self.audit_events_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        query = self.audit_search.text().strip().casefold() if hasattr(self, "audit_search") else ""
        action_filter = self.audit_action_filter.currentData() if hasattr(self, "audit_action_filter") else None
        entries = list(reversed(self.audit_log))
        visible = []
        for entry in entries:
            action = str(entry.get("action", "Operazione"))
            searchable = " ".join(
                str(entry.get(key, "")) for key in
                ("time", "referee", "action", "entity", "before", "after", "detail")
            ).casefold()
            if query and query not in searchable:
                continue
            if action_filter and str(action_filter).casefold() not in action.casefold() \
                    and str(action_filter).casefold() not in str(entry.get("detail", "")).casefold():
                continue
            visible.append(entry)
        self.audit_count_label.setText(
            f"{len(visible)} operazioni visualizzate · {len(self.audit_log)} totali"
        )
        if not visible:
            self.audit_events_layout.addWidget(
                EmptyState("info", "Nessuna operazione trovata", "Modifica i filtri oppure registra una nuova operazione.")
            )
            self.audit_events_layout.addStretch(1)
            return
        for entry in visible:
            action = str(entry.get("action", "Operazione"))
            tone = "danger" if "penalità" in action.casefold() or "ritiro" in action.casefold() else (
                "success" if "risultato" in action.casefold() else "neutral"
            )
            card = Card(padding=14, spacing=7)
            meta = QHBoxLayout()
            meta.addWidget(ui_label(str(entry.get("time", "Ora non disponibile")), "mono"))
            meta.addWidget(ui_pill(action.upper(), tone))
            meta.addStretch(1)
            meta.addWidget(ui_label(str(entry.get("referee") or "Arbitro non indicato"), "caption"))
            card.body.addLayout(meta)
            entity = str(entry.get("entity", "")).strip()
            if entity:
                card.body.addWidget(ui_label(entity, "h3"))
            before = str(entry.get("before", "")).strip() or "—"
            after = str(entry.get("after", "")).strip() or "—"
            card.body.addWidget(ui_label(f"{before}   →   {after}", "body", wrap=True))
            detail = str(entry.get("detail", "")).strip()
            if detail:
                card.body.addWidget(ui_label(detail, "muted", wrap=True))
            self.audit_events_layout.addWidget(card)
        self.audit_events_layout.addStretch(1)

    def accuracy_for_player(self,gid,player_id):
        reviews=self.move_reviews.get(gid,[])
        losses=[float(item.get("expected_points_loss",0)) for item in reviews if item.get("player")==player_id]
        if not losses:
            return None
        return max(0.0,min(100.0,100.0*(1.0-sum(losses)/len(losses))))

    def game_precision_summary(self,gid):
        _,_,white,black=game(gid)
        white_accuracy=self.accuracy_for_player(gid,white)
        black_accuracy=self.accuracy_for_player(gid,black)
        reviews=self.move_reviews.get(gid,[])
        counts={}
        for item in reviews:
            label=item.get("label","")
            counts[label]=counts.get(label,0)+1
        def fmt(value):
            return "non disponibile" if value is None else f"{value:.1f}%"
        return f"{name(white)}: {fmt(white_accuracy)} · {name(black)}: {fmt(black_accuracy)}",counts

    def build_pgn_game(self,gid):
        board=self.get_board(gid)
        _,round_no,white,black=game(gid)
        node=chess.pgn.Game.from_board(board)
        result=self.results.get(gid,"*")
        if result=="VOID": result="*"
        node.headers["Event"]=APP_NAME
        node.headers["Site"]="Coppa dei 5 Re"
        node.headers["Round"]=str(round_no)
        node.headers["White"]=name(white)
        node.headers["Black"]=name(black)
        node.headers["Result"]=result or "*"
        node.headers["TimeControl"]="900+3"
        termination=self.game_terminations.get(gid,{})
        if isinstance(termination,dict):
            node.headers["Termination"]=termination.get("termination","normal")
            if termination.get("detail"):
                node.headers["C5R_TerminationDetails"]=str(termination["detail"])
        elif termination:
            node.headers["Termination"]=str(termination)
        summary,_=self.game_precision_summary(gid)
        if self.move_reviews.get(gid):
            node.headers["C5R_Accuracy"]=summary
            node.headers["C5R_Review"]="Local Stockfish expected-points estimate; not Chess.com CAPS2"
        reviews={int(item.get("ply",0)):item for item in self.move_reviews.get(gid,[])}
        nag_map={
            "BRILLANTE":getattr(chess.pgn,"NAG_BRILLIANT_MOVE",3),
            "OTTIMA":getattr(chess.pgn,"NAG_GOOD_MOVE",1),
            "IMPRECISIONE":getattr(chess.pgn,"NAG_INACCURACY",6),
            "ERRORE":getattr(chess.pgn,"NAG_MISTAKE",2),
            "GRAVE ERRORE":getattr(chess.pgn,"NAG_BLUNDER",4),
        }
        for ply,move_node in enumerate(node.mainline(),1):
            review=reviews.get(ply)
            if review:
                label=review.get("label","")
                loss=float(review.get("expected_points_loss",0))*100
                note=f"C5R Game Review: {label}; expected-points loss {loss:.1f}%; eval before {int(review.get('before_cp',0))/100:+.2f}, after {int(review.get('after_cp',0))/100:+.2f}"
                move_node.comment=(move_node.comment+" | "+note).strip(" |")
                nag=nag_map.get(label)
                if nag is not None:
                    move_node.nags.add(nag)

            annotation = self.move_annotations.get(gid, {}).get(str(ply), {})
            if isinstance(annotation, dict):
                comment = str(annotation.get("note", "")).strip()
                if comment:
                    move_node.comment = (move_node.comment + " | Nota C5R: " + comment).strip(" |")
                variation = str(annotation.get("variation", "")).strip()
                if variation:
                    variation_board = move_node.board()
                    variation_parent = move_node
                    try:
                        for token in variation.split():
                            variation_move = variation_board.parse_san(token)
                            variation_parent = variation_parent.add_variation(variation_move)
                            variation_board.push(variation_move)
                    except ValueError as exc:
                        raise ValueError(f"Variante non valida per {gid}, mossa {ply}: {exc}") from exc
        return node

    def build_playoff_pgn(self,key):
        pair=getattr(self,"playoff_pairs",{}).get(key,(None,None))
        white,black=pair if pair else (None,None)
        node=chess.pgn.Game()
        node.headers["Event"]=APP_NAME
        node.headers["Site"]="Coppa dei 5 Re"
        node.headers["Round"]={"sf1":"Semifinale 1","sf2":"Semifinale 2","final":"Finale","third":"Finale 3°–4° posto"}.get(key,key)
        node.headers["White"]=name(white) if white else "Da definire"
        node.headers["Black"]=name(black) if black else "Da definire"
        node.headers["Result"]=self.playoff_results.get(key,"*")
        node.headers["TimeControl"]="1800+10"
        term=self.game_terminations.get(key,{})
        if isinstance(term,dict):
            node.headers["Termination"]=term.get("termination","normal")
            if term.get("detail"): node.headers["C5R_TerminationDetails"]=str(term["detail"])
        winner=self.playoff_winners.get(key)
        if winner:
            node.headers["C5R_ArmageddonWinner"]=name(winner)
            node.headers["C5R_Armageddon"]="Winner recorded after Armageddon"
        return node

    def export_all_pgn(self):
        path,_=QFileDialog.getSaveFileName(self,"Esporta tutte le partite","Coppa5Re-Torneo.pgn","PGN (*.pgn)")
        if not path:
            return
        chunks=[]
        for gid,_,_,_ in GAMES:
            node=self.build_pgn_game(gid)
            chunks.append(node.accept(chess.pgn.StringExporter(headers=True,variations=True,comments=True)))
        for key in ("sf1","sf2","third","final"):
            pair=getattr(self,"playoff_pairs",{}).get(key,(None,None))
            if self.playoff_results.get(key) or all(pair):
                node=self.build_playoff_pgn(key)
                chunks.append(node.accept(chess.pgn.StringExporter(headers=True,variations=False,comments=True)))
        Path(path).write_text("\n\n".join(chunks)+"\n",encoding="utf-8")
        self.statusBar().showMessage("Archivio PGN esportato con risultati, terminazioni e annotazioni C5R disponibili.",3500)

    def analyze_selected_archive_game(self):
        row = self.archive_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Analisi partita", "Seleziona una partita conclusa nell'archivio.")
            return
        entries=self.archive_entries()
        if row>=len(entries):
            return
        kind,gid,_,_,_=entries[row]
        if kind=="playoff":
            QMessageBox.information(self,"Analisi playoff","Il tabellone salva risultati, terminazioni e vincitore Armageddon. Le mosse delle partite playoff non sono ancora registrate su una scacchiera nell'app.")
            return
        saved = self.eval_history.get(gid)
        if saved:
            self.show_game_analysis(gid, saved)
            return
        moves = self.moves.get(gid, [])
        if not moves:
            QMessageBox.information(self, "Analisi partita", "Questa partita non contiene mosse registrate.")
            return
        if self.analysis_running_gid is not None:
            QMessageBox.information(self, "Analisi in corso", "Attendi la fine dell'analisi già avviata.")
            return
        service = self.get_engine_service()
        if service is None:
            QMessageBox.warning(self, "Stockfish non disponibile", "Stockfish integrato non trovato nella build.")
            return
        self.analysis_running_gid = gid
        self.statusBar().showMessage(f"Stockfish sta analizzando {gid}: {len(moves)} posizioni…")
        service.request_game(gid, moves)

    def on_game_analysis_ready(self, gid, positions):
        if gid:
            self.analysis_running_gid = None
            self.eval_history[gid] = positions
            if positions:
                self.move_reviews[gid] = positions
            self.save()
            self.refresh_archive()
            self.statusBar().showMessage(f"Analisi Stockfish completata: {gid}.", 3500)
            self.show_game_analysis(gid, positions)

    def on_game_analysis_failed(self, gid, error):
        self.analysis_running_gid = None
        if gid:
            QMessageBox.warning(self, "Analisi non riuscita", f"Stockfish non è riuscito ad analizzare {gid}: {error}")
        else:
            self.statusBar().showMessage(f"Stockfish non si è avviato: {error}", 6000)

    def show_game_analysis(self, gid, positions):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Game Review C5R · {gid}")
        dialog.resize(1120, 800)
        root = QVBoxLayout(dialog)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        white_player = game(gid)[2]
        black_player = game(gid)[3]
        white_accuracy = self.accuracy_for_player(gid, white_player)
        black_accuracy = self.accuracy_for_player(gid, black_player)
        def accuracy_text(value):
            return "—" if value is None else f"{value:.1f}%"
        bad = sum(1 for item in positions if item.get("label") in ("ERRORE", "GRAVE ERRORE"))
        inaccuracies = sum(1 for item in positions if item.get("label") == "IMPRECISIONE")
        root.addWidget(ui_label(f"Analisi della partita · {gid}", "h1"))
        summary_card = Card("Precisione C5R", "Stima locale basata sulla perdita dei punti attesi. Non replica l'algoritmo proprietario CAPS2 di Chess.com.")
        metrics = QHBoxLayout()
        for caption, value, hint in [
            (name(white_player), accuracy_text(white_accuracy), "Precisione Bianco"),
            (name(black_player), accuracy_text(black_accuracy), "Precisione Nero"),
            ("MOSSE ANALIZZATE", str(len(positions)), "Posizioni valutate"),
            ("ERRORI", str(bad), f"{inaccuracies} imprecisioni"),
        ]:
            tile = StatTile(caption)
            tile.set(value, hint)
            metrics.addWidget(tile, 1)
        summary_card.body.addLayout(metrics)
        root.addWidget(summary_card)

        if not positions:
            root.addWidget(EmptyState("chart", "Nessuna posizione analizzata", "Questa partita non contiene dati di analisi."))
        else:
            content = QHBoxLayout()
            content.setSpacing(14)
            moves_card = Card("Timeline delle mosse", "Seleziona una riga per rivedere la posizione sulla scacchiera.")
            table = QTableWidget(len(positions), 6)
            table.setHorizontalHeaderLabels(["PLY", "GIOCATORE", "MOSSA", "QUALITÀ", "VALUTAZIONE", "PERDITA EP"])
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            style_table(table, row_height=40, selectable=True)
            tones = {
                "BRILLANTE": "brass", "MIGLIORE": "success", "OTTIMA": "success",
                "BUONA": "info", "IMPRECISIONE": "warning", "ERRORE": "danger",
                "GRAVE ERRORE": "danger",
            }
            for row_index, item in enumerate(positions):
                score = int(item.get("score", 0))
                if abs(score) >= 10000:
                    evaluation = "Matto"
                else:
                    evaluation = f"{score / 100:+.2f}"
                values = (
                    str(item.get("ply", row_index + 1)),
                    name(item.get("player", "")),
                    item.get("san", item.get("uci", "")),
                    item.get("label", "—"),
                    evaluation,
                    f"{float(item.get('expected_points_loss', 0)) * 100:.1f}%",
                )
                for col, value in enumerate(values):
                    cell = QTableWidgetItem(str(value))
                    if col == 3:
                        cell.setData(Qt.ItemDataRole.UserRole + 1, tones.get(str(value), "neutral"))
                    if col in (0, 4, 5):
                        cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(row_index, col, cell)
            table.setItemDelegateForColumn(3, PillDelegate(table))
            moves_card.body.addWidget(table)
            content.addWidget(moves_card, 3)

            board_card = Card("Posizione selezionata", "La scacchiera è in sola lettura.")
            preview_row = QHBoxLayout()
            eval_bar = EvalBar()
            eval_bar.setMinimumHeight(250)
            preview = BoardWidget(False)
            preview.setMinimumSize(260, 260)
            preview_row.addWidget(eval_bar)
            preview_row.addWidget(preview, 1)
            board_card.body.addLayout(preview_row)
            move_detail = ui_label("Seleziona una mossa nella timeline.", "muted", wrap=True)
            board_card.body.addWidget(move_detail)

            annotation_card = Card(
                "Annotazioni della mossa",
                "Salva commenti e una variante alternativa in notazione SAN, partendo dalla posizione dopo la mossa selezionata.",
                padding=12, spacing=7
            )
            annotation_note = ui_label("Nessuna nota associata.", "muted", wrap=True)
            annotation_variation = ui_label("Variante: —", "muted", wrap=True)
            annotation_card.body.addWidget(annotation_note)
            annotation_card.body.addWidget(annotation_variation)
            edit_annotation = QPushButton("MODIFICA NOTA / VARIANTE")
            edit_annotation.clicked.connect(lambda: edit_current_annotation())
            annotation_card.body.addWidget(edit_annotation)
            board_card.body.addWidget(annotation_card)

            def refresh_annotation_display(item):
                ply = str(int(item.get("ply", 1)))
                saved = self.move_annotations.get(gid, {}).get(ply, {})
                note = str(saved.get("note", "")).strip() if isinstance(saved, dict) else ""
                variation = str(saved.get("variation", "")).strip() if isinstance(saved, dict) else ""
                annotation_note.setText("Nota: " + (note or "nessuna"))
                annotation_variation.setText("Variante: " + (variation or "—"))

            def edit_current_annotation():
                current = table.currentRow()
                if not (0 <= current < len(positions)):
                    return
                item = positions[current]
                ply = str(int(item.get("ply", current + 1)))
                saved = self.move_annotations.get(gid, {}).get(ply, {})
                old_note = str(saved.get("note", "")) if isinstance(saved, dict) else ""
                old_variation = str(saved.get("variation", "")) if isinstance(saved, dict) else ""
                note_text, ok = QInputDialog.getMultiLineText(
                    dialog, "Annotazione mossa", f"{gid} · mossa {ply} · commento:", old_note
                )
                if not ok:
                    return
                variation_text, ok = QInputDialog.getText(
                    dialog, "Variante alternativa",
                    "Inserisci una sequenza di mosse SAN (es. Nf6 d4 d6):", old_variation
                )
                if not ok:
                    return
                variation_text = variation_text.strip()
                fen = item.get("fen")
                if variation_text and fen:
                    try:
                        validation_board = chess.Board(fen)
                        for token in variation_text.split():
                            validation_move = validation_board.parse_san(token)
                            validation_board.push(validation_move)
                    except Exception as exc:
                        QMessageBox.warning(dialog, "Variante non valida", f"La variante non è legale da questa posizione: {exc}")
                        return
                note_text = note_text.strip()
                entry = {"note": note_text, "variation": variation_text}
                if not note_text and not variation_text:
                    if gid in self.move_annotations:
                        self.move_annotations[gid].pop(ply, None)
                        if not self.move_annotations[gid]:
                            self.move_annotations.pop(gid, None)
                else:
                    self.move_annotations.setdefault(gid, {})[ply] = entry
                self.log_operation(
                    "Annotazione mossa", f"{gid} · ply {ply}",
                    "Annotazione presente" if old_note or old_variation else "Vuota",
                    "Annotazione aggiornata" if note_text or variation_text else "Annotazione rimossa"
                )
                self.save()
                refresh_annotation_display(item)
                self.statusBar().showMessage(f"Annotazione della mossa {ply} salvata.", 3000)

            content.addWidget(board_card, 2)
            root.addLayout(content, 1)

            def select_position(row_index, _column=0):
                if not (0 <= row_index < len(positions)):
                    return
                item = positions[row_index]
                fen = item.get("fen")
                if fen:
                    position = chess.Board(fen)
                    preview.set_position(position, locked=True)
                score = int(item.get("score", 0))
                mover = item.get("player")
                white_score = score if mover == white_player else -score
                fraction = 1.0 / (1.0 + math.exp(-max(-4000, min(4000, white_score)) / 400.0))
                eval_text = "BIANCO" if white_score > 0 else ("NERO" if white_score < 0 else "PARI")
                eval_bar.set_eval(fraction, f"{eval_text} · {abs(white_score) / 100:.2f}")
                move_detail.setText(
                    f"{name(mover)} · {item.get('san', item.get('uci', ''))} · "
                    f"{item.get('label', '—')} · perdita punti attesi "
                    f"{float(item.get('expected_points_loss', 0)) * 100:.1f}%"
                )
                refresh_annotation_display(item)
            table.cellClicked.connect(select_position)
            table.selectRow(0)
            select_position(0)

            review_toolbar = QHBoxLayout()
            review_toolbar.addWidget(ui_label("MOSTRA", "field"))
            quality_filter = QComboBox()
            quality_filter.addItem("Tutte le mosse", "all")
            quality_filter.addItem("Imprecisioni + errori", "mistakes")
            quality_filter.addItem("Solo errori gravi", "blunders")
            quality_filter.setAccessibleName("Filtro qualità delle mosse")
            review_toolbar.addWidget(quality_filter)
            review_count = ui_label(f"{len(positions)} posizioni analizzate", "caption")
            review_toolbar.addWidget(review_count, 1)
            previous_move = QPushButton("←  PRECEDENTE")
            next_move = QPushButton("SUCCESSIVA  →")
            previous_move.setToolTip("Seleziona la mossa precedente tra quelle visibili.")
            next_move.setToolTip("Seleziona la mossa successiva tra quelle visibili.")
            review_toolbar.addWidget(previous_move)
            review_toolbar.addWidget(next_move)
            root.addLayout(review_toolbar)

            def visible_review_rows():
                mode = quality_filter.currentData()
                visible_rows = []
                for index, move_item in enumerate(positions):
                    label = str(move_item.get("label", "")).upper()
                    if mode == "mistakes" and label not in ("IMPRECISIONE", "ERRORE", "GRAVE ERRORE"):
                        continue
                    if mode == "blunders" and label != "GRAVE ERRORE":
                        continue
                    visible_rows.append(index)
                return visible_rows

            def apply_review_filter():
                rows_visible = visible_review_rows()
                for row_index in range(len(positions)):
                    table.setRowHidden(row_index, row_index not in rows_visible)
                review_count.setText(f"{len(rows_visible)} mosse visibili · {len(positions)} analizzate")
                previous_move.setEnabled(bool(rows_visible))
                next_move.setEnabled(bool(rows_visible))
                current = table.currentRow()
                if rows_visible and current not in rows_visible:
                    table.selectRow(rows_visible[0])
                    select_position(rows_visible[0])

            def move_review_selection(step):
                rows_visible = visible_review_rows()
                if not rows_visible:
                    return
                current = table.currentRow()
                if current not in rows_visible:
                    target = rows_visible[0]
                else:
                    target = rows_visible[(rows_visible.index(current) + step) % len(rows_visible)]
                table.selectRow(target)
                select_position(target)
                table.scrollToItem(table.item(target, 0))

            quality_filter.currentIndexChanged.connect(apply_review_filter)
            previous_move.clicked.connect(lambda: move_review_selection(-1))
            next_move.clicked.connect(lambda: move_review_selection(1))
            apply_review_filter()

        footer = QHBoxLayout()
        footer.addWidget(ui_label(
            "Le valutazioni sono derivate da Stockfish e hanno finalità di analisi locale.",
            "caption", wrap=True
        ), 1)
        close = QPushButton("CHIUDI")
        close.setObjectName("PrimaryButton")
        close.clicked.connect(dialog.accept)
        footer.addWidget(close)
        root.addLayout(footer)
        dialog.exec()

    def export_selected_archive_game(self):
        row=self.archive_table.currentRow()
        if row<0: return
        entries=self.archive_entries()
        if row>=len(entries): return
        kind,gid,_,_,_=entries[row]
        if kind=="qualification":
            self.export_pgn(gid)
        else:
            node=self.build_playoff_pgn(gid)
            content=node.accept(chess.pgn.StringExporter(headers=True,variations=False,comments=True))
            path,_=QFileDialog.getSaveFileName(self,"Esporta PGN playoff",f"{gid}.pgn","Partite PGN (*.pgn)")
            if path:
                Path(path).write_text(content,encoding="utf-8")
                self.statusBar().showMessage("PGN playoff esportato.",2500)

    def export_standings_csv(self):
        path,_=QFileDialog.getSaveFileName(self,"Esporta classifica","Classifica-C5R.csv","CSV (*.csv)")
        if not path: return
        with open(path,"w",newline="",encoding="utf-8-sig") as file:
            writer=csv.writer(file,delimiter=";")
            writer.writerow(["Posizione","Giocatore","Partite","Vittorie","Patte","Sconfitte","Penalità","Punti","Spareggio"])
            for position,row in enumerate(self.standings(),1):
                tied_group=[item["id"] for item in self.standings() if item["points"]==row["points"]]
                writer.writerow([position,name(row["id"]),row["played"],row["wins"],row["draws"],row["losses"],
                    row["penalty"],row["points"],self.tie_break_value(row["id"],tied_group)])
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
            painter.drawText(180,360,"Cadenza: qualificazione 15+3 · playoff 30+10    Spareggio: Art. 8")
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

    def export_tournament_report_pdf(self,destination=None,announce=True):
        path=destination
        if path is None:
            path,_=QFileDialog.getSaveFileName(self,"Esporta report ufficiale","Report-Ufficiale-C5R.pdf","PDF (*.pdf)")
        if not path:
            return None
        writer=QPdfWriter(path)
        writer.setTitle("Report ufficiale · Coppa dei 5 Re")
        writer.setCreator("Coppa dei 5 Re · Control Room")
        writer.setResolution(150)
        painter=QPainter(writer)
        try:
            page_width=writer.width()
            page_height=writer.height()
            margin=170
            max_width=page_width-margin*2
            y=margin
            page_no=1

            def page_header():
                nonlocal y,page_no
                painter.setPen(QColor("#9A6A18"))
                painter.setFont(QFont("Segoe UI",17,QFont.Weight.Bold))
                painter.drawText(margin,margin+35,"COPPA DEI 5 RE")
                painter.setPen(QColor("#596675"))
                painter.setFont(QFont("Segoe UI",8))
                painter.drawText(margin,page_height-65,
                    f"Report arbitrale · {datetime.now().strftime('%d/%m/%Y %H:%M')} · Pagina {page_no}")
                y=margin+90

            def ensure_space(height):
                nonlocal y,page_no
                if y+height>page_height-margin-100:
                    writer.newPage()
                    page_no+=1
                    page_header()

            def write_line(text,size=9,bold=False,color="#202A35",gap=10):
                nonlocal y
                font=QFont("Segoe UI",size,QFont.Weight.Bold if bold else QFont.Weight.Normal)
                painter.setFont(font)
                painter.setPen(QColor(color))
                rect=painter.fontMetrics().boundingRect(0,0,max_width,2000,Qt.TextFlag.TextWordWrap,str(text))
                height=max(font.pixelSize()+8,rect.height())
                ensure_space(height+gap)
                painter.drawText(QRect(margin,y,max_width,height+4),Qt.TextFlag.TextWordWrap,str(text))
                y+=height+gap

            def section(title):
                nonlocal y
                ensure_space(48)
                write_line(title.upper(),11,True,"#9A6A18",8)
                painter.setPen(QPen(QColor("#D7DEE5"),2))
                painter.drawLine(margin,y,max_width+margin,y)
                y+=14

            page_header()
            write_line("REPORT UFFICIALE DEL TORNEO",15,True,"#202A35",8)
            write_line(f"Arbitro responsabile: {self.referee or 'Non indicato'}")
            write_line("Cadenze regolamentari: qualificazione 15+3 · semifinali e finali 30+10")
            write_line(f"Spareggi: {self.tie_break or 'Regolamento Art. 8'}")
            write_line(f"Generato il: {datetime.now().strftime('%d/%m/%Y alle %H:%M:%S')}")
            completed=sum(1 for value in self.results.values() if value not in (None,"VOID"))+sum(1 for value in self.playoff_results.values() if value not in (None,"VOID"))
            valid_void=sum(1 for value in self.results.values() if value=="VOID")
            total_moves=sum(len(value) for value in self.moves.values())
            write_line(f"Quadro torneo: {completed} partite concluse · {valid_void} annullate/escluse · {total_moves} mosse registrate · {len(self.incident_reports)} verbali/incidenti.")
            section("Classifica generale")
            write_line("POS.   GIOCATORE                         G   V   X   P   PEN.       PUNTI NETTI",9,True)
            for position,row in enumerate(self.standings(),1):
                line=(f"{position:>2}       {name(row['id']):<30} "
                    f"{row['played']:>2}  {row['wins']:>2}  {row['draws']:>2}  {row['losses']:>2}  "
                    f"{row['penalty']:>+6.1f}     {row['points']:>6.1f}")
                write_line(line,9)
            section("Statistiche individuali")
            raw,played,wins,draws,losses=self.raw_stats()
            for row in self.standings():
                player=row["id"]
                rate=(wins[player]/played[player]*100.0) if played[player] else 0.0
                write_line(
                    f"{name(player)} · {played[player]} partite · {wins[player]} vittorie · "
                    f"{draws[player]} patte · {losses[player]} sconfitte · {rate:.1f}% vittorie · "
                    f"{row['points']:.1f} punti netti",
                    9
                )
            section("Calendario e risultati")
            for gid,rnd,white,black in GAMES:
                result=self.results.get(gid,"Da disputare")
                if result=="VOID":
                    result="Annullata / esclusa"
                elif result is None:
                    result="Da disputare"
                write_line(f"Round {rnd} · {gid}   |   {name(white)} – {name(black)}   |   {result}")
            section("Mosse e partite")
            for gid,rnd,white,black in GAMES:
                if not self.moves.get(gid):
                    continue
                try:
                    pgn_node=self.build_pgn_game(gid)
                    sans=pgn_node.accept(chess.pgn.StringExporter(headers=False,variations=False,comments=False)).strip()
                    write_line(f"Round {rnd} · {gid} · {name(white)} – {name(black)}",9,True)
                    write_line(sans or "Nessuna mossa SAN disponibile",8,gap=7)
                except Exception as exc:
                    write_line(f"{gid} · PGN non disponibile: {exc}",8)
            section("Playoff")
            for key,label in (("sf1","Semifinale 1"),("sf2","Semifinale 2"),("third","3°/4° posto"),("final","Finale")):
                result=self.playoff_results.get(key,"Da disputare")
                winner=self.playoff_winners.get(key)
                pair=getattr(self,"playoff_pairs",{}).get(key,(None,None))
                players=" – ".join(name(player) if player else "Da definire" for player in pair)
                if winner:
                    result+=f" · Armageddon: {name(winner)}"
                write_line(f"{label}: {players} · {result}")
            section("Penalità e provvedimenti")
            if not self.penalties:
                write_line("Nessuna penalità registrata.")
            for item in self.penalties:
                write_line(f"{item.get('time','')} · {name(item.get('player',''))} · "
                    f"{float(item.get('points',0)):+.1f} pt · {item.get('reason','')}")
            section("Registro arbitrale")
            if not self.audit_log:
                write_line("Nessuna operazione registrata.")
            for item in self.audit_log[-80:]:
                write_line(f"{item.get('time','')} · {item.get('action','')} · {item.get('entity','')} · "
                    f"{item.get('before','')} → {item.get('after','')} · {item.get('detail','')}",8)
            section("Verbali e note arbitrali")
            if not self.incident_reports and not self.match_notes:
                write_line("Nessun verbale o nota arbitrale registrati.")
            for incident in self.incident_reports:
                write_line("Verbale · "+json.dumps(incident,ensure_ascii=False,default=str),8)
            for gid,notes in self.match_notes.items():
                for note in notes:
                    write_line(f"Nota · {gid} · {note.get('time','')} · {note.get('referee','')} · {note.get('kind','Nota')} · {note.get('text','')}",8)
            section("Attestazione")
            write_line("Il presente documento riepiloga i dati registrati nella Control Room alla data di generazione. "
                "Eventuali rettifiche successive devono essere annotate nel registro arbitrale.")
            write_line("Firma del direttore di gara: ______________________________________________",10)
            write_line("Data: ____________________________     Firma: ______________________________",10)
        finally:
            painter.end()
        if announce:
            self.statusBar().showMessage("Report ufficiale PDF esportato.",3000)
        return str(path)

    def export_final_report_package(self):
        destination,_=QFileDialog.getSaveFileName(
            self,"Crea pacchetto finale del torneo","Pacchetto-Finale-C5R.zip","Archivio ZIP (*.zip)"
        )
        if not destination:
            return
        if not destination.lower().endswith(".zip"):
            destination += ".zip"
        temp_root=Path(tempfile.mkdtemp(prefix="c5r-final-report-"))
        try:
            report_path=temp_root/"Report-Ufficiale-C5R.pdf"
            self.export_tournament_report_pdf(str(report_path),announce=False)
            pgn_dir=temp_root/"PGN"
            pgn_dir.mkdir(parents=True,exist_ok=True)
            exporter=chess.pgn.StringExporter(headers=True,variations=False,comments=True)
            pgn_count=0
            for gid,round_no,white,black in GAMES:
                node=self.build_pgn_game(gid)
                (pgn_dir/f"{gid}.pgn").write_text(
                    node.accept(chess.pgn.StringExporter(headers=True,variations=False,comments=True)),encoding="utf-8"
                )
                pgn_count+=1
            for gid in ("sf1","sf2","third","final"):
                node=self.build_playoff_pgn(gid)
                (pgn_dir/f"{gid}.pgn").write_text(
                    node.accept(chess.pgn.StringExporter(headers=True,variations=False,comments=True)),encoding="utf-8"
                )
                pgn_count+=1

            standings_path=temp_root/"Classifica.csv"
            with standings_path.open("w",newline="",encoding="utf-8-sig") as stream:
                writer=csv.writer(stream,delimiter=";")
                writer.writerow(["Posizione","Giocatore","Partite","Vittorie","Patte","Sconfitte","Penalita","Punti netti"])
                for position,row in enumerate(self.standings(),1):
                    writer.writerow([position,name(row["id"]),row["played"],row["wins"],row["draws"],
                                     row["losses"],row["penalty"],row["points"]])

            audit_path=temp_root/"Registro-arbitrale.csv"
            with audit_path.open("w",newline="",encoding="utf-8-sig") as stream:
                writer=csv.writer(stream,delimiter=";")
                writer.writerow(["Data","Arbitro","Azione","Oggetto","Prima","Dopo","Dettagli"])
                for entry in self.audit_log:
                    writer.writerow([entry.get(key,"") for key in
                        ("time","referee","action","entity","before","after","detail")])

            matches=[]
            for gid,round_no,white,black in GAMES:
                node=self.build_pgn_game(gid)
                moves=node.accept(chess.pgn.StringExporter(headers=False,variations=False,comments=False)).strip()
                matches.append({"id":gid,"round":round_no,"white":name(white),"black":name(black),
                                "result":self.results.get(gid),"moves":moves})
            summary={
                "tournament":"Coppa dei 5 Re",
                "generated_at":datetime.now().isoformat(timespec="seconds"),
                "referee":self.referee,
                "time_controls":{"qualification":"15+3","playoffs":"30+10"},
                "standings":[
                    {"position":position,"player":name(row["id"]),"played":row["played"],
                     "wins":row["wins"],"draws":row["draws"],"losses":row["losses"],
                     "penalty":row["penalty"],"points":row["points"]}
                    for position,row in enumerate(self.standings(),1)
                ],
                "matches":matches,
                "playoff_results":self.playoff_results,
                "playoff_winners":self.playoff_winners,
                "penalties":self.penalties,
                "incidents":self.incident_reports,
                "notes":self.match_notes,
                "total_moves":sum(len(value) for value in self.moves.values()),
            }
            (temp_root/"Riepilogo.json").write_text(
                json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding="utf-8"
            )
            manifest={
                "files":["Report-Ufficiale-C5R.pdf","Classifica.csv","Registro-arbitrale.csv",
                         "Riepilogo.json","PGN/*.pgn"],
                "pgn_files":pgn_count,
                "generated_at":summary["generated_at"],
            }
            (temp_root/"LEGGIMI.txt").write_text(
                "Pacchetto finale Coppa dei 5 Re\nContiene report PDF, classifica, registro arbitrale, "
                "riepilogo JSON e PGN individuali per qualificazione e playoff.\n"
                "I recapiti privati dei giocatori non sono inclusi.\n",
                encoding="utf-8"
            )
            with zipfile.ZipFile(destination,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as archive:
                for item in temp_root.rglob("*"):
                    if item.is_file():
                        archive.write(item,item.relative_to(temp_root).as_posix())
            self.statusBar().showMessage(f"Pacchetto finale creato · {pgn_count} PGN inclusi.",5000)
        except Exception as exc:
            QMessageBox.critical(self,"Report finale non creato",f"Errore durante la generazione del pacchetto: {exc}")
        finally:
            shutil.rmtree(temp_root,ignore_errors=True)

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
            data=decode_document(json.loads(Path(path).read_text(encoding="utf-8")))
            if data.get("schedule"):
                schedule=[(g["id"],int(g["round"]),g["white"],g["black"]) for g in data["schedule"]]
                validate_schedule(schedule)
            answer=QMessageBox.question(self,"Ripristina backup",
                "I dati attuali verranno sostituiti dal backup selezionato. Continuare?",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes: return
            atomic_write_json(storage_path(),data)
            self.state_load_blocked=False
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
        style_table(self.draw_table, row_height=56, selectable=False)
        self.draw_table.setMinimumHeight(320); layout.addWidget(table_card(self.draw_table))
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
            self.results.clear()
            self.moves.clear()
            self.boards.clear()
            self.move_reviews.clear()
            self.eval_history.clear()
            self.move_annotations.clear()
            self.match_notes.clear()
            self.game_terminations.clear()
            self.clocks.clear()
            self.playoff_results.clear()
            self.playoff_winners.clear()
            self.round_closures.clear()
        GAMES[:]=proposed
        BYES.clear()
        for rnd in range(1,6):
            played=[p for g in GAMES if g[1]==rnd for p in (g[2],g[3])]
            BYES[rnd]=next(p for p in ORDER if p not in played)
        self.log_operation("Calendario aggiornato", "", "Calendario precedente", "Nuovo calendario")
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
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 30)
        layout.setSpacing(14)
        layout.addWidget(ui_label("Programma e risultati", "h1"))
        layout.addWidget(ui_label(
            "Le partite sono raggruppate per turno. Usa i filtri per trovare un giocatore o controllare lo stato del girone.",
            "lead", wrap=True
        ))
        filters_card = Card("Filtri del calendario", padding=14, spacing=10)
        filters = QHBoxLayout()
        self.calendar_search = QLineEdit()
        self.calendar_search.setPlaceholderText("Cerca un giocatore o una partita…")
        self.filter_round = QComboBox()
        self.filter_round.addItems(["Tutti i turni"] + [f"Round {r}" for r in range(1, 6)])
        self.filter_player = QComboBox()
        self.filter_player.addItem("Tutti i giocatori", None)
        for pid in ORDER:
            self.filter_player.addItem(name(pid), pid)
        self.filter_status = QComboBox()
        self.filter_status.addItems(["Tutti gli stati", "Da disputare", "In corso", "Concluse", "Annullate"])
        for control in (self.calendar_search, self.filter_round, self.filter_player, self.filter_status):
            filters.addWidget(control, 2 if control is self.calendar_search else 1)
        filters_card.body.addLayout(filters)
        wizard_row = QHBoxLayout()
        wizard_row.addStretch(1)
        round_wizard = QPushButton("ASSISTENTE OPERATIVO ROUND")
        round_wizard.setObjectName("PrimaryButton")
        round_wizard.clicked.connect(self.open_round_wizard)
        print_sheets=QPushButton("STAMPA SCHEDE PARTITA")
        print_sheets.clicked.connect(self.export_all_match_sheets_pdf)
        print_qr=QPushButton("STAMPA QR TAVOLI")
        print_qr.clicked.connect(self.export_all_match_qr_pdf)
        wizard_row.addWidget(round_wizard)
        wizard_row.addWidget(print_sheets)
        wizard_row.addWidget(print_qr)
        filters_card.body.addLayout(wizard_row)
        for control in (self.calendar_search, self.filter_round, self.filter_player, self.filter_status):
            signal = control.textChanged if control is self.calendar_search else control.currentIndexChanged
            signal.connect(self.apply_calendar_filters)
        layout.addWidget(filters_card)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(14)
        self.calendar_combos = {}
        self.calendar_pairings = {}
        self.calendar_cards = {}
        self.calendar_status_labels = {}
        self.calendar_round_sections = {}
        self.calendar_round_progress = {}
        self.calendar_round_bars = {}
        self.calendar_bye_labels = {}

        for rnd in range(1, 6):
            round_card = Card(f"ROUND {rnd:02d}", padding=16, spacing=10)
            header = QHBoxLayout()
            progress_label = ui_label("0/2 concluse", "caption")
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 2)
            progress_bar.setTextVisible(False)
            progress_bar.setFixedWidth(112)
            header.addStretch(1)
            header.addWidget(progress_label)
            header.addWidget(progress_bar)
            round_card.body.addLayout(header)
            self.calendar_round_progress[rnd] = progress_label
            self.calendar_round_bars[rnd] = progress_bar
            for gid, game_round, white, black in [g for g in GAMES if g[1] == rnd]:
                match_card = QFrame()
                match_card.setObjectName("CardRaised")
                row = QHBoxLayout(match_card)
                row.setContentsMargins(14, 10, 14, 10)
                row.setSpacing(12)
                tag = ui_label(gid.replace(f"R{rnd}-", "TAVOLO "), "caption")
                tag.setMinimumWidth(82)
                matchup = ui_label(f"{name(white)}   vs   {name(black)}", "h3")
                status = ui_pill("DA GIOCARE", "neutral")
                combo = QComboBox()
                for val, text in RESULT_OPTIONS:
                    combo.addItem(text, val)
                combo.setMinimumWidth(150)
                combo.setToolTip("Registra o modifica il risultato della partita.")
                combo.currentIndexChanged.connect(
                    lambda i, gid=gid, cb=combo: self.set_result(gid, cb.itemData(i))
                )
                row.addWidget(tag)
                row.addWidget(matchup, 1)
                row.addWidget(status)
                row.addWidget(combo)
                self.calendar_pairings[gid] = matchup
                self.calendar_cards[gid] = match_card
                self.calendar_status_labels[gid] = status
                self.calendar_combos[gid] = combo
                round_card.body.addWidget(match_card)
            bye = ui_label(f"Riposa: {name(BYES[rnd])}", "muted")
            self.calendar_bye_labels[rnd] = bye
            round_card.body.addWidget(bye)
            self.calendar_round_sections[rnd] = round_card
            v.addWidget(round_card)
        v.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.apply_calendar_filters()
        return page

    def apply_calendar_filters(self):
        if not hasattr(self, "calendar_cards"):
            return
        round_text = self.filter_round.currentText()
        selected_player = self.filter_player.currentData()
        state = self.filter_status.currentText()
        query = self.calendar_search.text().strip().casefold() if hasattr(self, "calendar_search") else ""
        visible_by_round = {rnd: 0 for rnd in range(1, 6)}
        for gid, card in self.calendar_cards.items():
            _, rnd, white, black = game(gid)
            matches_round = round_text == "Tutti i turni" or round_text == f"Round {rnd}"
            matches_player = selected_player is None or selected_player in (white, black)
            result = self.results.get(gid)
            is_void = result == "VOID"
            is_done = result not in (None, "VOID")
            is_running = not is_void and not is_done and (
                self.clock_data(gid).get("started") or bool(self.moves.get(gid))
            )
            is_pending = not is_void and not is_done and not is_running
            state_matches = (
                state == "Tutti gli stati"
                or (state == "Da disputare" and is_pending)
                or (state == "In corso" and is_running)
                or (state == "Concluse" and is_done)
                or (state == "Annullate" and is_void)
            )
            match_text = f"{gid} {name(white)} {name(black)}".casefold()
            matches_query = not query or query in match_text
            visible = matches_round and matches_player and state_matches and matches_query
            card.setVisible(visible)
            if visible:
                visible_by_round[rnd] += 1
        for rnd, section in self.calendar_round_sections.items():
            visible = visible_by_round[rnd] > 0
            section.setVisible(visible)
            self.calendar_bye_labels[rnd].setVisible(visible)
        self._refresh_calendar_round_progress()

    def _refresh_calendar_round_progress(self):
        if not hasattr(self, "calendar_round_progress"):
            return
        for rnd in range(1, 6):
            games = [game_row for game_row in GAMES if game_row[1] == rnd]
            done = sum(1 for gid, _, _, _ in games if self.results.get(gid) not in (None, "VOID"))
            voided = sum(1 for gid, _, _, _ in games if self.results.get(gid) == "VOID")
            progress_label = self.calendar_round_progress[rnd]
            closed = self.round_closures.get(str(rnd))
            progress_label.setText(
                f"{done}/2 concluse" + (f" · {voided} annullate" if voided else "")
                + (f" · CHIUSO {closed}" if closed else "")
            )
            self.calendar_round_bars[rnd].setValue(done + voided)
            self.calendar_bye_labels[rnd].setText(f"RIPOSA  ·  {name(BYES[rnd])}")

    def build_standings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 30)
        layout.setSpacing(16)
        layout.addWidget(ui_label("Classifica generale", "h1"))
        layout.addWidget(ui_label(
            "Il punteggio netto include le penalità. Gli spareggi seguono l'Art. 8: "
            "scontro diretto tra due soli giocatori, Sonneborn–Berger e numero di vittorie.",
            "lead", wrap=True
        ))
        podium_row = QHBoxLayout()
        podium_row.setSpacing(12)
        self.podium_cards = {}
        for rank in (2, 1, 3):
            variant = "CardAccent" if rank == 1 else "Card"
            card = Card(f"{rank}° POSTO", variant=variant, padding=16, spacing=7)
            top = QHBoxLayout()
            avatar = Avatar("?", T.player_tint(rank - 1), 42)
            top.addWidget(avatar)
            person = QVBoxLayout()
            player_label = ui_label("Da definire", "h3")
            points_label = ui_label("0,0 punti", "numsm")
            person.addWidget(player_label)
            person.addWidget(points_label)
            top.addLayout(person, 1)
            card.body.addLayout(top)
            caption = ui_label("Posizione provvisoria", "caption")
            caption.setWordWrap(True)
            card.body.addWidget(caption)
            self.podium_cards[rank] = {
                "avatar": avatar, "name": player_label, "points": points_label,
                "caption": caption
            }
            podium_row.addWidget(card, 1)
        layout.addLayout(podium_row)

        table_card_widget = Card("Dettaglio classifica", "G = giocate · V = vittorie · X = patte · P = sconfitte")
        self.st_table = QTableWidget(0, 8)
        self.st_table.setHorizontalHeaderLabels(["POS", "GIOCATORE", "G", "V", "X", "P", "PEN.", "PT NETTI"])
        self.st_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (0, 2, 3, 4, 5, 6, 7):
            self.st_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        style_table(self.st_table, row_height=48, selectable=False)
        table_card_widget.body.addWidget(table_card(self.st_table))
        layout.addWidget(table_card_widget, 1)
        self.st_summary = ui_label("", "muted", wrap=True)
        layout.addWidget(self.st_summary)
        return page

    def build_odds(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 30)
        layout.setSpacing(16)
        layout.addWidget(ui_label("Probabilità e scenari", "h1"))
        layout.addWidget(ui_label(
            "Stime Monte Carlo su 15.000 scenari, basate sui pronostici iniziali e sui risultati registrati. "
            "La quota equa è il reciproco della probabilità stimata: non è una quota bookmaker.",
            "lead", wrap=True
        ))
        disclaimer = Card("Come leggere i dati", "Le barre aiutano a confrontare le probabilità; non rappresentano previsioni certe.")
        legend = QHBoxLayout()
        legend.addWidget(ui_pill("Vittoria torneo", "brass"))
        legend.addWidget(ui_pill("Accesso top 4", "success"))
        legend.addStretch(1)
        disclaimer.body.addLayout(legend)
        layout.addWidget(disclaimer)
        self.odds_rows = []
        self.odds_rows_layout = QVBoxLayout()
        self.odds_rows_layout.setSpacing(10)
        for pid in ORDER:
            row_card = Card(padding=14, spacing=8)
            top = QHBoxLayout()
            avatar = Avatar(name(pid)[:1], T.player_tint(ORDER.index(pid)), 38)
            player_label = ui_label(name(pid), "h3")
            rank_label = ui_pill("—", "neutral")
            quota_label = ui_label("Quota equa —", "mono")
            top.addWidget(avatar)
            top.addWidget(player_label, 1)
            top.addWidget(rank_label)
            top.addWidget(quota_label)
            row_card.body.addLayout(top)
            win_line = QHBoxLayout()
            win_line.addWidget(ui_label("VITTORIA", "field"))
            win_bar = ProbBar(T.C.brass)
            win_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            win_line.addWidget(win_bar, 1)
            row_card.body.addLayout(win_line)
            top_line = QHBoxLayout()
            top_line.addWidget(ui_label("TOP 4", "field"))
            top_bar = ProbBar(T.C.success)
            top_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            top_line.addWidget(top_bar, 1)
            row_card.body.addLayout(top_line)
            self.odds_rows.append({
                "player": pid, "card": row_card, "name": player_label,
                "rank": rank_label, "quota": quota_label, "win": win_bar, "top": top_bar,
            })
            self.odds_rows_layout.addWidget(row_card)
        layout.addLayout(self.odds_rows_layout)
        forecast=Card("Simulatore predittivo avanzato",
            "Confronta scenari prudente, base e ad alta sensibilità. Gli intervalli sono incertezza Monte Carlo, non garanzie sul risultato.")
        forecast_controls=QHBoxLayout()
        self.forecast_runs_combo=QComboBox()
        for runs,label in [(2000,"2.000 simulazioni"),(5000,"5.000 simulazioni"),(10000,"10.000 simulazioni")]:
            self.forecast_runs_combo.addItem(label,runs)
        forecast_controls.addWidget(self.forecast_runs_combo)
        forecast_button=QPushButton("CONFRONTA SCENARI")
        forecast_button.setObjectName("PrimaryButton")
        forecast_button.clicked.connect(self.refresh_advanced_forecast)
        forecast_controls.addWidget(forecast_button)
        forecast.body.addLayout(forecast_controls)
        self.forecast_summary=ui_label(
            "Avvia il confronto per calcolare probabilità, intervalli al 95% e qualità storica del modello.",
            "muted", wrap=True)
        forecast.body.addWidget(self.forecast_summary)
        layout.addWidget(forecast)
        self.odds_footer = ui_label("", "caption", wrap=True)
        layout.addWidget(self.odds_footer)
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
        variant = "CardAccent" if title == "FINALE" else "Card"
        frame = QFrame()
        frame.setObjectName(variant)
        v = QVBoxLayout(frame)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(9)
        heading = QLabel(title)
        heading.setObjectName("Eyebrow")
        x = QLabel(a)
        x.setObjectName("MatchTitle")
        y = QLabel(b)
        y.setObjectName("MatchTitle")
        separator = QFrame()
        separator.setObjectName("Divider")
        v.addWidget(heading)
        v.addWidget(x)
        v.addWidget(separator)
        v.addWidget(y)
        frame.labels = (heading, x, y)
        frame.status_label = QLabel("DA DISPUTARE")
        frame.status_label.setProperty("role", "caption")
        v.addWidget(frame.status_label)
        return frame

    def build_playoffs(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 24, 26, 30)
        layout.setSpacing(16)
        layout.addWidget(ui_label("Tabellone playoff", "h1"))
        layout.addWidget(ui_label(
            "Le prime quattro classificate accedono alle semifinali: 1ª–4ª e 2ª–3ª. "
            "I vincitori disputano la finale, gli sconfitti la partita per il terzo posto.",
            "lead", wrap=True
        ))
        notice = Card("Regola dell'Armageddon", "In caso di patta nei playoff il pareggio resta registrato. Il vincitore dell'Armageddon va annotato separatamente secondo condizioni definite dal direttore di gara.", variant="CardAccent", padding=14)
        layout.addWidget(notice)

        overview = Card("Percorso verso la finale", "Il tabellone si aggiorna in base alla classifica e ai risultati registrati.")
        self.playoff_overview = ui_label("Semifinali in attesa delle prime quattro posizioni.", "body", wrap=True)
        self.playoff_champion = ui_label("Vincitore del torneo: da definire", "h3", wrap=True)
        overview.body.addWidget(self.playoff_overview)
        overview.body.addWidget(self.playoff_champion)
        layout.addWidget(overview)

        semi_row = QHBoxLayout()
        semi_row.setSpacing(14)
        self.sf1 = self.bracket_card("SEMIFINALE 1 · 1ª vs 4ª", "1ª classificata", "4ª classificata")
        self.sf2 = self.bracket_card("SEMIFINALE 2 · 2ª vs 3ª", "2ª classificata", "3ª classificata")
        semi_row.addWidget(self.sf1, 1)
        semi_row.addWidget(self.sf2, 1)
        layout.addLayout(semi_row)

        connector = ui_label("VINCENTI DELLE SEMIFINALI  ↓  FINALE     ·     SCONFITTI  ↓  3° / 4° POSTO", "caption", align=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(connector)

        lower = QHBoxLayout()
        lower.setSpacing(14)
        self.final = self.bracket_card("FINALE", "Vincente SF1", "Vincente SF2")
        self.third = self.bracket_card("3° / 4° POSTO", "Perdente SF1", "Perdente SF2")
        lower.addWidget(self.final, 1)
        lower.addWidget(self.third, 1)
        layout.addLayout(lower)

        self.playoff_cards = {"sf1": self.sf1, "sf2": self.sf2, "final": self.final, "third": self.third}
        self.playoff_winners = getattr(self, "playoff_winners", {})
        for key, card in self.playoff_cards.items():
            card.clock_label = QLabel("BIANCO 30:00 · NERO 30:00 · TOCCA A WHITE")
            card.clock_label.setObjectName("Muted")
            card.layout().addWidget(card.clock_label)

            card.result_box = QComboBox()
            card.result_box.addItem("In corso", None)
            for value, text in RESULT_OPTIONS:
                if value is not None:
                    card.result_box.addItem(text, value)
            card.result_box.addItem("Annullata / esclusa", "VOID")
            card.result_box.currentIndexChanged.connect(
                lambda i, k=key, current=card: self.set_playoff_result(k, current.result_box.itemData(i))
            )
            card.winner_box = QComboBox()
            card.winner_box.addItem("Vincitore Armageddon da definire", None)
            card.winner_box.currentIndexChanged.connect(
                lambda i, k=key, current=card: self.set_playoff_winner(k, current.winner_box.itemData(i))
            )
            card.layout().addWidget(ui_label("RISULTATO", "field"))
            card.layout().addWidget(card.result_box)
            card.layout().addWidget(ui_label("EVENTUALE VINCITORE ARMAGEDDON", "field"))
            card.layout().addWidget(card.winner_box)

            buttons = QGridLayout()
            start = QPushButton("AVVIA 30+10")
            start.clicked.connect(lambda checked=False, k=key: self.start_playoff_clock(k))
            switch = QPushButton("CAMBIA TURNO · +10s")
            switch.clicked.connect(lambda checked=False, k=key: self.switch_playoff_clock(k))
            draw = QPushButton("PATTA / ARMAGEDDON")
            draw.clicked.connect(lambda checked=False, k=key: self.offer_playoff_draw(k))
            resign = QPushButton("ABBANDONO")
            resign.setProperty("kind", "danger")
            resign.clicked.connect(lambda checked=False, k=key: self.resign_playoff(k))
            force = QPushButton("FORZA RISULTATO")
            force.clicked.connect(lambda checked=False, k=key: self.force_playoff_result(k))
            buttons.addWidget(start, 0, 0)
            buttons.addWidget(switch, 0, 1)
            buttons.addWidget(draw, 1, 0)
            buttons.addWidget(resign, 1, 1)
            buttons.addWidget(force, 2, 0, 1, 2)
            card.layout().addLayout(buttons)
            card.clock_start_button = start
            card.clock_switch_button = switch
            card.draw_button = draw
            card.resign_button = resign
            card.force_button = force
        layout.addStretch(1)
        return page

    def set_playoff_result(self,key,value,detail="Inserimento manuale"):
        if getattr(self,"state_load_blocked",False):
            QMessageBox.warning(self,"Archivio non disponibile",
                "Non registro risultati playoff finché l'archivio locale non è leggibile. Ripristina un backup JSON valido.")
            return
        old=self.playoff_results.get(key)
        if old==value: return
        if old is not None:
            answer=QMessageBox.question(self,"Modifica risultato playoff",
                f"Sostituire {old} con {value or 'In corso'}?",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:
                self.refresh_playoffs(); return
        if value is None:
            self.playoff_results.pop(key,None)
            self.game_terminations.pop(key,None)
            self.playoff_winners.pop(key,None)
        else:
            self.playoff_results[key]=value
            self.game_terminations[key]={"termination":"time forfeit" if "bandierina" in detail.lower() or "tempo" in detail.lower() else ("abandoned" if "abbandono" in detail.lower() else ("adjudication" if "arbitro" in detail.lower() or "forz" in detail.lower() else "normal")),"detail":detail}
            self.clock_data(key)["started"]=False
            if value!="1/2-1/2":
                self.playoff_winners.pop(key,None)
        self.log_operation("Risultato playoff",key,old or "In corso",value or "In corso",detail)
        if value not in (None,"VOID"):
            timed_out="bandierina" in detail.lower() or "tempo" in detail.lower()
            self.record_operational_alert(
                "Tempo playoff esaurito · risultato da validare" if timed_out else "Risultato playoff da verificare",
                f"{key.upper()} · esito {value} · {detail}",
                "danger" if timed_out else "warning","playoffs",f"playoff:{key}:{len(self.audit_log)}"
            )
        if key in ("sf1","sf2") and old is not None and old!=value:
            for downstream in ("final","third"):
                previous=self.playoff_results.pop(downstream,None)
                previous_winner=self.playoff_winners.pop(downstream,None)
                if previous is not None or previous_winner is not None:
                    self.log_operation("Playoff downstream azzerato",downstream,
                        previous or "In corso", "Da rigiocare",
                        f"È cambiato il risultato di {key}")
        self.save(); self.save_recovery(); self.refresh_playoffs()
    def set_playoff_winner(self,key,player):
        old=self.playoff_winners.get(key)
        if player is None:
            self.playoff_winners.pop(key,None)
        else:
            pair=getattr(self,"playoff_pairs",{}).get(key,(None,None))
            if player not in pair: return
            self.playoff_winners[key]=player
        self.log_operation("Vincitore Armageddon",key,old or "Da definire",player or "Da definire")
        if key in ("sf1","sf2") and old!=player:
            for downstream in ("final","third"):
                previous=self.playoff_results.pop(downstream,None)
                previous_winner=self.playoff_winners.pop(downstream,None)
                if previous is not None or previous_winner is not None:
                    self.log_operation("Playoff downstream azzerato",downstream,
                        previous or "In corso","Da rigiocare",f"È cambiato il vincitore di {key}")
        self.save(); self.refresh_playoffs()
    def offer_playoff_draw(self,key):
        pair=getattr(self,"playoff_pairs",{}).get(key,(None,None))
        if not all(pair):
            QMessageBox.information(self,"Playoff","Gli abbinamenti non sono ancora definiti.")
            return
        answer=QMessageBox.question(self,"Patta consensuale",
            f"{name(pair[0])} e {name(pair[1])} confermano entrambi la patta della partita 30+10?\\n"
            "Il regolamento Art. 10 richiede poi un Armageddon. Le condizioni non sono ancora definite.",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer==QMessageBox.StandardButton.Yes:
            self.set_playoff_result(key,"1/2-1/2",detail="Patta consensuale · Armageddon da disputare ai sensi dell'Art. 10")
            QMessageBox.information(self,"Armageddon richiesto",
                "Registrata la patta. Disputate l'Armageddon secondo condizioni comunicate dal direttore di gara; quindi selezionate il vincitore nel menu dedicato.")
    def resign_playoff(self,key):
        pair=getattr(self,"playoff_pairs",{}).get(key,(None,None))
        if not all(pair) or self.playoff_results.get(key): return
        side=self.clock_data(key).get("side_to_move","white")
        resigning=pair[0] if side=="white" else pair[1]
        result="0-1" if side=="white" else "1-0"
        answer=QMessageBox.question(self,"Abbandono playoff",
            f"Confermi l'abbandono di {name(resigning)}? Risultato {result}.",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer==QMessageBox.StandardButton.Yes:
            self.set_playoff_result(key,result,detail=f"Abbandono di {name(resigning)}")
    def force_playoff_result(self,key):
        options=["1-0","1/2-1/2","0-1"]
        choice,ok=QInputDialog.getItem(self,"Forzatura risultato playoff",f"{key.upper()} · risultato arbitrale:",options,0,False)
        if not ok: return
        detail,ok=QInputDialog.getText(self,"Motivazione arbitro","Motivazione:",text="Forzatura del direttore di gara")
        if ok:
            self.set_playoff_result(key,choice,detail=detail or "Forzatura arbitrale")
    def playoff_pair_winner(self,key,pair=None):
        if pair is None:
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
        node=self.build_pgn_game(gid)
        content=node.accept(chess.pgn.StringExporter(headers=True,variations=False,comments=True))
        path,_=QFileDialog.getSaveFileName(self,"Esporta PGN",gid+".pgn","Partite PGN (*.pgn)")
        if path:
            Path(path).write_text(content,encoding="utf-8")
            self.statusBar().showMessage("PGN esportato con le annotazioni C5R disponibili.",3000)
    def refresh_all(self):
        if not hasattr(self,"live_cards"): return
        for c in self.live_cards: c.refresh()
        for gid, cb in self.calendar_combos.items():
            g = game(gid)
            if hasattr(self, "calendar_pairings"):
                self.calendar_pairings[gid].setText(f"{name(g[2])}   vs   {name(g[3])}")
            cb.blockSignals(True)
            cb.setCurrentIndex(max(0, cb.findData(self.results.get(gid))))
            cb.blockSignals(False)
            result = self.results.get(gid)
            if result == "VOID":
                set_pill(self.calendar_status_labels[gid], "ANNULLATA", "danger")
            elif result:
                set_pill(self.calendar_status_labels[gid], "CONCLUSA", "success")
            elif self.clock_data(gid).get("started") or self.moves.get(gid):
                set_pill(self.calendar_status_labels[gid], "IN CORSO", "warning")
            else:
                set_pill(self.calendar_status_labels[gid], "DA GIOCARE", "neutral")
        if hasattr(self,"calendar_bye_labels"):
            for rnd,label in self.calendar_bye_labels.items():
                label.setText(f"ROUND {rnd}  ·  Riposa: {name(BYES[rnd])}  ·  BYE")
        self.refresh_draw_page()
        self.refresh_standings(); self.refresh_odds(); self.refresh_penalties(); self.refresh_playoffs()
        self.refresh_dashboard(); self.refresh_archive(); self.refresh_h2h(); self.refresh_audit()
        self.refresh_player_profile(); self.refresh_compare(); self.refresh_openings(); self.refresh_snapshot_status(); self.refresh_history(); self.refresh_incidents()
        self.refresh_communications()
        self.apply_calendar_filters(); self.refresh_notification_badge()
        if self.broadcast and self.broadcast.isVisible(): self.broadcast.refresh_from_app()
    def refresh_standings(self):
        rows = self.standings()
        self.st_table.setRowCount(5)
        previous = None
        rank = 0
        for i, row in enumerate(rows):
            current_key = (
                row["points"],
                self.tie_break_value(row["id"], [item["id"] for item in rows if item["points"] == row["points"]])
            )
            if previous is None or current_key != previous:
                rank = i + 1
            previous = current_key
            display_name = name(row["id"]) + (" · RITIRATO" if row["id"] in self.withdrawn_players else "")
            values = [
                f"{rank}°", display_name, str(row["played"]), str(row["wins"]),
                str(row["draws"]), str(row["losses"]),
                f"{row['penalty']:+.1f}" if row["penalty"] else "—",
                f"{row['points']:.1f}"
            ]
            for column, value in enumerate(values):
                prefix = "🥇 " if rank == 1 else "🥈 " if rank == 2 else "🥉 " if rank == 3 else ""
                item = QTableWidgetItem(prefix + value if column == 0 else value)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter if column != 1
                    else Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
                if row["id"] == "simone":
                    item.setForeground(QColor(GOLD))
                if column == 7:
                    item.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
                self.st_table.setItem(i, column, item)
        for position in (1, 2, 3):
            podium = self.podium_cards.get(position)
            if not podium:
                continue
            row = rows[position - 1]
            initials = "".join(part[0] for part in name(row["id"]).split()[:2]).upper()
            podium["avatar"].set_player(initials or "?", T.player_tint(ORDER.index(row["id"])))
            podium["name"].setText(name(row["id"]))
            podium["points"].setText(f"{row['points']:.1f} punti netti")
            podium["caption"].setText(
                f"{row['played']}/5 partite · {row['wins']} vittorie · "
                f"{row['draws']} patte · penalità {row['penalty']:+.1f}"
            )
        concluded = sum(1 for value in self.results.values() if value not in (None, "VOID"))
        voided = sum(1 for value in self.results.values() if value == "VOID")
        unresolved_ties = False
        for points in {row["points"] for row in rows}:
            point_group = [row for row in rows if row["points"] == points]
            if len(point_group) > 1:
                ids = [row["id"] for row in point_group]
                values = [self.tie_break_value(player_id, ids) for player_id in ids]
                if len(set(values)) < len(values):
                    unresolved_ties = True
                    break
        self.st_summary.setText(
            f"PARTITE CONCLUSE  {concluded}/10  ·  ANNULLATE {voided}  ·  PENALITÀ {len(self.penalties)}"
            + ("  ·  SPAREGGIO ART. 8 DA DISPUTARE" if unresolved_ties else "")
        )

    def advanced_forecast(self,n=2000):
        raw,played,_,_,_=self.raw_stats()
        penalties=self.penalty_points()
        current={p:raw[p]+penalties[p] for p in PLAYERS}
        form={p:(raw[p]+1.0)/(played[p]+2.0) for p in PLAYERS}
        remaining=[g for g in GAMES if self.results.get(g[0]) is None]
        payload=json.dumps({"results":self.results,"penalties":self.penalties,"schedule":GAMES},
            sort_keys=True,ensure_ascii=False,default=str)
        seed=int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8],"big")
        modes=(("Prudente",0.55,0.015),("Base",1.0,0.035),("Sensibilità alta",1.55,0.065))
        forecasts={}
        count=max(500,int(n))
        for index,(label,factor,noise) in enumerate(modes):
            rng=random.Random(seed+index*104729)
            wins={p:0.0 for p in PLAYERS}
            for _ in range(count):
                score=current.copy()
                for gid,r,w,b in remaining:
                    base_white,base_black,(pw,pd,pb)=PAIR_PRIORS[frozenset((w,b))]
                    if w!=base_white:
                        pw,pb=pb,pw
                    shift=max(-0.24,min(0.24,0.20*factor*(form[w]-form[b])))
                    jitter=rng.uniform(-noise,noise)
                    pw=max(0.025,pw+shift+jitter)
                    pb=max(0.025,pb-shift-jitter)
                    total=pw+pd+pb
                    pw,pd,pb=pw/total,pd/total,pb/total
                    draw=rng.random()
                    if draw<pw: score[w]+=1
                    elif draw<pw+pd: score[w]+=.5; score[b]+=.5
                    else: score[b]+=1
                best=max(score.values())
                tied=[p for p in PLAYERS if score[p]==best]
                for player in tied:
                    wins[player]+=1/len(tied)
            forecasts[label]={}
            for player in PLAYERS:
                probability=wins[player]/count
                margin=1.96*math.sqrt(max(0.0,probability*(1-probability)/count))
                forecasts[label][player]=(probability,max(0.0,probability-margin),min(1.0,probability+margin))
        brier_values=[]
        for gid,r,w,b in GAMES:
            result=self.results.get(gid)
            if result in (None,"VOID"):
                continue
            base_white,base_black,(pw,pd,pb)=PAIR_PRIORS[frozenset((w,b))]
            if w!=base_white:
                pw,pb=pb,pw
            target=(1.0,0.0,0.0) if result=="1-0" else ((0.0,0.0,1.0) if result=="0-1" else (0.0,1.0,0.0))
            brier_values.append(sum((actual-predicted)**2 for actual,predicted in zip(target,(pw,pd,pb)))/3.0)
        return forecasts,(sum(brier_values)/len(brier_values) if brier_values else None),len(brier_values),current,form

    def refresh_advanced_forecast(self):
        if not hasattr(self,"forecast_summary"):
            return
        runs=int(self.forecast_runs_combo.currentData() or 2000)
        try:
            forecasts,brier,sample,current,form=self.advanced_forecast(runs)
            rows=[]
            for player in sorted(PLAYERS,key=lambda item:forecasts["Base"][item][0],reverse=True):
                cautious=forecasts["Prudente"][player][0]*100
                base,low,high=forecasts["Base"][player]
                sensitive=forecasts["Sensibilità alta"][player][0]*100
                rows.append(f"{name(player)}: prudente {cautious:.1f}% · base {base*100:.1f}% "
                    f"(IC 95% {low*100:.1f}–{high*100:.1f}%) · sensibilità alta {sensitive:.1f}%")
            leader=max(current,key=current.get)
            brier_text=(f"Brier score storico: {brier:.3f} su {sample} partite concluse (più basso è meglio)."
                if brier is not None else "Brier score non disponibile: non ci sono partite valide concluse.")
            self.forecast_summary.setText(
                f"{runs:,} simulazioni per scenario.\n".replace(",",".")
                +"\n".join(rows)+"\n\n"
                +f"Driver leggibili: {name(leader)} guida per punti attuali ({current[leader]:.1f}); "
                "la forma è regolarizzata con prior 1 vittoria / 2 partite per ridurre oscillazioni con pochi risultati.\n"
                +brier_text+" Gli intervalli descrivono solo l'errore Monte Carlo, non l'incertezza completa del modello."
            )
        except Exception as exc:
            self.forecast_summary.setText(f"Simulazione non disponibile: {exc}")

    def refresh_odds(self):
        values = self.odds()
        ordered = sorted(PLAYERS, key=lambda player: values[player][0], reverse=True)
        rows_by_player = {row["player"]: row for row in self.odds_rows}
        for rank, player in enumerate(ordered, 1):
            win, top = values[player]
            row = rows_by_player[player]
            row["rank"].setText(f"#{rank}")
            row["rank"].setProperty("tone", "brass" if rank == 1 else "neutral")
            row["rank"].style().unpolish(row["rank"])
            row["rank"].style().polish(row["rank"])
            row["quota"].setText("Quota equa —" if win <= 0 else f"Quota equa  {1 / win:.2f}")
            row["win"].set(win, f"{win * 100:.1f}%")
            row["top"].set(top, f"{top * 100:.1f}%")
            self.odds_rows_layout.removeWidget(row["card"])
            self.odds_rows_layout.insertWidget(rank - 1, row["card"])
        self.odds_footer.setText(
            "15.000 scenari Monte Carlo · calcolo deterministico aggiornato dopo risultati, penalità e calendario. "
            "La quota equa è 1 / probabilità stimata: non è una quota bookmaker e non è una previsione certa."
        )

    def refresh_penalties(self):
        self.pen_list.clear()
        if not self.penalties: self.pen_list.addItem("Nessuna penalità registrata.")
        for x in self.penalties:
            self.pen_list.addItem(f"{name(x.get('player',''))}   {x.get('points',0):+.1f} pt   ·   {x.get('reason','')}   ·   {x.get('time','')}")
    def refresh_playoffs(self):
        if not hasattr(self, "playoff_cards"):
            return
        rows = self.standings()
        ids = [row["id"] for row in rows]
        pair1 = (ids[0], ids[3])
        pair2 = (ids[1], ids[2])
        self.playoff_pairs = {"sf1": pair1, "sf2": pair2}
        winner1 = self.playoff_pair_winner("sf1", pair1)
        winner2 = self.playoff_pair_winner("sf2", pair2)
        loser1 = next((player for player in pair1 if player and player != winner1), None) if winner1 else None
        loser2 = next((player for player in pair2 if player and player != winner2), None) if winner2 else None
        final_pair = (winner1, winner2)
        third_pair = (loser1, loser2)
        self.playoff_pairs.update({"final": final_pair, "third": third_pair})
        labels = {
            "sf1": ("SEMIFINALE 1", pair1),
            "sf2": ("SEMIFINALE 2", pair2),
            "final": ("FINALE", final_pair),
            "third": ("3° / 4° POSTO", third_pair),
        }
        for key, card in self.playoff_cards.items():
            title, pair = labels[key]
            card.labels[0].setText(title)
            card.labels[1].setText(name(pair[0]) if pair[0] else "Da definire")
            card.labels[2].setText(name(pair[1]) if pair[1] else "Da definire")
            result = self.playoff_results.get(key)
            winner = self.playoff_pair_winner(key, pair) if all(pair) else None
            for index, player in ((1, pair[0]), (2, pair[1])):
                is_winner = bool(winner and player == winner)
                color = T.C.brass_hi if is_winner else T.C.text
                card.labels[index].setStyleSheet(
                    f"color: {color}; font-weight: {'800' if is_winner else '600'};"
                )
            if result == "1/2-1/2":
                card.status_label.setText(
                    "PATTA · ARMAGEDDON DA REGISTRARE"
                    if not self.playoff_winners.get(key) else f"ARMAGEDDON · {name(self.playoff_winners[key])}"
                )
            elif result in ("1-0", "0-1"):
                card.status_label.setText(f"VINCITORE · {name(winner)}" if winner else "INCONTRO CONCLUSO")
            elif self.clock_data(key).get("started"):
                card.status_label.setText("IN CORSO · OROLOGIO ATTIVO")
            elif all(pair):
                card.status_label.setText("PRONTO PER IL 30+10")
            else:
                card.status_label.setText("IN ATTESA DELLE QUALIFICATE")
            card.result_box.blockSignals(True)
            card.result_box.setCurrentIndex(max(0, card.result_box.findData(result)))
            card.result_box.blockSignals(False)
            card.result_box.setEnabled(all(pair))
            card.winner_box.blockSignals(True)
            card.winner_box.clear()
            card.winner_box.addItem("Vincitore da definire", None)
            for player in pair:
                if player:
                    card.winner_box.addItem(name(player), player)
            chosen = self.playoff_winners.get(key)
            if chosen not in pair:
                self.playoff_winners.pop(key, None)
                chosen = None
            card.winner_box.setCurrentIndex(max(0, card.winner_box.findData(chosen)))
            card.winner_box.setEnabled(result == "1/2-1/2" and pair[0] is not None and pair[1] is not None)
            card.winner_box.blockSignals(False)
            card.clock_label.setText(self.playoff_clock_text(key))
            clock = self.clock_data(key)
            active = bool(clock.get("started")) and result is None and all(pair)
            card.clock_start_button.setEnabled(not active and result is None and all(pair))
            card.clock_switch_button.setEnabled(active)
            card.draw_button.setEnabled(result is None and all(pair))
            card.resign_button.setEnabled(result is None and all(pair))
            card.force_button.setEnabled(all(pair))
        semi_ready = sum(1 for pair in (pair1, pair2) if all(pair))
        completed = sum(
            1 for key in ("sf1", "sf2", "final", "third")
            if self.playoff_results.get(key) not in (None, "VOID")
        )
        self.playoff_overview.setText(
            f"{semi_ready}/2 semifinali pronte · {completed}/4 incontri conclusi. "
            "Le qualificate derivano dalla classifica corrente."
        )
        final_result = self.playoff_results.get("final")
        champion = None
        if all(final_pair):
            if final_result == "1-0":
                champion = final_pair[0]
            elif final_result == "0-1":
                champion = final_pair[1]
            elif final_result == "1/2-1/2":
                champion = self.playoff_winners.get("final")
        self.playoff_champion.setText(
            f"CAMPIONE · {name(champion)}" if champion else "Vincitore del torneo: da definire"
        )

    def open_broadcast(self):
        if self.broadcast is None: self.broadcast=BroadcastWindow(self)
        self.broadcast.refresh_from_app()
        self.broadcast.showNormal()
        self.broadcast.resize(1180,760)
        self.broadcast.show()
        self.broadcast.raise_()
        self.broadcast.activateWindow()
    def closeEvent(self,event):
        if hasattr(self,"clock_timer"): self.clock_timer.stop()
        if hasattr(self,"notification_timer"): self.notification_timer.stop()
        if hasattr(self,"_move_save_timer"):
            self._move_save_timer.stop()
            self._move_save_pending=False
        probe=getattr(self,"_public_probe_thread",None)
        if probe is not None and probe.isRunning():
            probe.wait(6000)
        server=getattr(self,"match_http_server",None)
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass
            self.match_http_server=None
        service=getattr(self,"engine_service",None)
        if service is not None and service.isRunning():
            service.stop()
            service.wait(6000)
        if not getattr(self,"state_load_blocked",False):
            self.save()
            self.recovery_path.unlink(missing_ok=True)
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
    if "--bundle-smoke" in sys.argv:
        report=Path(os.environ.get("TEMP",str(Path.home())))/"c5r-bundle-smoke.txt"
        win=None
        try:
            app=QApplication(["Coppa5Re"]); app.setApplicationName(APP_NAME); T.apply_theme(app)
            win=MainWindow()
            engine_path=win.find_engine()
            logo_widgets=win.findChildren(LogoWidget)
            logo_status=[widget.renderer.isValid() for widget in logo_widgets]
            engine_ok=bool(engine_path and Path(engine_path).is_file())
            logo_ok=bool(logo_widgets) and all(logo_status)
            report.write_text(
                f"engine_ok={engine_ok}\\nengine_path={engine_path}\\n"
                f"logo_count={len(logo_widgets)}\\nlogo_status={logo_status}\\n"
                f"meipass={getattr(sys,'_MEIPASS',None)}\\n",
                encoding="utf-8",
            )
            win.close()
            sys.exit(0 if engine_ok and logo_ok else 2)
        except Exception as exc:
            try:
                report.write_text(f"ERROR: {type(exc).__name__}: {exc}\\n",encoding="utf-8")
            except Exception:
                pass
            if win is not None:
                try: win.close()
                except Exception: pass
            sys.exit(3)
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); T.apply_theme(app)
    win=MainWindow(); win.show(); sys.exit(app.exec())
if __name__=="__main__": main()
