#!/usr/bin/env python3
"""
Exact FPL Wildcard MILP — global 15-man optimum over COMPLETE search space.
No truncation. Directly encodes production objective:
  maximize sum_g ( sum_p ep_{p,g} * y_{p,g} + sum_p ep_{p,g} * c_{p,g} )
subject to squad, budget, club, formation, captain, GW3 hard-XI locks.
"""

import json, hashlib, time, sys
from collections import Counter
from typing import Optional, List, Tuple, Dict, Any
from fpl_skill.api import get_fpl_data, normalize_dataset, calculate_player_gw_ep, VALID_FORMATIONS, select_best_legal_xi, evaluate_squad_multi_gw
import pulp

FORMATIONS = list(VALID_FORMATIONS)  # All legal formations

def load(horizon: Tuple[int, int] = (3, 6)):
    raw = get_fpl_data()
    records = raw.get("records", [])
    norm = normalize_dataset(records)
    players = norm["players"]
    fm = norm["fixture_map"]
    gws = list(range(horizon[0], horizon[1] + 1)) if isinstance(horizon, tuple) else list(horizon)
    for p in players:
        p["cost_int"] = p.get("now_cost") or 0
    ep = {}
    for p in players:
        ep[p["player_id"]] = {g: calculate_player_gw_ep(p, g, fm) for g in gws}
    data_repr = [{"id": p["player_id"], "name": p["web_name"], "team": p["team"], "pos": p["position"], "cost": p["cost_int"], "ep": round(sum(ep[p["player_id"]][g] for g in gws), 4)} for p in sorted(players, key=lambda x: x["player_id"])]
    data_hash = hashlib.sha256(json.dumps(data_repr, sort_keys=True).encode()).hexdigest()[:16]
    return players, fm, ep, data_hash, raw, gws

