"""Phase 3 season-versioned autosub, chip cohort and fixture ticker services.

No network I/O. Inputs must come from timestamped official FPL public snapshots.
Rules are explicit season inputs; this module does not silently assume a season's
chip catalogue or substitution policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .current_data import (
    assert_future_gameweeks,
    assert_gameweeks_have_fixtures,
    build_fixture_map,
    normalize_fixtures,
    planning_horizon,
)


class RuleInputError(ValueError):
    """Missing or invalid season rule / match-state input."""


@dataclass(frozen=True)
class SeasonRules:
    season: str
    rules_version: str
    rules_status: str = "UNVERIFIED_CONFIGURATION"
    min_defenders: int = 3
    min_midfielders: int = 2
    min_forwards: int = 1
    max_defenders: int = 5
    max_midfielders: int = 5
    max_forwards: int = 3
    captain_multiplier: int = 2
    triple_captain_multiplier: int = 3
    bench_boost_chip: str = "bboost"
    triple_captain_chip: str = "3xc"

    def __post_init__(self) -> None:
        if not self.season.strip() or not self.rules_version.strip() or not self.rules_status.strip():
            raise RuleInputError("season and rules_version are required")
        if self.min_defenders < 3 or self.min_midfielders < 2 or self.min_forwards < 1:
            raise RuleInputError("FPL outfield minimums cannot be lower than 3 DEF / 2 MID / 1 FWD")
        if self.max_defenders < self.min_defenders or self.max_midfielders < self.min_midfielders or self.max_forwards < self.min_forwards:
            raise RuleInputError("position maxima must be >= minima")
        if self.captain_multiplier < 1 or self.triple_captain_multiplier < self.captain_multiplier:
            raise RuleInputError("invalid captain multipliers")


def _formation_counts(player_ids: Sequence[int], positions: Mapping[int, str]) -> Dict[str, int]:
    counts = {"DEF": 0, "MID": 0, "FWD": 0}
    for pid in player_ids:
        pos = positions.get(pid)
        if pos not in counts:
            raise RuleInputError(f"unknown outfield position for player {pid}: {pos!r}")
        counts[pos] += 1
    return counts


def _legal_formation(player_ids: Sequence[int], positions: Mapping[int, str], rules: SeasonRules) -> bool:
    if len(player_ids) != 10:
        return False
    c = _formation_counts(player_ids, positions)
    return (
        rules.min_defenders <= c["DEF"] <= rules.max_defenders
        and rules.min_midfielders <= c["MID"] <= rules.max_midfielders
        and rules.min_forwards <= c["FWD"] <= rules.max_forwards
    )


def simulate_autosubs(
    picks: Sequence[Mapping[str, Any]],
    minutes_by_player: Mapping[int, float],
    positions_by_player: Mapping[int, str],
    rules: SeasonRules,
    *,
    active_chip: Optional[str] = None,
) -> Dict[str, Any]:
    """Simulate legal substitutions and captain fallback for one completed GW.

    Picks must be the 15 official pick rows with positions 1..15. Player
    positions must come from the same season's official bootstrap. Missing
    minutes/position data fails closed. Bench outfield entries are processed
    in bench order; each only replaces a non-playing starter if formation stays
    legal. The rules object versions all season-sensitive behavior.
    """
    if len(picks) != 15:
        raise RuleInputError("exactly 15 official picks are required")
    rows = sorted(picks, key=lambda p: int(p.get("position", 0)))
    slot_positions = [int(p.get("position", 0)) for p in rows]
    if slot_positions != list(range(1, 16)):
        raise RuleInputError("pick positions must be unique and cover 1..15")
    ids = [int(p["element"]) for p in rows]
    if len(set(ids)) != 15:
        raise RuleInputError("duplicate player id in picks")
    missing_minutes = set(ids) - set(int(k) for k in minutes_by_player)
    missing_positions = set(ids) - set(int(k) for k in positions_by_player)
    if missing_minutes:
        raise RuleInputError(f"missing minutes for player ids: {sorted(missing_minutes)}")
    if missing_positions:
        raise RuleInputError(f"missing position for player ids: {sorted(missing_positions)}")

    pos = {int(k): str(v).upper() for k, v in positions_by_player.items()}
    if any(not isinstance(minutes_by_player[pid], (int, float)) or minutes_by_player[pid] < 0 for pid in ids):
        raise RuleInputError("minutes must be non-negative numbers")
    starters = [int(p["element"]) for p in rows[:11]]
    bench = [int(p["element"]) for p in rows[11:]]
    if pos[starters[0]] != "GKP":
        raise RuleInputError("starting goalkeeper must occupy pick position 1")
    if sum(pos[pid] == "GKP" for pid in starters) != 1:
        raise RuleInputError("starting XI must contain exactly one goalkeeper")
    if sum(pos[pid] == "GKP" for pid in bench) != 1:
        raise RuleInputError("bench must contain exactly one goalkeeper")
    if not _legal_formation(starters[1:], pos, rules):
        raise RuleInputError("starting XI formation is illegal under supplied season rules")

    captain_rows = [p for p in rows if p.get("is_captain")]
    vice_rows = [p for p in rows if p.get("is_vice_captain")]
    if len(captain_rows) != 1 or len(vice_rows) != 1:
        raise RuleInputError("exactly one captain and one vice-captain are required")
    captain_id, vice_id = int(captain_rows[0]["element"]), int(vice_rows[0]["element"])
    if captain_id == vice_id or captain_id not in starters or vice_id not in starters:
        raise RuleInputError("captain and vice-captain must be distinct starters")

    played = {pid for pid in ids if float(minutes_by_player[pid]) > 0}
    no_show = [pid for pid in starters if pid not in played]
    substitutions: List[Dict[str, int]] = []

    starting_gk = starters[0]
    bench_gks = [pid for pid in bench if pos[pid] == "GKP"]
    if starting_gk not in played and bench_gks and bench_gks[0] in played:
        replacement = bench_gks[0]
        starters[0] = replacement
        substitutions.append({"out": starting_gk, "in": replacement, "kind": "goalkeeper"})
        no_show.remove(starting_gk)

    outfield_bench = [pid for pid in bench if pos[pid] != "GKP"]
    for incoming in outfield_bench:
        if incoming not in played:
            continue
        eligible_out = [
            pid for pid in no_show
            if pid != starting_gk and _legal_formation(
                [x for x in starters[1:] if x != pid] + [incoming], pos, rules
            )
        ]
        if not eligible_out:
            continue
        outgoing = eligible_out[0]
        starters[starters.index(outgoing)] = incoming
        no_show.remove(outgoing)
        substitutions.append({"out": outgoing, "in": incoming, "kind": "outfield"})

    effective_captain = captain_id if captain_id in played else (
        vice_id if vice_id in played else None
    )
    multiplier = 1
    if effective_captain is not None:
        multiplier = rules.triple_captain_multiplier if active_chip == rules.triple_captain_chip else rules.captain_multiplier

    bench_boost = active_chip == rules.bench_boost_chip
    counted = sorted(set(starters) | (set(bench) if bench_boost else set()))
    return {
        "season": rules.season,
        "rules_version": rules.rules_version,
        "rules_status": rules.rules_status,
        "active_chip": active_chip,
        "substitutions": substitutions,
        "starting_xi_after_subs": starters,
        "nonplaying_starters_unreplaced": no_show,
        "effective_captain": effective_captain,
        "captain_multiplier": multiplier,
        "bench_boost_active": bench_boost,
        "counted_player_ids": counted,
        "played_player_ids": sorted(played),
    }


def chip_usage_rates(entries: Sequence[Mapping[str, Any]], event: int, *, source_url: str, captured_at: str, content_hash: str) -> Dict[str, Any]:
    """Descriptive chip use from official entry history; unknown histories excluded."""
    if event < 1:
        raise ValueError("event must be >= 1")
    if not source_url.startswith("https://") or not content_hash.strip():
        raise RuleInputError("chip source_url and content_hash are required")
    try:
        captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise RuleInputError("chip captured_at must be ISO-8601") from exc
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise RuleInputError("chip captured_at must be timezone-aware")
    known = 0
    counts: Dict[str, int] = {}
    for entry in entries:
        history = entry.get("chips")
        if not isinstance(history, list):
            continue
        known += 1
        seen_this_event = set()
        for item in history:
            if not isinstance(item, Mapping):
                continue
            try:
                chip_event = int(item.get("event", -1))
            except (TypeError, ValueError):
                continue
            if chip_event != event:
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            seen_this_event.add(name)
        for name in seen_this_event:
            counts[name] = counts.get(name, 0) + 1
    return {
        "event": event,
        "source_url": source_url,
        "captured_at": captured_at,
        "content_hash": content_hash,
        "sample_size": len(entries),
        "known_history_denominator": known,
        "unknown_history_count": len(entries) - known,
        "chips": {
            name: {"used_count": count, "usage_pct": (100.0 * count / known) if known else None}
            for name, count in sorted(counts.items())
        },
        "interpretation": "descriptive cohort usage only; not a chip recommendation",
    }


def build_fixture_ticker(
    fixtures: Any,
    teams: Sequence[Mapping[str, Any]],
    events: Any,
    *,
    horizon: int = 8,
    source_url: str,
    captured_at: str,
    content_hash: str,
) -> Dict[str, Any]:
    """Build next-N-GW ticker with blanks, singles, doubles and home/away."""
    if not 1 <= horizon <= 8:
        raise ValueError("horizon must be between 1 and 8")
    if not source_url.startswith("https://") or not content_hash.strip():
        raise CurrentDataError("fixture source_url and content_hash are required")
    try:
        captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise CurrentDataError("captured_at must be ISO-8601") from exc
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise CurrentDataError("captured_at must be timezone-aware")
    gameweeks = planning_horizon(events, horizon)
    assert_future_gameweeks(gameweeks, events)
    normalized = normalize_fixtures(fixtures)
    fixture_map = build_fixture_map(fixtures, teams)
    assert_gameweeks_have_fixtures(fixture_map, gameweeks)
    team_rows = []
    for team in teams:
        tid = int(team["id"])
        short = str(team.get("short_name", team.get("name", tid)))
        cells = []
        for gw in gameweeks:
            rows = fixture_map.get(gw, {}).get(tid, [])
            if not rows:
                cells.append({"gameweek": gw, "status": "BGW", "fixtures": []})
            else:
                cells.append({
                    "gameweek": gw,
                    "status": "DGW" if len(rows) > 1 else "SGW",
                    "fixtures": [
                        {
                            "opponent_id": row["opp"],
                            "venue": "H" if row["is_home"] else "A",
                            "difficulty": row["fdr"],
                            "kickoff_time": row["kickoff_time"],
                            "finished": row["finished"],
                        }
                        for row in rows
                    ],
                })
        team_rows.append({"team_id": tid, "team": short, "gameweeks": cells})
    return {
        "schema_version": "phase3.fixture-ticker.0.1.0",
        "source_url": source_url,
        "captured_at": captured_at,
        "content_hash": content_hash,
        "horizon": gameweeks,
        "teams": team_rows,
        "fixture_count": len(normalized),
    }
