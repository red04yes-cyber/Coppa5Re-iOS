"""End-to-end regression for Windows public portal, protected QR links, referee alerts and final package."""
from pathlib import Path
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APPDATA = tempfile.mkdtemp(prefix="c5r-public-portal-")
os.environ["APPDATA"] = APPDATA
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import chess
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from windows_app.main import MainWindow, GAMES

app = QApplication([])
window = MainWindow()
server = None
old_get_save = QFileDialog.getSaveFileName
old_critical = QMessageBox.critical
output = Path(tempfile.mkdtemp(prefix="c5r-final-package-test-"))
try:
    # One match state powers the board, clocks, move list, portal cards and APIs.
    gid = "R1-M1"
    board = chess.Board()
    for uci in ("e2e4", "e7e5"):
        board.push_uci(uci)
    window.moves[gid] = [move.uci() for move in board.move_stack]
    window.boards[gid] = board
    window.clocks[gid] = {
        "white": 600, "black": 500, "started": True,
        "last_wall": time.time() - 3.0, "side_to_move": "white",
    }
    state = window.match_web_state(gid)
    assert state["fen"] == board.fen()
    assert state["last_move"] == "e7e5"
    assert state["move_text"] == "1. e4 e5"
    assert state["clock_running"] is True
    assert state["clock_white"] <= 597
    assert state["clock_turn"] == "white"

    portal = window.public_portal_state()
    assert len(portal["matches"]) == len(GAMES) + 4
    assert len(portal["standings"]) == 5
    assert any(item["game_id"] == gid for item in portal["matches"])
    portal_html = window.portal_web_html()
    assert "TUTTI I TAVOLI" in portal_html
    assert "CLASSIFICA LIVE" in portal_html
    assert "/api/portal?token=" in portal_html
    assert "setInterval(poll,1000)" in portal_html

    # HTTPS base URL produces remote links with the same protected token.
    window.public_base_url = "https://spectator.example.invalid"
    window.spectator_token = "unit-test-random-viewer-token"
    host, port = window.start_match_web_server("127.0.0.1")
    server = window.match_http_server
    public_portal_url = window.portal_web_url(public=True)
    public_match_url = window.match_web_url(gid, public=True)
    assert public_portal_url.startswith("https://spectator.example.invalid/portal?token=")
    assert public_match_url.startswith("https://spectator.example.invalid/match/R1-M1?token=")
    assert window.portal_web_url().startswith("http://127.0.0.1:")
    assert window.valid_spectator_token("unit-test-random-viewer-token")
    assert not window.valid_spectator_token("wrong-token")

    # The HTTP server rejects missing/incorrect tokens and serves the portal and live JSON to valid viewers.
    base = f"http://127.0.0.1:{port}"
    try:
        urllib.request.urlopen(base + "/portal", timeout=5)
        raise AssertionError("Portal without token unexpectedly accepted")
    except urllib.error.HTTPError as exc:
        assert exc.code == 403
    query = "?token=unit-test-random-viewer-token"
    with urllib.request.urlopen(base + "/portal" + query, timeout=5) as response:
        page = response.read().decode("utf-8")
        assert response.status == 200 and "CLASSIFICA LIVE" in page
    with urllib.request.urlopen(base + "/api/portal" + query, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
        assert len(payload["matches"]) >= 14 and len(payload["standings"]) == 5
    with urllib.request.urlopen(base + "/api/match/" + gid + query, timeout=5) as response:
        match_payload = json.loads(response.read().decode("utf-8"))
        assert match_payload["fen"] == board.fen()
        assert match_payload["last_move"] == "e7e5"
    with urllib.request.urlopen(base + "/match/" + gid + query, timeout=5) as response:
        match_page = response.read().decode("utf-8")
        assert "SCACCHIERA LIVE" in match_page and "token=" in match_page

    # Public URL generation is independent of the operator's local address; no live tunnel is required in this test.
    window.public_base_url = ""

    # Long-duration and result-review notices are generated for arbiters and persist until acknowledged.
    window.long_match_minutes = 30
    window.clocks[gid].update({
        "started": True, "started_at": time.time() - 31 * 60,
        "last_wall": time.time(), "overlong_alerted": False,
    })
    window.check_long_match_alerts()
    assert any("oltre la durata" in item["title"] for item in window.operational_alerts)
    window.set_result(gid, "1-0", confirm=False, detail="Risultato di prova")
    result_alert = next(item for item in window.operational_alerts if item["source_key"].startswith("result:"))
    assert result_alert["acknowledged"] is False
    window.acknowledge_operational_alert(result_alert["id"])
    assert result_alert["acknowledged"] is True

    # The PDF and the one-click ZIP package both contain the final tournament report and PGNs.
    pdf_path = output / "Report-test.pdf"
    assert window.export_tournament_report_pdf(str(pdf_path), announce=False) == str(pdf_path)
    assert pdf_path.exists() and pdf_path.stat().st_size > 500
    zip_path = output / "Pacchetto-Finale-C5R.zip"
    QFileDialog.getSaveFileName = staticmethod(lambda *args, **kwargs: (str(zip_path), ""))
    QMessageBox.critical = staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(str(args))))
    window.export_final_report_package()
    assert zip_path.exists() and zip_path.stat().st_size > 500
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        assert "Report-Ufficiale-C5R.pdf" in names
        assert "Classifica.csv" in names
        assert "Registro-arbitrale.csv" in names
        assert "Riepilogo.json" in names
        assert "PGN/R1-M1.pgn" in names
        summary = json.loads(archive.read("Riepilogo.json").decode("utf-8"))
        assert summary["tournament"] == "Coppa dei 5 Re"
finally:
    QFileDialog.getSaveFileName = old_get_save
    QMessageBox.critical = old_critical
    if server is not None:
        server.shutdown()
        server.server_close()
        window.match_http_server = None
    window.close()

print("Windows public portal, protected remote QR, live clocks, referee alerts and final report package OK")