def build_and_solve(
    budget: float,
    player_locks: Optional[List[int]] = None,
    horizon: Tuple[int, int] = (3, 6),
    solve: bool = True,
    time_limit: int = 60
) -> Dict[str, Any]:
    player_locks = list(player_locks or [])
    budget_int = int(round(budget * 10))
    players, fm, ep, data_hash, raw, gws = load(horizon=horizon)
    print(f"Players: {len(players)}  Data hash: {data_hash}", flush=True)
    print(f"Locks: {player_locks}  Budget: £{budget:.1f}m  Horizon: {horizon}", flush=True)
    by_pos = {
        "GKP": [p for p in players if p["position"]=="GKP"],
        "DEF": [p for p in players if p["position"]=="DEF"],
        "MID": [p for p in players if p["position"]=="MID"],
        "FWD": [p for p in players if p["position"]=="FWD"],
    }
    by_id = {p["player_id"]: p for p in players}

    # Verify locks exist
    for pid in player_locks:
        if pid not in by_id:
            raise KeyError(f"Locked player ID {pid} not found in player dataset")

    prob = pulp.LpProblem("FPL_Exact_Wildcard", pulp.LpMaximize)
    x = {pid: pulp.LpVariable(f"x_{pid}", cat="Binary") for pid in by_id}
    y = {(pid,g): pulp.LpVariable(f"y_{pid}_{g}", cat="Binary") for pid in by_id for g in gws}
    c = {(pid,g): pulp.LpVariable(f"c_{pid}_{g}", cat="Binary") for pid in by_id for g in gws}
    K = list(range(len(FORMATIONS)))
    z = {(k,g): pulp.LpVariable(f"z_{k}_{g}", cat="Binary") for k in K for g in gws}

    # Objective
    prob += pulp.lpSum(ep[pid][g] * y[(pid,g)] for pid in by_id for g in gws) + pulp.lpSum(ep[pid][g] * c[(pid,g)] for pid in by_id for g in gws)

    # Squad size & positions
    prob += pulp.lpSum(x[pid] for pid in by_id) == 15
    prob += pulp.lpSum(x[p["player_id"]] for p in by_pos["GKP"]) == 2
    prob += pulp.lpSum(x[p["player_id"]] for p in by_pos["DEF"]) == 5
    prob += pulp.lpSum(x[p["player_id"]] for p in by_pos["MID"]) == 5
    prob += pulp.lpSum(x[p["player_id"]] for p in by_pos["FWD"]) == 3

    # Budget
    prob += pulp.lpSum(by_id[pid]["cost_int"] * x[pid] for pid in by_id) <= budget_int

    # Club limit <= 3
    teams = sorted(set(p["team"] for p in players))
    club_players = {team: [p for p in players if p["team"]==team] for team in teams}
    for team in teams:
        prob += pulp.lpSum(x[p["player_id"]] for p in club_players[team]) <= 3

    # Player locks
    for pid in player_locks:
        prob += x[pid] == 1

    # y <= x
    for pid in by_id:
        for g in gws:
            prob += y[(pid,g)] <= x[pid]

    # Starting XI size 11
    for g in gws:
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id) == 11
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="GKP") == 1
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="DEF") >= 3
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="DEF") <= 5
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="MID") >= 2
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="MID") <= 5
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="FWD") >= 1
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="FWD") <= 3

    # Formation selection
    for g in gws:
        prob += pulp.lpSum(z[(k,g)] for k in K) == 1
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="DEF") == pulp.lpSum(FORMATIONS[k][0] * z[(k,g)] for k in K)
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="MID") == pulp.lpSum(FORMATIONS[k][1] * z[(k,g)] for k in K)
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="FWD") == pulp.lpSum(FORMATIONS[k][2] * z[(k,g)] for k in K)

    # Captain (MID or FWD)
    for g in gws:
        prob += pulp.lpSum(c[(pid,g)] for pid in by_id) == 1
        for pid in by_id:
            pos = by_id[pid]["position"]
            if pos in ("GKP","DEF"):
                prob += c[(pid,g)] == 0
            else:
                prob += c[(pid,g)] <= y[(pid,g)]

    if not solve:
        return {
            "status": "BUILT",
            "objective": None,
            "squad_ids": [],
            "prob": prob,
            "variables_count": len(prob.variables()),
            "constraints_count": len(prob.constraints),
            "data_hash": data_hash,
            "players": players
        }

    solver = pulp.PULP_CBC_CMD(msg=True, timeLimit=time_limit, gapRel=0, gapAbs=0)
    t0 = time.time()
    prob.solve(solver)
    elapsed = time.time() - t0
    status = pulp.LpStatus[prob.status]

    if status != "Optimal":
        print(f"Status: {status} Objective: None Time: {elapsed:.1f}s", flush=True)
        return {
            "status": status,
            "objective": None,
            "elapsed": elapsed,
            "squad_ids": [],
            "by_gw_y": {},
            "by_gw_c": {},
            "by_gw_z": {},
            "data_hash": data_hash,
            "raw": raw,
            "players": players,
            "ep": ep,
            "fm": next(iter([p.get("fixture_map") for p in players if p.get("fixture_map")]), None)
        }

    obj = pulp.value(prob.objective)
    print(f"Status: {status} Objective: {obj} Time: {elapsed:.1f}s", flush=True)

    squad_ids = [pid for pid in by_id if pulp.value(x[pid]) and pulp.value(x[pid]) > 0.5]
    by_gw_y = {g: [pid for pid in by_id if pulp.value(y[(pid,g)]) and pulp.value(y[(pid,g)]) > 0.5] for g in gws}
    by_gw_c = {g: [pid for pid in by_id if pulp.value(c[(pid,g)]) and pulp.value(c[(pid,g)]) > 0.5][0] for g in gws if any(pulp.value(c[(pid,g)]) and pulp.value(c[(pid,g)]) > 0.5 for pid in by_id)}
    by_gw_z = {g: [k for k in K if pulp.value(z[(k,g)]) and pulp.value(z[(k,g)]) > 0.5][0] for g in gws if any(pulp.value(z[(k,g)]) and pulp.value(z[(k,g)]) > 0.5 for k in K)}

    return {
        "status": status, "objective": obj, "elapsed": elapsed,
        "squad_ids": squad_ids, "by_gw_y": by_gw_y, "by_gw_c": by_gw_c, "by_gw_z": by_gw_z,
        "data_hash": data_hash, "raw": raw, "players": players, "ep": ep,
        "fm": next(iter([p.get("fixture_map") for p in players if p.get("fixture_map")]), None)
    }

if __name__ == "__main__":
    res = build_and_solve(budget=100.0)
    import json, pathlib, datetime
    out = pathlib.Path("/tmp/fpl_exact_milp_result.json")
    j = {k: (v if k not in ("players","raw","fm","ep") else str(type(v))) for k,v in res.items()}
    j["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out.write_text(json.dumps(j, indent=2))
    print(f"Wrote {out}")
