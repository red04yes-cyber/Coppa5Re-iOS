"""Regression checks for the Windows analytics helpers and page wiring."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="c5r-analytics-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from windows_app.c5r_analytics import (
    player_performance, player_color_statistics, player_error_statistics,
    player_time_statistics, simulate_standings, tournament_summary,
)
from windows_app.main import MainWindow

schedule = [
    ("g1", 1, "a", "b"),
    ("g2", 2, "b", "a"),
    ("g3", 3, "a", "b"),
]
results = {"g1": "1-0", "g2": "0-1", "g3": "1/2-1/2"}
assert player_performance(schedule, results, "a") == [("R1", 1.0), ("R2", 2.0), ("R3", 2.5)]
colors = player_color_statistics(schedule, results, "a")
assert colors["white"]["wins"] == 1 and colors["white"]["draws"] == 1
assert colors["black"]["wins"] == 1 and colors["black"]["win_pct"] == 100.0

reviews = {"g1": [
    {"player": "a", "label": "IMPRECISIONE"},
    {"player": "b", "label": "ERRORE"},
    {"player": "a", "label": "GRAVE ERRORE"},
]}
errors = player_error_statistics(schedule, reviews, "a")
assert errors["reviewed_moves"] == 2 and errors["counts"]["GRAVE ERRORE"] == 1
times = {"g1": [{"player": "a", "seconds": 4}, {"player": "b", "seconds": 6}],
         "g2": [{"player": "a", "seconds": 8}]}
timing = player_time_statistics(times, "a")
assert timing["moves"] == 2 and timing["average_seconds"] == 6 and timing["median_seconds"] == 6

ranking = simulate_standings(schedule, results, {"a": 0, "b": 0}, ["a", "b"])
assert ranking[0]["id"] == "a" and ranking[0]["points"] == 2.5
summary = tournament_summary(
    schedule, results, {"g1": ["e2e4"], "g2": ["e2e4"], "g3": ["d2d4"]},
    reviews, times, {"g1": "Italiana", "g2": "Siciliana", "g3": "Francese"}, {}
)
assert summary["completed"] == 3 and summary["timed_moves"] == 3
assert summary["average_move_seconds"] == 6

app = QApplication([])
window = MainWindow()
assert "analytics" in window._page_keys
analytics_index = window._page_keys.index("analytics")
analytics_page = window.tabs.widget(analytics_index).widget()
assert analytics_page.simulation_table.rowCount() == 5
assert analytics_page.error_table.rowCount() == 5

# Full elapsed thinking time is measured from the start of the player's turn,
# not merely the final one-second clock refresh interval.
window.engine_enabled = False
window.results = {}
window.moves = {}
window.boards.clear()
window.clocks.clear()
window.move_times = {}
window.start_clock("R1-M1")
window.clock_data("R1-M1")["turn_started_at"] = time.time() - 2.5
window.record_move("R1-M1", "e2e4")
record = window.move_times["R1-M1"][0]
assert record["player"] == "jacopo" and record["seconds"] >= 2.4
window.close()
print("C5R Windows analytics OK: performance, colors, errors, move timing, report summaries, hypothetical standings and PDF page wiring.")
