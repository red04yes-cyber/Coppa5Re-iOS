"""Windows analytics page: read-only insights and hypothetical standings."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel
)

try:
    from .c5r_widgets import Card, LineChart, StatTile, style_table, table_card, label as ui_label
    from .c5r_analytics import (
        player_performance, player_color_statistics, player_error_statistics,
        player_time_statistics, simulate_standings, tournament_summary,
    )
except ImportError:
    from c5r_widgets import Card, LineChart, StatTile, style_table, table_card, label as ui_label
    from c5r_analytics import (
        player_performance, player_color_statistics, player_error_statistics,
        player_time_statistics, simulate_standings, tournament_summary,
    )


class TournamentAnalyticsPage(QWidget):
    def __init__(self, app, players, player_order, schedule, player_name, player_color):
        super().__init__()
        self.app = app
        self.players = players
        self.player_order = player_order
        self.schedule = schedule
        self.player_name = player_name
        self.player_color = player_color
        self.simulation_controls = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 30)
        root.setSpacing(14)
        root.addWidget(ui_label("Analisi del torneo", "h1"))
        root.addWidget(ui_label(
            "Andamento, rendimento per colore, precisione, tempi di riflessione e simulazione ipotetica. "
            "Le analisi temporali iniziano a raccogliere dati dalle mosse registrate con questa versione.",
            "lead", wrap=True
        ))

        self.player_combo = QComboBox()
        for player_id in player_order:
            self.player_combo.addItem(player_name(player_id), player_id)
        self.player_combo.currentIndexChanged.connect(self.refresh)
        player_card = Card("Prestazioni individuali", "Punteggio cumulativo al termine di ogni turno.")
        player_card.body.addWidget(self.player_combo)
        self.performance_chart = LineChart()
        self.performance_chart.setMinimumHeight(245)
        player_card.body.addWidget(self.performance_chart)
        self.player_summary = ui_label("", "body", wrap=True)
        player_card.body.addWidget(self.player_summary)
        stats_row = QHBoxLayout()
        self.color_stats = StatTile("RISULTATI BIANCO / NERO", "chart")
        self.error_stats = StatTile("IMPRECISIONI · ERRORI · GRAVI", "info")
        self.time_stats = StatTile("TEMPO MEDIO PER MOSSA", "clock")
        for tile in (self.color_stats, self.error_stats, self.time_stats):
            stats_row.addWidget(tile, 1)
        player_card.body.addLayout(stats_row)
        self.player_detail = ui_label("", "muted", wrap=True)
        player_card.body.addWidget(self.player_detail)
        export = QPushButton("ESPORTA SCHEDA PERSONALE PDF")
        export.clicked.connect(lambda: self.app.export_player_report_pdf(self.player_combo.currentData()))
        player_card.body.addWidget(export, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(player_card)

        summary_card = Card("Report generale del torneo",
            "Statistiche calcolate sulle partite concluse e sui dati effettivamente disponibili.")
        self.tournament_summary_label = ui_label("", "body", wrap=True)
        summary_card.body.addWidget(self.tournament_summary_label)
        root.addWidget(summary_card)

        simulation = Card("Simulatore della classifica",
            "Modifica virtualmente i risultati delle partite ancora da disputare. Le modifiche restano temporanee e non vengono salvate.")
        self.simulation_hint = ui_label("", "muted", wrap=True)
        simulation.body.addWidget(self.simulation_hint)
        self.simulation_rows = QVBoxLayout()
        self.simulation_rows.setSpacing(6)
        simulation.body.addLayout(self.simulation_rows)
        self.simulation_table = QTableWidget(0, 4)
        self.simulation_table.setHorizontalHeaderLabels(["POS.", "GIOCATORE", "GIOCATE", "PUNTI NETTI"])
        self.simulation_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        style_table(self.simulation_table, row_height=38, selectable=False)
        simulation.body.addWidget(table_card(self.simulation_table))
        reset = QPushButton("AZZERA RISULTATI IPOTETICI")
        reset.clicked.connect(self.reset_simulation)
        simulation.body.addWidget(reset, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(simulation)
        self._build_simulation_controls()
        self.refresh()

    def _build_simulation_controls(self):
        for index, (gid, rnd, white, black) in enumerate(self.schedule):
            if self.app.results.get(gid) is not None:
                continue
            row = QHBoxLayout()
            row.addWidget(ui_label(f"R{rnd} · {self.player_name(white)} – {self.player_name(black)}", "body"), 1)
            combo = QComboBox()
            combo.addItem("Da simulare", None)
            combo.addItem(f"Vince {self.player_name(white)}", "1-0")
            combo.addItem("Patta", "1/2-1/2")
            combo.addItem(f"Vince {self.player_name(black)}", "0-1")
            combo.currentIndexChanged.connect(self.refresh_simulation)
            row.addWidget(combo)
            self.simulation_rows.addLayout(row)
            self.simulation_controls[gid] = combo

    def reset_simulation(self):
        for combo in self.simulation_controls.values():
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.refresh_simulation()

    def refresh(self):
        if not hasattr(self, "player_combo"):
            return
        player_id = self.player_combo.currentData()
        performance = player_performance(self.schedule, self.app.results, player_id)
        labels = [item[0] for item in performance]
        values = [item[1] for item in performance]
        color = self.player_color(self.player_order.index(player_id))
        self.performance_chart.set_data(labels, [(self.player_name(player_id), color, values)])
        current = self.app.player_profile_data(player_id)
        self.player_summary.setText(
            f"{self.player_name(player_id)} · {current['points']:.1f} punti netti · "
            f"{current['wins']} vittorie, {current['draws']} patte, {current['losses']} sconfitte."
        )
        colors = player_color_statistics(self.schedule, self.app.results, player_id)
        w, b = colors["white"], colors["black"]
        self.color_stats.set(
            f"{w['wins']}/{w['draws']}/{w['losses']} · {b['wins']}/{b['draws']}/{b['losses']}",
            "Bianco e Nero · vittorie / patte / sconfitte"
        )
        errors = player_error_statistics(self.schedule, self.app.move_reviews, player_id)
        ec = errors["counts"]
        self.error_stats.set(
            f"{ec['IMPRECISIONE']} · {ec['ERRORE']} · {ec['GRAVE ERRORE']}",
            f"{errors['reviewed_moves']} mosse analizzate"
        )
        timing = player_time_statistics(getattr(self.app, "move_times", {}), player_id)
        if timing["average_seconds"] is None:
            self.time_stats.set("N/D", "Nessuna mossa cronometrata raccolta")
            timing_text = "Tempi per mossa non disponibili per le partite precedenti all'attivazione della raccolta."
        else:
            self.time_stats.set(f"{timing['average_seconds']:.1f} s", f"{timing['moves']} mosse misurate")
            timing_text = (
                f"Mediana {timing['median_seconds']:.1f} s · tempo totale misurato "
                f"{timing['total_seconds']/60:.1f} minuti."
            )
        def pct(row, key):
            return "—" if row[key + "_pct"] is None else f"{row[key + '_pct']:.1f}%"
        self.player_detail.set(
            f"BIANCO: {pct(w, 'win')} vittorie · {pct(w, 'draw')} patte · {pct(w, 'loss')} sconfitte "
            f"({w['played']} partite).\n"
            f"NERO: {pct(b, 'win')} vittorie · {pct(b, 'draw')} patte · {pct(b, 'loss')} sconfitte "
            f"({b['played']} partite).\n"
            f"Errori: {ec['IMPRECISIONE']} imprecisioni, {ec['ERRORE']} errori, "
            f"{ec['GRAVE ERRORE']} gravi errori.\n{timing_text}"
        )
        summary = tournament_summary(
            self.schedule, self.app.results, self.app.moves, self.app.move_reviews,
            getattr(self.app, "move_times", {}), {gid: self.app.opening_name(gid) for gid, *_ in self.schedule},
            self.app.game_terminations
        )
        openings = ", ".join(f"{label} ({count})" for label, count in summary["openings"][:6]) or "Non ancora disponibili"
        endings = ", ".join(f"{label} ({count})" for label, count in summary["endings"]) or "Non disponibili"
        avg_time = "N/D" if summary["average_move_seconds"] is None else f"{summary['average_move_seconds']:.1f} secondi"
        avg_game = "N/D" if summary["average_game_duration_seconds"] is None else f"{summary['average_game_duration_seconds']/60:.1f} minuti"
        self.tournament_summary_label.setText(
            f"Partite concluse: {summary['completed']}/{len(self.schedule)}.\n"
            f"Aperture più giocate: {openings}.\n"
            f"Tipi di conclusione: {endings}.\n"
            f"Precisione: {summary['reviewed_moves']} mosse analizzate · "
            f"{summary['errors']['IMPRECISIONE']} imprecisioni · {summary['errors']['ERRORE']} errori · "
            f"{summary['errors']['GRAVE ERRORE']} gravi errori.\n"
            f"Tempo medio per mossa: {avg_time} ({summary['timed_moves']} mosse cronometrate).\\n"
            f"Durata media misurata delle partite: {avg_game} ({summary['games_with_timing']} partite con tempi disponibili)."
        )
        self.refresh_simulation()

    def refresh_simulation(self):
        hypothetical = dict(self.app.results)
        for gid, combo in self.simulation_controls.items():
            value = combo.currentData()
            if value:
                hypothetical[gid] = value
            else:
                hypothetical.pop(gid, None)
        rows = simulate_standings(
            self.schedule, hypothetical, self.app.penalty_points(), self.player_order
        )
        self.simulation_table.setRowCount(len(rows))
        for index, item in enumerate(rows, 1):
            values = [str(index), self.player_name(item["id"]), str(item["played"]), f"{item['points']:.1f}"]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column != 1:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.simulation_table.setItem(index - 1, column, cell)
        changed = sum(1 for combo in self.simulation_controls.values() if combo.currentData())
        self.simulation_hint.setText(
            f"{changed} risultati ipotetici impostati. Nessun risultato ufficiale viene modificato."
        )
