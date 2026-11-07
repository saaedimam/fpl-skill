"""Phase 3 season rules, autosub, chip usage and fixture ticker tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fpl_skill.current_data import CurrentDataError
from fpl_skill.phase3_gameweek import (
    RuleInputError, SeasonRules, build_fixture_ticker, chip_usage_rates,
    simulate_autosubs,
)


RULES = SeasonRules("2026/27", "test-fixture-rules-v1", rules_status="TEST_ONLY")


def _picks(captain=2, vice=3):
    return [
        {"element": 1, "position": 1, "is_captain": False, "is_vice_captain": False},
        *[
            {"element": i, "position": i, "is_captain": i == captain, "is_vice_captain": i == vice}
            for i in range(2, 12)
        ],
        *[
            {"element": i, "position": i, "is_captain": False, "is_vice_captain": False}
            for i in range(12, 16)
        ],
    ]


def _positions():
    return {1: "GKP", 2: "DEF", 3: "DEF", 4: "DEF", 5: "DEF",
            6: "MID", 7: "MID", 8: "MID", 9: "MID", 10: "FWD", 11: "FWD",
            12: "DEF", 13: "MID", 14: "FWD", 15: "GKP"}


def test_outfield_autosub_preserves_legal_formation_and_bench_order():
    minutes = {i: 90 for i in range(1, 16)}
    minutes[2] = 0
    result = simulate_autosubs(_picks(), minutes, _positions(), RULES)
    assert result["substitutions"] == [{"out": 2, "in": 12, "kind": "outfield"}]
    assert result["starting_xi_after_subs"][1] == 12


def test_multiple_outfield_autosubs_preserve_formation():
    minutes = {i: 90 for i in range(1, 16)}
    minutes[2] = 0
    minutes[3] = 0
    result = simulate_autosubs(_picks(), minutes, _positions(), RULES)
    assert len(result["substitutions"]) == 1
    assert result["substitutions"][0]["in"] == 12
    assert result["nonplaying_starters_unreplaced"] == [3]


def test_goalkeeper_and_vice_captain_fallback():
    minutes = {i: 90 for i in range(1, 16)}
    minutes[1] = 0
    minutes[2] = 0
    result = simulate_autosubs(_picks(captain=2, vice=3), minutes, _positions(), RULES)
    assert {"out": 1, "in": 15, "kind": "goalkeeper"} in result["substitutions"]
    assert result["effective_captain"] == 3


def test_triple_captain_and_bench_boost_are_explicit_chip_effects():
    minutes = {i: 90 for i in range(1, 16)}
    tc = simulate_autosubs(_picks(), minutes, _positions(), RULES, active_chip="3xc")
    bb = simulate_autosubs(_picks(), minutes, _positions(), RULES, active_chip="bboost")
    assert tc["captain_multiplier"] == 3
    assert bb["bench_boost_active"] is True
    assert len(bb["counted_player_ids"]) == 15


def test_rejects_missing_minutes_and_bad_squad_shape():
    minutes = {i: 90 for i in range(1, 15)}
    with pytest.raises(RuleInputError, match="missing minutes"):
        simulate_autosubs(_picks(), minutes, _positions(), RULES)
    with pytest.raises(RuleInputError, match="exactly 15"):
        simulate_autosubs(_picks()[:14], {i: 90 for i in range(1, 15)}, _positions(), RULES)


def test_chip_usage_uses_only_known_histories_as_denominator():
    result = chip_usage_rates([
        {"chips": [{"name": "wildcard", "event": 4}]},
        {"chips": []},
        {"entry_id": 3},
    ], 4, source_url="https://fantasy.premierleague.com/api/entry/10/history/", captured_at="2026-11-08T10:00:00Z", content_hash="sha256:chip")
    assert result["known_history_denominator"] == 2
    assert result["unknown_history_count"] == 1
    assert result["chips"]["wildcard"]["usage_pct"] == 50.0


def test_fixture_ticker_marks_bgw_sgw_and_dgw():
    teams = [{"id": 1, "short_name": "AAA"}, {"id": 2, "short_name": "BBB"},
             {"id": 3, "short_name": "CCC"}]
    events = [{"id": i, "is_next": i == 2, "finished": i < 2} for i in range(1, 9)]
    fixtures = [
        {"id": 1, "event": 2, "team_h": 1, "team_a": 2, "team_h_difficulty": 2, "team_a_difficulty": 4, "kickoff_time": "2026-11-10T15:00:00Z", "finished": False},
        {"id": 2, "event": 2, "team_h": 1, "team_a": 3, "team_h_difficulty": 3, "team_a_difficulty": 3, "kickoff_time": "2026-11-12T15:00:00Z", "finished": False},
        {"id": 3, "event": 3, "team_h": 2, "team_a": 3, "team_h_difficulty": 3, "team_a_difficulty": 3, "kickoff_time": "2026-11-18T15:00:00Z", "finished": False},
    ]
    result = build_fixture_ticker(fixtures, teams, events, horizon=2, source_url="https://fantasy.premierleague.com/api/fixtures/", captured_at="2026-11-08T10:00:00Z", content_hash="sha256:test")
    team1 = next(t for t in result["teams"] if t["team_id"] == 1)
    team2 = next(t for t in result["teams"] if t["team_id"] == 2)
    assert team1["gameweeks"][0]["status"] == "DGW"
    assert team2["gameweeks"][0]["status"] == "SGW"
    assert team1["gameweeks"][1]["status"] == "BGW"


def test_fixture_ticker_rejects_missing_fixture_horizon():
    teams = [{"id": 1, "short_name": "AAA"}, {"id": 2, "short_name": "BBB"}]
    events = [{"id": 1, "is_next": True, "finished": False}]
    with pytest.raises(CurrentDataError):
        build_fixture_ticker([], teams, events, horizon=1, source_url="https://fantasy.premierleague.com/api/fixtures/", captured_at="2026-11-08T10:00:00Z", content_hash="sha256:test")


def test_fixture_ticker_requires_provenance():
    teams = [{"id": 1, "short_name": "AAA"}, {"id": 2, "short_name": "BBB"}]
    events = [{"id": 1, "is_next": True, "finished": False}]
    fixtures = [{"id": 1, "event": 1, "team_h": 1, "team_a": 2,
                 "team_h_difficulty": 2, "team_a_difficulty": 3, "finished": False}]
    with pytest.raises(CurrentDataError, match="source_url"):
        build_fixture_ticker(fixtures, teams, events, horizon=1,
                             source_url="", captured_at="2026-11-08T10:00:00Z",
                             content_hash="sha256:test")


def test_chip_usage_requires_provenance():
    from fpl_skill.phase3_gameweek import RuleInputError
    with pytest.raises(RuleInputError, match="source_url"):
        chip_usage_rates([{"chips": []}], 1, source_url="", captured_at="2026-11-08T10:00:00Z", content_hash="sha256:x")
