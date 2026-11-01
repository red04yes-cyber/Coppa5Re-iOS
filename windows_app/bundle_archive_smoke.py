from pathlib import Path
import sys

from PyInstaller.archive.readers import CArchiveReader

exe = Path("dist/Coppa5Re.exe")
assert exe.is_file(), f"Windows EXE not found: {exe}"
archive = CArchiveReader(str(exe))
names = list(archive.toc.keys())
engine_name = next((n for n in names if n.replace("\\", "/").lower().endswith("stockfish/stockfish.exe")), None)
logo_name = next((n for n in names if n.replace("\\", "/").lower().endswith("assets/c5r-logo.svg")), None)
assert engine_name, "Stockfish executable is not embedded in Coppa5Re.exe"
assert logo_name, "C5R tournament logo is not embedded in Coppa5Re.exe"
engine_data = archive.extract(engine_name)
logo_data = archive.extract(logo_name)
assert len(engine_data) > 10_000_000, f"Unexpected Stockfish payload size: {len(engine_data)}"
assert b"<svg" in logo_data[:4096].lower(), "Embedded C5R logo is not a valid SVG payload"
print(f"One-file EXE resources OK: {engine_name} ({len(engine_data)} bytes), {logo_name} ({len(logo_data)} bytes)")
