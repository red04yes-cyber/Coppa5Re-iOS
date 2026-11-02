"""Pure analytics helpers for Coppa5Re Windows.

All functions are read-only: simulated results never mutate tournament state.
"""
from __future__ import annotations

from collections import Counter
from typing import Any


VALID_RESULTS = {"1-0", "0-1", "1/2-1/2"}


def player_performance(schedule, results, player_id):
    """Cumulative score after each round, ignoring unfinished/void games."""
    rounds = sorted({int(item[1]) for item in schedule})
    score = 0.0
    output = []
    for round_no in rounds:
        for gid, rnd, white, black in schedule:
            if int(rnd) != round_no or player_id not in (white, black):
                continue
            result = results.get(gid)
            if result not in VALID_RESULTS:
                continue
            if result == "1/2-1/2":
                score += 0.5
            elif (result == "1-0" and player_id == white) or (result == "0-1" and player_id == black):
                score += 1.0
        output.append((f"R{round_no}", score))
    return output


def player_color_statistics(schedule, results, player_id):
    data = {
        "white": {"wins": 0, "draws": 0, "losses": 0, "played": 0},
        "black": {"wins": 0, "draws": 0, "losses": 0, "played": 0},
    }
    for gid, _rnd, white, black in schedule:
        if player_id not in (white, black):
            continue
        result = results.get(gid)
        if result not in VALID_RESULTS:
            continue
        color = "white" if player_id == white else "black"
        row = data[color]
        row["played"] += 1
        if result == "1/2-1/2":
            row["draws"] += 1
        elif (result == "1-0" and color == "white") or (result == "0-1" and color == "black"):
            row["wins"] += 1
        else:
            row["losses"] += 1
    for row in data.values():
        row["win_pct"] = 100.0 * row["wins"] / row["played"] if row["played"] else None
        row["draw_pct"] = 100.0 * row["draws"] / row["played"] if row["played"] else None
        row["loss_pct"] = 100.0 * row["losses"] / row["played"] if row["played"] else None
    return data


def player_error_statistics(schedule, reviews, player_id):
    game_players = {gid: (white, black) for gid, _rnd, white, black in schedule}
    labels = ("IMPRECISIONE", "ERRORE", "GRAVE ERRORE")
    counts = {label: 0 for label in labels}
    total = 0
    for gid, entries in reviews.items():
        pair = game_players.get(gid)
        if not pair or player_id not in pair:
            continue
        for item in entries if isinstance(entries, list) else []:
            if item.get("player") != player_id:
                continue
            label = str(item.get("label", "")).upper()
            if label in counts:
                counts[label] += 1
            total += 1
    return {"counts": counts, "reviewed_moves": total}


def player_time_statistics(move_times, player_id):
    samples = []
    for entries in move_times.values():
        if not isinstance(entries, list):
            continue
        for item in entries:
            if item.get("player") != player_id:
                continue
            try:
                seconds = float(item.get("seconds"))
            except (TypeError, ValueError):
                continue
            if seconds >= 0:
                samples.append(seconds)
    if not samples:
        return {"moves": 0, "average_seconds": None, "median_seconds": None, "total_seconds": 0.0}
    ordered = sorted(samples)
    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return {
        "moves": len(samples),
        "average_seconds": sum(samples) / len(samples),
        "median_seconds": median,
        "total_seconds": sum(samples),
    }


def tournament_error_statistics(schedule, reviews):
    players = {player for _gid, _rnd, white, black in schedule for player in (white, black)}
    return {
        player: player_error_statistics(schedule, reviews, player)
        for player in players
    }


