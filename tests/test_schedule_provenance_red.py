"""Unsealed development regressions for shared schedule provenance."""
import pytest
from test_release_gates import SAMPLE, _all, _err, _fm, _squad

# --- shared schedule provenance red regressions ----------------------------

def test_legacy_ep_rejects_unverified_missing_team_schedule():
    from fpl_skill import api_legacy

    player = {"player_id": 9999, "team": 99, "position": "MID", "minutes": 90}
    fixture_map = {10: {1: [{"opp": 2, "is_home": True, "fdr": 3}]}}
    with pytest.raises(_err(), match="INSUFFICIENT_DATA|schedule|fixture"):
        api_legacy.calculate_player_gw_ep(player, 10, fixture_map)


def test_legacy_xi_and_multi_gw_decisions_reject_partial_team_schedule():
    from fpl_skill import api_legacy

    squad = _squad()
    squad[0] = dict(squad[0], team=99)
    fixture_map = _fm()
    with pytest.raises(_err(), match="INSUFFICIENT_DATA|schedule|fixture"):
        api_legacy.select_best_legal_xi(squad, 10, fixture_map)
    with pytest.raises(_err(), match="INSUFFICIENT_DATA|schedule|fixture"):
        api_legacy.evaluate_squad_multi_gw(squad, [10], fixture_map)


def test_legacy_transfer_and_wildcard_search_reject_partial_team_schedule():
    from fpl_skill import api_legacy

    current = _squad()
    current[0] = dict(current[0], team=99)
    all_players = _all()
    all_players[0] = dict(all_players[0], team=99)
    fixture_map = _fm()
    with pytest.raises(_err(), match="INSUFFICIENT_DATA|schedule|fixture"):
        api_legacy.find_best_one_ft(
            current, all_players, bank=1.0, fixture_map=fixture_map,
            gameweeks=[10, 11, 12, 13], events=SAMPLE["events"],
        )
    with pytest.raises(_err(), match="INSUFFICIENT_DATA|schedule|fixture"):
        api_legacy.optimize_wildcard_squad(
            all_players, fixture_map=fixture_map, gameweeks=[10, 11, 12, 13],
            events=SAMPLE["events"],
        )


def test_optimizer_load_rejects_one_missing_team_even_when_aggregate_ep_is_nonzero(monkeypatch):
    from fpl_skill import optimizer

    players = [
        {"player_id": 1, "team": 1, "position": "MID", "web_name": "Mapped", "now_cost": 50},
        {"player_id": 2, "team": 99, "position": "MID", "web_name": "Missing", "now_cost": 50},
    ]
    monkeypatch.setattr(optimizer, "get_fpl_data", lambda: {"records": []})
    monkeypatch.setattr(optimizer, "normalize_dataset", lambda records: {
        "players": [dict(p) for p in players],
        "fixture_map": {10: {1: [{"opp": 2, "is_home": True, "fdr": 3}]}},
    })
    monkeypatch.setattr(optimizer, "_live_events", lambda: [
        {"id": 10, "is_next": True, "finished": False}
    ])
    monkeypatch.setattr(
        optimizer, "_gw_distribution",
        lambda player, gw, fm, engine: {
            "mean": 2.0 if player["team"] == 1 else 0.0,
            "p10": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0,
            "variance": 0.0, "p_haul": 0.0, "p_zero": 1.0, "fixtures": 1 if player["team"] == 1 else 0,
        },
    )
    with pytest.raises(_err(), match="INSUFFICIENT_DATA|schedule|fixture"):
        optimizer.load(horizon=[10])
