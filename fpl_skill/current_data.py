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
* ``blank_teams`` identifies candidate blanks; provenance gates must certify them.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

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
    Teams absent from a GW are candidate blanks only; ``PredictionEngine``
    requires an authoritative complete per-team schedule before classifying them.
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



def build_fixture_schedules(
    snapshot: Any,
    *,
    event_ids: Sequence[int],
    teams: Sequence[Mapping[str, Any]],
    published_event_ids: Set[int],
    complete_event_ids: Set[int],
) -> Dict[Tuple[int, int], Any]:
    """Build per-team schedules from an exact raw fixture response.

    Publication and completeness are explicit upstream evidence. An absent
    team row is never itself evidence that the schedule is complete or blank.
    """
    from fpl_skill.live_state import FixtureSchedule, RetrievalRecord

    if not isinstance(snapshot.payload, bytes) or not snapshot.payload:
        raise CurrentDataError("Raw fixture payload bytes are required for provenance.")
    retrieved_at = snapshot.retrieved_at
    if retrieved_at is not None and (
        retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None
        or retrieved_at.utcoffset().total_seconds() != 0
    ):
        raise ValueError("retrieved_at must be timezone-aware UTC")
    if snapshot.endpoint != "/api/fixtures/":
        raise CurrentDataError("Fixture provenance requires the canonical /api/fixtures/ endpoint.")
    try:
        fixtures = json.loads(snapshot.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentDataError("Official fixture payload is not valid UTF-8 JSON.") from exc
    if not isinstance(fixtures, list):
        raise CurrentDataError("Official fixture payload must be a JSON list.")

    normalized_events = {int(event_id) for event_id in event_ids}
    normalized_teams = [int(team["id"]) for team in teams if team.get("id") is not None]
    if not normalized_events or not normalized_teams:
        raise CurrentDataError("Event IDs and bootstrap team IDs are required for fixture schedules.")
    if len(normalized_teams) != len(set(normalized_teams)):
        raise CurrentDataError("Bootstrap team IDs are duplicated; fixture provenance is conflicted.")

    rows_by_event_team: Dict[Tuple[int, int], List[Mapping[str, Any]]] = {}
    events_with_fixture_rows = set()
    unassigned_event_teams = set()
    for fixture in fixtures:
        if not isinstance(fixture, Mapping):
            raise CurrentDataError("Official fixture payload contains a non-object row.")
        event = fixture.get("event")
        if event is None:
            if fixture.get("team_h") is None or fixture.get("team_a") is None:
                raise CurrentDataError("Unassigned fixture row is missing team IDs.")
            for team_id in (int(fixture["team_h"]), int(fixture["team_a"])):
                if team_id not in normalized_teams:
                    raise CurrentDataError(f"Unassigned fixture references unknown bootstrap team {team_id}.")
                unassigned_event_teams.add(team_id)
            continue
        event = int(event)
        if event not in normalized_events:
            continue
        events_with_fixture_rows.add(event)
        if fixture.get("id") is None or fixture.get("team_h") is None or fixture.get("team_a") is None:
            raise CurrentDataError("Official fixture row is missing ID, home team, or away team.")
        for team_id in (int(fixture["team_h"]), int(fixture["team_a"])):
            if team_id not in normalized_teams:
                raise CurrentDataError(f"Fixture references unknown bootstrap team {team_id}.")
            rows_by_event_team.setdefault((event, team_id), []).append(dict(fixture))

    schedules = {}
    for event_id in sorted(normalized_events):
        for team_id in sorted(normalized_teams):
            retrieval = RetrievalRecord(
                event_id=event_id,
                team_id=team_id,
                endpoint=snapshot.endpoint,
                retrieved_at=retrieved_at,
                observed_at=None,
                payload=snapshot.payload,
                source=snapshot.source,
            )
            schedules[(event_id, team_id)] = FixtureSchedule(
                event_id=event_id,
                team_id=team_id,
                fixtures=tuple(rows_by_event_team.get((event_id, team_id), ())),
                published=event_id in published_event_ids,
                complete=(event_id in complete_event_ids and event_id in events_with_fixture_rows),
                retrieval=retrieval,
                source=snapshot.source,
                conflicted=team_id in unassigned_event_teams,
            )
    return schedules


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
    """Return teams absent from ``gw`` as candidate blanks, not proven blanks."""
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


def require_team_event_schedule(
    fixture_map: Mapping[Any, Any], team_id: Any, event_id: int,
    fixture_schedules: Optional[Mapping[Any, Any]] = None,
) -> str:
    """Validate a team's event schedule; absence alone never proves a blank.

    Verified FixtureSchedule evidence is authoritative for the (event, team)
    pair. Legacy provenance mappings remain supported for compatibility.
    """
    event_id = int(event_id)
    schedule = None
    if isinstance(fixture_schedules, Mapping):
        schedule = fixture_schedules.get((event_id, int(team_id))) if str(team_id).isdigit() else fixture_schedules.get((event_id, team_id))
        if schedule is None:
            schedule = fixture_schedules.get(team_id)
    if schedule is not None:
        from datetime import timedelta
        from fpl_skill.live_state import FixtureSchedule, FixtureStatus, classify_fixture_schedule
        if not isinstance(schedule, FixtureSchedule):
            raise CurrentDataError("INSUFFICIENT_DATA: schedule evidence is not a verified FixtureSchedule.")
        record = schedule.retrieval
        if (schedule.event_id != event_id or str(schedule.team_id) != str(team_id)
                or record.event_id != event_id or str(record.team_id) != str(team_id)
                or record.endpoint != "/api/fixtures/" or record.source != "official-fpl"
                or schedule.source not in (None, "official-fpl")
                or record.retrieved_at is None or record.retrieved_at.tzinfo is None
                or record.retrieved_at.utcoffset() != timedelta(0)
                or not record.payload or len(record.payload_hash) != 64):
            raise CurrentDataError("INSUFFICIENT_DATA: FixtureSchedule provenance is incomplete or mismatched.")
        status = classify_fixture_schedule(schedule)
        if status is FixtureStatus.BLANK:
            return "BLANK"
        if status is FixtureStatus.UNKNOWN and bool(schedule.fixtures):
            return "PLAYING"
        raise CurrentDataError(f"INSUFFICIENT_DATA: schedule classified {status.value}.")
    event_map = fixture_map.get(event_id, {})
    fixtures = event_map.get(team_id) if isinstance(event_map, Mapping) else None
    if isinstance(fixtures, Mapping):
        fixtures = [fixtures]
    if fixtures:
        return "PLAYING"
    evidence_map = fixture_map.get("__schedule_provenance__", {})
    evidence = evidence_map.get((event_id, team_id)) if isinstance(evidence_map, Mapping) else None
    if not isinstance(evidence, Mapping) or evidence.get("status") != "BLANK":
        raise CurrentDataError(
            f"INSUFFICIENT_DATA: no verified team schedule for event {event_id}, team {team_id}; "
            "an absent fixture mapping cannot establish BLANK."
        )
    required = ("event", "team", "endpoint", "retrieved_at", "payload_hash")
    missing = [key for key in required if evidence.get(key) in (None, "")]
    if missing:
        raise CurrentDataError(f"INSUFFICIENT_DATA: BLANK schedule provenance missing {missing}.")
    if int(evidence["event"]) != event_id or str(evidence["team"]) != str(team_id):
        raise CurrentDataError("INSUFFICIENT_DATA: BLANK schedule provenance event/team mismatch.")
    if evidence["endpoint"] != "/api/fixtures/":
        raise CurrentDataError("INSUFFICIENT_DATA: BLANK schedule provenance endpoint mismatch.")
    from datetime import datetime
    try:
        retrieved = datetime.fromisoformat(str(evidence["retrieved_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise CurrentDataError("INSUFFICIENT_DATA: invalid BLANK retrieval timestamp.") from exc
    if retrieved.tzinfo is None or retrieved.utcoffset() is None:
        raise CurrentDataError("INSUFFICIENT_DATA: BLANK retrieval timestamp must be timezone-aware.")
    import re
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(evidence["payload_hash"])):
        raise CurrentDataError("INSUFFICIENT_DATA: BLANK payload_hash must be SHA-256.")
    return "BLANK"
