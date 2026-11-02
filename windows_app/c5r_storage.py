"""Robust local JSON persistence for Coppa dei 5 Re (Windows edition)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 5


class StorageIntegrityError(ValueError):
    """Raised when the saved tournament file fails its integrity check."""


def _canonical(data: dict[str, Any]) -> bytes:
    payload = {key: value for key, value in data.items() if key != "_c5r_meta"}
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def seal_document(data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data)
    payload.pop("_c5r_meta", None)
    payload["_c5r_meta"] = {
        "schema_version": SCHEMA_VERSION,
        "sha256": hashlib.sha256(_canonical(payload)).hexdigest(),
    }
    return payload


def decode_document(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise StorageIntegrityError("Il contenuto JSON non è un oggetto.")
    payload = dict(raw)
    meta = payload.pop("_c5r_meta", None)
    if meta is not None:
        if not isinstance(meta, dict):
            raise StorageIntegrityError("Metadati di integrità non validi.")
        version = int(meta.get("schema_version", 1))
        if version > SCHEMA_VERSION:
            raise StorageIntegrityError(
                f"Il file usa uno schema più recente ({version}) di quello supportato ({SCHEMA_VERSION})."
            )
        expected = str(meta.get("sha256", ""))
        actual = hashlib.sha256(_canonical(payload)).hexdigest()
        if not expected or not hmac.compare_digest(expected, actual):
            raise StorageIntegrityError("Il controllo SHA-256 non corrisponde: il file potrebbe essere danneggiato.")
    # Migrazioni additive: i file delle versioni precedenti restano leggibili.
    defaults = {
        "results": {}, "penalties": [], "moves": {}, "clocks": {}, "move_times": {},
        "audit_log": [], "match_notes": {}, "playoff_results": {},
        "playoff_winners": {}, "eval_history": {}, "game_terminations": {},
        "move_reviews": {}, "withdrawn_players": {}, "move_annotations": {},
        "round_closures": {}, "ui_preferences": {},
        "ui_profiles": {}, "incident_reports": [], "player_bios": {}, "notification_drafts": [],
    }
    for key, value in defaults.items():
        payload.setdefault(key, value.copy() if isinstance(value, (dict, list)) else value)
    if not isinstance(payload.get("results"), dict) or not isinstance(payload.get("clocks"), dict):
        raise StorageIntegrityError("La struttura dei risultati o dei cronometri non è valida.")
    return payload


def read_document(path: str | Path) -> tuple[dict[str, Any], Path | None]:
    source = Path(path)
    candidates = [source, source.with_suffix(source.suffix + ".bak"),
                  source.with_suffix(source.suffix + ".bak.1")]
    errors: list[str] = []
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
            return decode_document(raw), (candidate if candidate != source else None)
        except Exception as exc:
            errors.append(f"{candidate.name}: {exc}")
    if errors:
        raise StorageIntegrityError("Nessuna copia integra disponibile. " + " | ".join(errors))
    raise FileNotFoundError(source)


def atomic_write_json(path: str | Path, data: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_suffix(target.suffix + ".bak")
    backup_old = target.with_suffix(target.suffix + ".bak.1")
    if target.exists():
        try:
            if backup.exists():
                shutil.copy2(backup, backup_old)
            shutil.copy2(target, backup)
        except OSError:
            # Il salvataggio principale rimane prioritario rispetto alla rotazione.
            pass
    sealed = seal_document(data)
    temporary = target.with_suffix(target.suffix + ".tmp")
    encoded = json.dumps(sealed, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
