"""Historical edition archive and cross-edition statistics for C5R Windows."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .c5r_storage import atomic_write_json, decode_document


def _score(result: str, player: str, white: str, black: str) -> float:
    if result == "1-0":
        return 1.0 if player == white else 0.0
    if result == "0-1":
        return 1.0 if player == black else 0.0
    if result == "1/2-1/2":
        return 0.5
    return 0.0


def historical_standings(state: dict[str, Any], player_order: list[str]) -> list[dict[str, Any]]:
    schedule = state.get("schedule", [])
    results = state.get("results", {})
    penalties = {player: 0.0 for player in player_order}
    for penalty in state.get("penalties", []):
        player = penalty.get("player")
        if player in penalties:
            try:
                penalties[player] += float(penalty.get("points", 0))
            except (TypeError, ValueError):
                continue
    raw = {player: 0.0 for player in player_order}
    played = {player: 0 for player in player_order}
    wins = {player: 0 for player in player_order}
    draws = {player: 0 for player in player_order}
    losses = {player: 0 for player in player_order}
    valid_games = []
    for item in schedule:
        if not isinstance(item, dict):
            continue
        gid, white, black = item.get("id"), item.get("white"), item.get("black")
        result = results.get(gid)
        if white not in raw or black not in raw or white == black or result not in ("1-0", "0-1", "1/2-1/2"):
            continue
        valid_games.append((gid, white, black, result))
        played[white] += 1
        played[black] += 1
        raw[white] += _score(result, white, white, black)
        raw[black] += _score(result, black, white, black)
        if result == "1-0":
            wins[white] += 1
            losses[black] += 1
        elif result == "0-1":
            wins[black] += 1
            losses[white] += 1
        else:
            draws[white] += 1
            draws[black] += 1

    total = {player: raw[player] + penalties[player] for player in player_order}

    def tie_key(player: str, group: list[str]) -> tuple[float, float, int]:
        direct = 0.0
        if len(group) == 2:
            opponent = next((candidate for candidate in group if candidate != player), None)
            for _, white, black, result in valid_games:
                if {white, black} != {player, opponent}:
                    continue
                direct = _score(result, player, white, black)
                break
        sonneborn = 0.0
        for _, white, black, result in valid_games:
            if player not in (white, black):
                continue
            opponent = black if player == white else white
            sonneborn += total[opponent] * _score(result, player, white, black)
        return direct, sonneborn, wins[player]

    grouped: dict[float, list[str]] = {}
    for player in player_order:
        grouped.setdefault(total[player], []).append(player)
    ordered: list[str] = []
    for points in sorted(grouped, reverse=True):
        group = grouped[points]
        group.sort(key=lambda player: (tuple(-value for value in tie_key(player, group)), player_order.index(player)))
        ordered.extend(group)

    return [
        {
            "id": player, "played": played[player], "wins": wins[player],
            "draws": draws[player], "losses": losses[player],
            "raw_points": raw[player], "penalty": penalties[player],
            "points": total[player],
        }
        for player in ordered
    ]


def _result_winner(result: str | None, pair: tuple[str | None, str | None], armageddon: str | None) -> str | None:
    if not all(pair):
        return None
    if result == "1-0":
        return pair[0]
    if result == "0-1":
        return pair[1]
    if result == "1/2-1/2" and armageddon in pair:
        return armageddon
    return None


def historical_podium(state: dict[str, Any], standings: list[dict[str, Any]]) -> list[str | None]:
    ranking = [row["id"] for row in standings]
    if len(ranking) < 4:
        return [None, None, None, None]
    results = state.get("playoff_results", {})
    armageddon = state.get("playoff_winners", {})
    sf1 = (ranking[0], ranking[3])
    sf2 = (ranking[1], ranking[2])
    w1 = _result_winner(results.get("sf1"), sf1, armageddon.get("sf1"))
    w2 = _result_winner(results.get("sf2"), sf2, armageddon.get("sf2"))
    l1 = next((p for p in sf1 if p and p != w1), None) if w1 else None
    l2 = next((p for p in sf2 if p and p != w2), None) if w2 else None
    final_pair = (w1, w2)
    third_pair = (l1, l2)
    champion = _result_winner(results.get("final"), final_pair, armageddon.get("final"))
    bronze = _result_winner(results.get("third"), third_pair, armageddon.get("third"))
    if champion is None:
        return [None, None, None, None]
    runner_up = next((p for p in final_pair if p and p != champion), None)
    fourth = next((p for p in third_pair if p and p != bronze), None) if bronze else None
    return [champion, runner_up, bronze, fourth]


def edition_summary(record: dict[str, Any], player_order: list[str]) -> dict[str, Any]:
    state = record.get("state", {})
    standings = historical_standings(state, player_order)
    podium = historical_podium(state, standings)
    schedule = state.get("schedule", [])
    results = state.get("results", {})
    completed = sum(1 for item in schedule if results.get(item.get("id")) in ("1-0", "0-1", "1/2-1/2"))
    voided = sum(1 for item in schedule if results.get(item.get("id")) == "VOID")
    names = record.get("edition", {}).get("player_names", {})
    player_rows = {}
    for row in standings:
        player_rows[row["id"]] = dict(row, name=names.get(row["id"], row["id"]))
    return {
        "path": record.get("_path"),
        "id": record.get("edition", {}).get("id", ""),
        "title": record.get("edition", {}).get("title", "Edizione senza titolo"),
        "created_at": record.get("edition", {}).get("created_at", ""),
        "referee": record.get("edition", {}).get("referee", ""),
        "standings": standings, "podium": podium, "champion": podium[0],
        "completed": completed, "voided": voided,
        "player_rows": player_rows,
        "players": len({player for item in schedule for player in (item.get("white"), item.get("black"))}),
        "is_complete": completed + voided == len(schedule) and podium[0] is not None,
    }


def archive_directory(storage_file: str | Path) -> Path:
    folder = Path(storage_file).parent / "editions"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def archive_edition(
    storage_file: str | Path, state: dict[str, Any], title: str,
    player_order: list[str], player_names: dict[str, str],
    created_at: str | None = None,
) -> Path:
    title = str(title).strip()
    if not title:
        raise ValueError("Inserisci il nome dell'edizione.")
    schedule = state.get("schedule")
    if not isinstance(schedule, list) or not schedule:
        raise ValueError("Il torneo non contiene un calendario valido.")
    created = created_at or datetime.now().isoformat(timespec="seconds")
    fingerprint = hashlib.sha256(
        json.dumps(state, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:10]
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:32] or "edizione"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    edition_id = f"{stamp}_{slug}_{fingerprint}"
    record = {
        "edition": {
            "id": edition_id, "title": title, "created_at": created,
            "referee": state.get("referee", ""),
            "player_names": {player: player_names.get(player, player) for player in player_order},
        },
        "state": state,
    }
    target = archive_directory(storage_file) / f"{edition_id}.json"
    atomic_write_json(target, record)
    return target


def import_edition_file(
    storage_file: str | Path, source_file: str | Path, title: str,
    player_order: list[str], player_names: dict[str, str],
) -> Path:
    raw = json.loads(Path(source_file).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("_c5r_snapshot"), dict) and isinstance(raw.get("state"), dict):
        state = decode_document(raw["state"])
    elif isinstance(raw, dict) and isinstance(raw.get("edition"), dict) and isinstance(raw.get("state"), dict):
        state = decode_document(raw["state"])
    else:
        state = decode_document(raw)
    return archive_edition(storage_file, state, title, player_order, player_names)


def list_editions(storage_file: str | Path, player_order: list[str]) -> list[dict[str, Any]]:
    folder = archive_directory(storage_file)
    records = []
    for path in folder.glob("*.json"):
        try:
            payload = decode_document(json.loads(path.read_text(encoding="utf-8")))
            if not isinstance(payload.get("edition"), dict) or not isinstance(payload.get("state"), dict):
                continue
            payload["_path"] = str(path)
            records.append(edition_summary(payload, player_order))
        except Exception:
            continue
    return sorted(records, key=lambda item: str(item.get("created_at", "")), reverse=True)


def career_statistics(
    editions: list[dict[str, Any]], player_order: list[str], player_names: dict[str, str]
) -> list[dict[str, Any]]:
    totals = {
        player: {"id": player, "name": player_names.get(player, player), "editions": 0,
                 "titles": 0, "podiums": 0, "best": None, "played": 0,
                 "wins": 0, "draws": 0, "losses": 0, "points": 0.0}
        for player in player_order
    }
    for edition in editions:
        for index, player in enumerate(edition.get("podium", [])):
            if player in totals:
                place = index + 1
                totals[player]["best"] = place if totals[player]["best"] is None else min(totals[player]["best"], place)
                if place == 1:
                    totals[player]["titles"] += 1
                if place <= 3:
                    totals[player]["podiums"] += 1
        for player, row in edition.get("player_rows", {}).items():
            if player not in totals:
                continue
            stats = totals[player]
            if row.get("played", 0) > 0:
                stats["editions"] += 1
            for key in ("played", "wins", "draws", "losses"):
                stats[key] += int(row.get(key, 0))
            stats["points"] += float(row.get("points", 0.0))
    return sorted(totals.values(), key=lambda row: (
        -row["titles"], -row["podiums"], -row["editions"], -row["points"],
        row["best"] if row["best"] is not None else 99, player_order.index(row["id"])
    ))
