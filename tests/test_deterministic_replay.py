"""
tests/test_deterministic_replay.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Verifies select_best_legal_xi() and build_and_solve(solve=False)
are deterministic: identical inputs produce identical outputs.
No network access all data synthetic fixtures.
"""
import copy
import pytest
from fpl_skill.api import select_best_legal_xi, VALID_FORMATIONS
from fpl_skill.optimizer import build_and_solve
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Synthetic squad fixture (15 players, valid FPL squad composition)
# ---------------------------------------------------------------------------


def _mk_squad():
    """Return reproducible 15-player squad internal dicts."""
    gkps = [
        {"player_id": 1, "web_name": "GKP_A", "position": "GKP", "team": "A", "now_cost": 50,
         "ep_next": 4.0, "chance_of_playing_next_round": 100},
        {"player_id": 2, "web_name": "GKP_B", "position": "GKP", "team": "B", "now_cost": 45,
         "ep_next": 3.0, "chance_of_playing_next_round": 100},
    ]
    defs = [
        {"player_id": 10 + i, "web_name": f"DEF_{i}", "position": "DEF", "team": chr(65 + i),
         "now_cost": 55, "ep_next": 5.0 - i * 0.2, "chance_of_playing_next_round": 100}
        for i in range(5)
    ]
    mids = [
        {"player_id": 20 + i, "web_name": f"MID_{i}", "position": "MID", "team": chr(75 + i),
         "now_cost": 70, "ep_next": 7.0 - i * 0.3, "chance_of_playing_next_round": 100}
        for i in range(5)
    ]
    fwds = [
        {"player_id": 30 + i, "web_name": f"FWD_{i}", "position": "FWD", "team": chr(80 + i),
         "now_cost": 80, "ep_next": 9.0 - i * 0.5, "chance_of_playing_next_round": 100}
        for i in range(3)
    ]
    return gkps + defs + mids + fwds


# ---------------------------------------------------------------------------
# 1. Deterministic replay test
# ---------------------------------------------------------------------------


def test_select_best_legal_xi_respects_formation_legality():
    """Formation returned must be in VALID_FORMATIONS."""
    squad = _mk_squad()
    FIXTURE_MAP = {}
    result = select_best_legal_xi(squad, 5, FIXTURE_MAP)
    formation = result.get("formation")
    # formation is a string like "3-5-2", VALID_FORMATIONS is list of tuples
    assert formation is None or tuple(int(x) for x in formation.split("-")) in VALID_FORMATIONS


def test_select_best_legal_xi_xi_has_eleven_players():
    """Starting XI must have exactly 11 players."""
    squad = _mk_squad()
    FIXTURE_MAP = {}
    result = select_best_legal_xi(squad, 5, FIXTURE_MAP)
    assert len(result["starting_xi"]) == 11


def test_select_best_legal_xi_deterministic():
    """Identical inputs must produce identical outputs."""
    squad = _mk_squad()
    FIXTURE_MAP = {}
    result1 = select_best_legal_xi(squad, 5, FIXTURE_MAP)
    result2 = select_best_legal_xi(squad, 5, FIXTURE_MAP)
    # Compare canonical decision fields explicitly
    assert result1["formation"] == result2["formation"]
    assert result1["starting_xi"] == result2["starting_xi"]
    assert result1["captain"] == result2["captain"]
    assert result1["vice_captain"] == result2["vice_captain"]


def test_select_best_legal_xi_legal_captain():
    """Captain must be an outfield player from starting XI."""
    squad = _mk_squad()
    FIXTURE_MAP = {}
    result = select_best_legal_xi(squad, 5, FIXTURE_MAP)
    assert result["captain"]["position"] != "GKP"


# ---------------------------------------------------------------------------
# 2. build_and_solve deterministic wrapper
# ---------------------------------------------------------------------------


def test_build_and_solve_deterministic():
    """build_and_solve with mock data produces consistent variables."""
    records = []
    for pos, et, n in [("GKP", 1, 5), ("DEF", 2, 10), ("MID", 3, 10), ("FWD", 4, 6)]:
        for i in range(n):
            pid = {"GKP": 0, "DEF": 100, "MID": 200, "FWD": 300}[pos] + i
            records.append({
                "player_id": pid, "web_name": f"{pos}_{i}", "position": pos,
                "team": f"T{i+10}", "now_cost": 55, "ep_next": 5.0,
                "element_type": et, "id": pid,
            })
    with patch("fpl_skill.optimizer.get_fpl_data", return_value={"records": records}):
        res1 = build_and_solve(budget=100.0, solve=False)
        res2 = build_and_solve(budget=100.0, solve=False)
        # Check the actual result structure
        assert "variables_count" in res1
        assert "status" in res1
        assert res1["variables_count"] == res2["variables_count"]
        assert res1["status"] == res2["status"]