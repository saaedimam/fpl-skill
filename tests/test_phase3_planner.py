"""Tests for public-input 8-GW transfer scenario planner."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fpl_skill.current_data import CurrentDataError
from fpl_skill import phase3_planner as planner


def _squad():
    return [{"player_id": i, "cost_m": 5.0, "position": "DEF", "team": i % 5,
             "web_name": f"P{i}"} for i in range(1, 16)]


def _picks():
    return [{"element": i, "selling_price": 50} for i in range(1, 16)]


def _events():
    return [{"id": i, "is_next": i == 4, "finished": i < 4} for i in range(1, 39)]


def test_resolve_horizon_is_eight_future_gameweeks():
    assert planner.resolve_horizon(4, 8, _events()) == list(range(4, 12))


def test_planner_uses_selling_price_and_compares_roll_scenario(monkeypatch):
    squad = _squad()
    players = squad + [{"player_id": 99, "cost_m": 5.0, "position": "DEF", "team": 1, "web_name": "New"}]
    def evaluate(s, gws, fixture_map):
        return {"total_ep": 100.0 if len(s) == 15 and s[0]["player_id"] != 99 else 110.0,
                "gw_details": {gw: {"total_ep": 10} for gw in gws}}
    def search(s, all_players, **kwargs):
        assert kwargs["bank"] == 1.0
        assert s[0]["selling_price_m"] == 4.5
        changed = [dict(p) for p in s]
        changed[0] = dict(all_players[-1])
        return {"player_out": s[0], "player_in": all_players[-1], "squad": changed}
    monkeypatch.setattr(planner, "evaluate_squad_multi_gw", evaluate)
    monkeypatch.setattr(planner, "find_best_one_ft", search)
    picks = _picks()
    picks[0]["selling_price"] = 45
    result = planner.plan_multi_gw_scenarios(
        squad=squad, official_picks=picks, all_players=players,
        bank_tenths=10, free_transfers=1, events=_events(),
        fixture_map={}, target_gw=4, horizon_length=8,
        roll_option_value_points=1.5,
    )
    assert result["horizon"] == list(range(4, 12))
    assert result["recommendation"] == "TRANSFER"
    assert result["best_transfer"]["outgoing_selling_price_m"] == 4.5
    assert result["scenarios"]["ROLL"] == 101.5


def test_no_free_transfer_requires_explicit_hit_permission(monkeypatch):
    squad = _squad()
    def evaluate(s, gws, fixture_map):
        return {"total_ep": 100.0, "gw_details": {}}
    def search(s, all_players, **kwargs):
        return {"player_out": s[0], "player_in": all_players[-1], "squad": s}
    monkeypatch.setattr(planner, "evaluate_squad_multi_gw", evaluate)
    monkeypatch.setattr(planner, "find_best_one_ft", search)
    args = dict(squad=squad, official_picks=_picks(), all_players=squad + [{"player_id": 99, "cost_m": 5.0}],
                bank_tenths=0, free_transfers=0, events=_events(), fixture_map={}, target_gw=4)
    hold = planner.plan_multi_gw_scenarios(**args)
    hit = planner.plan_multi_gw_scenarios(**args, allow_hit=True)
    assert hold["recommendation"] == "HOLD"
    assert hit["recommendation"] == "HOLD"
    assert hit["scenarios"]["ONE_HIT_TRANSFER"] == 96.0


def test_missing_selling_price_and_stale_horizon_fail_closed():
    picks = _picks()
    del picks[0]["selling_price"]
    with pytest.raises(CurrentDataError, match="selling_price"):
        planner.plan_multi_gw_scenarios(
            squad=_squad(), official_picks=picks, all_players=_squad(),
            bank_tenths=0, free_transfers=1, events=_events(),
            fixture_map={}, target_gw=4,
        )
    with pytest.raises(CurrentDataError):
        planner.resolve_horizon(3, 8, _events())


def test_no_legal_transfer_does_not_claim_roll_option_when_no_free_transfer(monkeypatch):
    squad = _squad()
    monkeypatch.setattr(planner, "evaluate_squad_multi_gw",
                        lambda s, gws, fixture_map: {"total_ep": 80.0, "gw_details": {}})
    monkeypatch.setattr(planner, "find_best_one_ft",
                        lambda *args, **kwargs: {"player_out": None, "player_in": None})
    result = planner.plan_multi_gw_scenarios(
        squad=squad, official_picks=_picks(), all_players=squad,
        bank_tenths=0, free_transfers=0, events=_events(),
        fixture_map={}, target_gw=4,
    )
    assert result["scenarios"] == {"HOLD": 80.0}