def simulate_standings(schedule, results, penalties, player_order):
    """Return a provisional ranking using points, head-to-head (two-way ties),
    Sonneborn-Berger and wins, matching the tournament tie-break order.
    """
    points = {player: 0.0 for player in player_order}
    wins = {player: 0 for player in player_order}
    played_games = []
    for gid, _rnd, white, black in schedule:
        result = results.get(gid)
        if white not in points or black not in points or result not in VALID_RESULTS:
            continue
        played_games.append((gid, white, black, result))
        if result == "1-0":
            points[white] += 1.0
            wins[white] += 1
        elif result == "0-1":
            points[black] += 1.0
            wins[black] += 1
        else:
            points[white] += 0.5
            points[black] += 0.5
    net = {p: points[p] + float(penalties.get(p, 0.0)) for p in player_order}

    def score_for(result, player, white, black):
        if result == "1/2-1/2":
            return 0.5
        return 1.0 if (result == "1-0" and player == white) or (result == "0-1" and player == black) else 0.0

    def tie_key(player, group):
        direct = 0.0
        if len(group) == 2:
            opponent = next(p for p in group if p != player)
            for _gid, white, black, result in played_games:
                if {white, black} == {player, opponent}:
                    direct += score_for(result, player, white, black)
        sonneborn = 0.0
        for _gid, white, black, result in played_games:
            if player in (white, black):
                opponent = black if player == white else white
                sonneborn += net[opponent] * score_for(result, player, white, black)
        return direct, sonneborn, wins[player]

    groups = {}
    for player in player_order:
        groups.setdefault(net[player], []).append(player)
    ordered = []
    for value in sorted(groups, reverse=True):
        group = groups[value]
        group.sort(key=lambda p: (tuple(-x for x in tie_key(p, group)), player_order.index(p)))
        ordered.extend(group)
    return [
        {"id": player, "points": net[player], "wins": wins[player],
         "played": sum(1 for _gid, white, black, _r in played_games if player in (white, black))}
        for player in ordered
    ]


def tournament_summary(schedule, results, moves, move_reviews, move_times, openings, terminations):
    completed = [(gid, rnd, white, black, results.get(gid)) for gid, rnd, white, black in schedule
                 if results.get(gid) in VALID_RESULTS]
    opening_counts = Counter()
    for gid, _rnd, _white, _black, _result in completed:
        if moves.get(gid):
            opening_counts[openings.get(gid, "Non classificata")] += 1
    endings = Counter()
    for gid, _rnd, _white, _black, result in completed:
        detail = terminations.get(gid, {})
        label = detail.get("detail") if isinstance(detail, dict) else detail
        if not label:
            label = "Patta" if result == "1/2-1/2" else "Altro risultato"
        endings[str(label)] += 1
    durations = []
    for entries in move_times.values():
        if isinstance(entries, list):
            for item in entries:
                try:
                    value = float(item.get("seconds"))
                    if value >= 0:
                        durations.append(value)
                except (TypeError, ValueError):
                    pass
    reviews = [item for entries in move_reviews.values() if isinstance(entries, list) for item in entries]
    error_counts = Counter(str(item.get("label", "")).upper() for item in reviews)
    game_durations = []
    for gid, _rnd, _white, _black, _result in completed:
        game_samples = []
        for item in move_times.get(gid, []) if isinstance(move_times.get(gid, []), list) else []:
            try:
                value = float(item.get("seconds"))
                if value >= 0:
                    game_samples.append(value)
            except (TypeError, ValueError):
                pass
        if game_samples:
            game_durations.append(sum(game_samples))
    return {
        "completed": len(completed),
        "openings": opening_counts.most_common(),
        "endings": endings.most_common(),
        "reviewed_moves": len(reviews),
        "errors": {key: error_counts.get(key, 0) for key in ("IMPRECISIONE", "ERRORE", "GRAVE ERRORE")},
        "timed_moves": len(durations),
        "average_move_seconds": sum(durations) / len(durations) if durations else None,
        "average_game_duration_seconds": sum(game_durations) / len(game_durations) if game_durations else None,
        "games_with_timing": len(game_durations),
        "average_game_moves": (sum(len(moves.get(gid, [])) for gid, *_ in completed) / len(completed)) if completed else None,
    }
