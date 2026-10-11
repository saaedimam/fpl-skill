"""
tests/test_certification_exactness.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Verifies that the canonical HiGHS MILP formulation in fpl_skill.optimizer
finds the exact mathematical optimum matching a brute-force oracle
on a tiny player pool.
"""

import itertools
from unittest.mock import patch
import pytest

from fpl_skill.optimizer import build_and_solve, FORMATIONS


def test_tiny_pool_brute_force_oracle_matches_highs_objective():
    """
    Construct a small, strictly defined player pool:
      - 2 GKP, 6 DEF, 6 MID, 4 FWD (total 18 players)
      - Horizon GW3-4
      - Explicit legal formations and attacking captain requirements
    Assert that brute-force combinatorial evaluation and HiGHS MILP
    objective agree with absolute difference < 1e-9.
    """
    players = []
    gws = [3, 4]
    pid = 1

    # Pool size: 2 GKP (C(2,2)=1), 6 DEF (C(6,5)=6), 6 MID (C(6,5)=6), 4 FWD (C(4,3)=4)
    # Total candidate squads: 1 * 6 * 6 * 4 = 144 squads
    for pos, count in [("GKP", 2), ("DEF", 6), ("MID", 6), ("FWD", 4)]:
        for i in range(count):
            cost = 45 + (pid % 30)
            players.append({
                "player_id": pid,
                "id": pid,
                "web_name": f"{pos}_{i}",
                "position": pos,
                "element_type": {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}[pos],
                "team": f"Team_{pid % 5}",
                "now_cost": cost,
                "cost_int": cost,
                "ep_next": 5.0,
                "ep_gw": {3: float((pid * 3) % 11 + 1), 4: float((pid * 5) % 13 + 1)},
            })
            pid += 1

    ep = {p["player_id"]: p["ep_gw"] for p in players}

    gkps = [p for p in players if p["position"] == "GKP"]
    defs = [p for p in players if p["position"] == "DEF"]
    mids = [p for p in players if p["position"] == "MID"]
    fwds = [p for p in players if p["position"] == "FWD"]

    budget_int = 1000  # £100.0m

    def eval_squad(squad):
        # 1. Club constraint: <= 3 per club
        team_counts = {}
        for p in squad:
            team_counts[p["team"]] = team_counts.get(p["team"], 0) + 1
            if team_counts[p["team"]] > 3:
                return -1e9

        # 2. Budget constraint
        if sum(p["cost_int"] for p in squad) > budget_int:
            return -1e9

        s_gk = [p for p in squad if p["position"] == "GKP"]
        s_d = [p for p in squad if p["position"] == "DEF"]
        s_m = [p for p in squad if p["position"] == "MID"]
        s_f = [p for p in squad if p["position"] == "FWD"]

        total_ep = 0.0
        for g in gws:
            best_gw = -1e9
            for n_d, n_m, n_f in FORMATIONS:
                top_gk = max(ep[p["player_id"]][g] for p in s_gk)
                top_d = sorted([ep[p["player_id"]][g] for p in s_d], reverse=True)[:n_d]
                top_m = sorted([ep[p["player_id"]][g] for p in s_m], reverse=True)[:n_m]
                top_f = sorted([ep[p["player_id"]][g] for p in s_f], reverse=True)[:n_f]

                # Attacking captain: max over starting MIDs and starting FWDs
                cap = max(top_m + top_f)
                gw_score = top_gk + sum(top_d) + sum(top_m) + sum(top_f) + cap
                if gw_score > best_gw:
                    best_gw = gw_score
            total_ep += best_gw
        return total_ep

    # Brute-force search over all positional subsets
    best_oracle_obj = -1e9
    for c_gk in itertools.combinations(gkps, 2):
        for c_d in itertools.combinations(defs, 5):
            for c_m in itertools.combinations(mids, 5):
                for c_f in itertools.combinations(fwds, 3):
                    sq = list(c_gk) + list(c_d) + list(c_m) + list(c_f)
                    score = eval_squad(sq)
                    if score > best_oracle_obj:
                        best_oracle_obj = score

    # Canonical solve via HiGHS
    with patch("fpl_skill.optimizer.load", return_value=(players, {}, ep, "test_hash", {}, gws)):
        res = build_and_solve(budget=100.0, horizon=(3, 4))
        assert res["status"] == "Optimal"
        highs_obj = float(res["objective"])

        diff = abs(best_oracle_obj - highs_obj)
        assert diff < 1e-9, f"Oracle {best_oracle_obj} != HiGHS {highs_obj} (diff={diff})"
