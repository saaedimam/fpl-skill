"""Current-data release gate.

Single normalizer for fixture payloads plus fail-loud checks used by every
planning path (prediction, transfers, optimizer):

* ``normalize_fixtures`` / ``build_fixture_map`` accept the live FPL
  ``/api/fixtures/`` schema (``event``, ``team_h``, ``team_a``,
  ``team_h_difficulty``, ``team_a_difficulty``, ``kickoff_time``, ``finished``)
  and the legacy record schema (``gameweek_history``/``fixture_details`` JSON
  produced by ``direct_api.fetch_direct_fpl_data``). Anything else raises.
* ``planning_horizon`` derives the horizon from bootstrap ``events``
  (``is_next``/``is_current``) instead of a hardcoded GW range.
* ``assert_future_gameweeks`` refuses planning windows containing finished GWs.
* ``assert_projections_valid`` refuses missing, NaN or all-zero projections.
* ``blank_teams`` reports genuine blank gameweeks explicitly.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

LIVE_FIXTURE_KEYS = ("event", "team_h", "team_a")


class CurrentDataError(RuntimeError):
    """Raised when current FPL data is missing, unrecognized or unusable for planning."""


def _parse(val: Any) -> Any:
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return None
    return val


def _team_aliases(teams: Optional[Iterable[Mapping[str, Any]]]) -> Dict[Any, List[Any]]:
    aliases: Dict[Any, List[Any]] = {}
    for t in teams or []:
        tid = t.get("id")
        keys = [k for k in (tid, t.get("name"), t.get("short_name")) if k is not None]
        for k in keys:
            aliases[k] = keys
    return aliases


def normalize_fixtures(fixtures: Any) -> List[Dict[str, Any]]:
    """Return fixtures as ``{gw, home, away, home_fdr, away_fdr, kickoff_time, finished}``.

    Fixtures with ``event`` None (unscheduled/postponed) are skipped. Raises
    ``CurrentDataError`` for a missing/empty payload or an unrecognized schema.
    """
    if fixtures is None:
        raise CurrentDataError("Fixtures payload is missing (None).")
    if not isinstance(fixtures, list):
        raise CurrentDataError(f"Fixtures payload must be a list, got {type(fixtures).__name__}.")
    if not fixtures:
        raise CurrentDataError("Fixtures payload is empty.")
    out: List[Dict[str, Any]] = []
    recognized = 0
    for f in fixtures:
        if not isinstance(f, Mapping):
            continue
        gh = _parse(f.get("fixture_details") or f.get("gameweek_history"))
        # Legacy record schema first: direct_api records carry both, and their
        # players are keyed by team name, matching home_team/away_team.
        if isinstance(gh, Mapping) and gh.get("home_team") and gh.get("away_team"):
            recognized += 1
            if not gh.get("gameweek"):
                continue
            out.append({
                "gw": int(gh["gameweek"]), "home": gh["home_team"], "away": gh["away_team"],
                "home_fdr": f.get("team_h_difficulty", 3), "away_fdr": f.get("team_a_difficulty", 3),
                "kickoff_time": gh.get("kickoff_time", f.get("kickoff_time")),
                "finished": bool(gh.get("finished", f.get("finished"))),
            })
            continue
        if all(k in f for k in LIVE_FIXTURE_KEYS):
            recognized += 1
            if f.get("event") is None:
                continue
            out.append({
                "gw": int(f["event"]), "home": f["team_h"], "away": f["team_a"],
                "home_fdr": f.get("team_h_difficulty", 3), "away_fdr": f.get("team_a_difficulty", 3),
                "kickoff_time": f.get("kickoff_time"), "finished": bool(f.get("finished")),
            })
            continue
    if recognized == 0:
        sample = sorted(fixtures[0].keys()) if isinstance(fixtures[0], Mapping) else type(fixtures[0]).__name__
        raise CurrentDataError(f"Unrecognized fixtures schema; first record keys: {sample}")
    if not out:
        raise CurrentDataError("Fixtures payload contains no scheduled gameweek fixtures.")
    return out


def build_fixture_map(fixtures: Any, teams: Optional[Iterable[Mapping[str, Any]]] = None) -> Dict[int, Dict[Any, List[Dict[str, Any]]]]:
    """``fixture_map[gw][team_key] -> [{opp, is_home, fdr, kickoff_time, finished}]``.

    Keys are whatever the payload uses for teams (live: team id; legacy: team
    name). When bootstrap ``teams`` are given, id, name and short_name are all
    registered so ``calculate_player_gw_ep``'s ``player["team"]`` lookup works
    for raw bootstrap elements (int id) and normalized players (name) alike.
    Teams absent from a GW that has fixtures are blank (see ``blank_teams``).
    """
    aliases = _team_aliases(teams)
    fm: Dict[int, Dict[Any, List[Dict[str, Any]]]] = {gw: {} for gw in range(1, 39)}
    for fx in normalize_fixtures(fixtures):
        gw = fx["gw"]
        fm.setdefault(gw, {})
        for team, opp, home, fdr in ((fx["home"], fx["away"], True, fx["home_fdr"]), (fx["away"], fx["home"], False, fx["away_fdr"])):
            entry = {"opp": opp, "is_home": home, "fdr": fdr, "kickoff_time": fx["kickoff_time"], "finished": fx["finished"]}
            for key in aliases.get(team, [team]):
                fm[gw].setdefault(key, []).append(entry)
    return fm


def _events(events_or_bootstrap: Any) -> List[Mapping[str, Any]]:
    ev = events_or_bootstrap.get("events") if isinstance(events_or_bootstrap, Mapping) else events_or_bootstrap
    if not ev:
        raise CurrentDataError("Bootstrap events are missing; cannot determine the current gameweek.")
    return list(ev)


def finished_gameweeks(events_or_bootstrap: Any) -> List[int]:
    return sorted(int(e["id"]) for e in _events(events_or_bootstrap) if e.get("finished") or e.get("data_checked"))


def next_gameweek(events_or_bootstrap: Any) -> int:
    ev = _events(events_or_bootstrap)
    for e in ev:
        if e.get("is_next"):
            return int(e["id"])
    for e in ev:
        if e.get("is_current") and not e.get("finished"):
            return int(e["id"])
    raise CurrentDataError("No upcoming gameweek in bootstrap events (season over or data stale).")


def planning_horizon(events_or_bootstrap: Any, length: int = 4) -> List[int]:
    """Next ``length`` gameweeks starting at the live next event (capped at GW38)."""
    start = next_gameweek(events_or_bootstrap)
    return list(range(start, min(38, start + length - 1) + 1))


def assert_future_gameweeks(gameweeks: Sequence[int], events_or_bootstrap: Any) -> None:
    """Raise if any requested planning gameweek is already finished or deadline-passed."""
    if not gameweeks:
        raise CurrentDataError("Planning horizon is empty.")
    nxt = next_gameweek(events_or_bootstrap)
    played = sorted(set(int(g) for g in gameweeks if int(g) < nxt) | (set(map(int, gameweeks)) & set(finished_gameweeks(events_or_bootstrap))))
    if played:
        raise CurrentDataError(
            f"Refusing to plan for already-played gameweek(s) {played}; next gameweek is {nxt}."
        )


def assert_gameweeks_have_fixtures(fixture_map: Mapping[int, Mapping[Any, Any]], gameweeks: Sequence[int]) -> None:
    empty = [g for g in gameweeks if not fixture_map.get(g)]
    if empty:
        raise CurrentDataError(f"No fixtures loaded for gameweek(s) {empty}; fixture data missing or stale.")


def blank_teams(fixture_map: Mapping[int, Mapping[Any, Any]], gw: int, team_keys: Iterable[Any]) -> List[Any]:
    """Teams (from ``team_keys``) with no fixture in ``gw``. Raises if ``gw`` has no fixtures at all."""
    assert_gameweeks_have_fixtures(fixture_map, [gw])
    gwmap = fixture_map[gw]
    return sorted({t for t in team_keys if not gwmap.get(t)}, key=str)


def assert_projections_valid(projections: Mapping[Any, Any], context: str = "planning run") -> None:
    """Raise if projections are missing, contain NaN/None, or are all zero."""
    if not projections:
        raise CurrentDataError(f"No player projections produced for {context}.")
    vals = []
    for k, v in projections.items():
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise CurrentDataError(f"Projection for {k} is not numeric ({v!r}) in {context}.")
        if math.isnan(f) or math.isinf(f):
            raise CurrentDataError(f"Projection for {k} is NaN/inf in {context}.")
        vals.append(f)
    if all(v == 0.0 for v in vals):
        raise CurrentDataError(
            f"All {len(vals)} player projections are zero for {context}; fixtures or player data are missing."
        )
