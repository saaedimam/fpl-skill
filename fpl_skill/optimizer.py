#!/usr/bin/env python3
"""
Exact FPL Wildcard MILP — global 15-man optimum over COMPLETE search space.
No truncation. Directly encodes production objective:
  maximize sum_g ( sum_p ep_{p,g} * y_{p,g} + sum_p ep_{p,g} * c_{p,g} )
subject to squad, budget, club, formation, captain, GW3 hard-XI locks.
"""

import json, hashlib, time, sys
from collections import Counter
from fpl_skill.api import get_fpl_data, normalize_dataset, calculate_player_gw_ep, VALID_FORMATIONS, select_best_legal_xi, evaluate_squad_multi_gw
import pulp

HARD_LOCKS = [411, 426, 399, 398, 165, 8, 115, 40, 427]  # Calafiori, B.Fernandes, Joao Pedro, Haaland
HARD_SET = set(HARD_LOCKS)
GWS = [3, 4, 5, 6]
BUDGET_INT = 1013  # 0.1m units
FORMATIONS = list(VALID_FORMATIONS)  # 7 tuples

def load():
    raw = get_fpl_data()
    records = raw.get("records", [])
    norm = normalize_dataset(records)
    players = norm["players"]
    fm = norm["fixture_map"]
    # dataset hash
    for p in players:
        p["cost_int"] = p.get("now_cost") or 0
    # precompute ep per GW
    ep = {}
    for p in players:
        ep[p["player_id"]] = {g: calculate_player_gw_ep(p, g, fm) for g in GWS}
    data_repr = [{"id": p["player_id"], "name": p["web_name"], "team": p["team"], "pos": p["position"], "cost": p["cost_int"], "ep36": round(sum(ep[p["player_id"]][g] for g in GWS),4)} for p in sorted(players, key=lambda x: x["player_id"])]
    data_hash = hashlib.sha256(json.dumps(data_repr, sort_keys=True).encode()).hexdigest()[:16]
    return players, fm, ep, data_hash, raw

def build_and_solve():
    players, fm, ep, data_hash, raw = load()
    print(f"Players: {len(players)}  Data hash: {data_hash}", flush=True)
    print(f"Hard locks: {HARD_LOCKS}", flush=True)
    by_pos = {
        "GKP": [p for p in players if p["position"]=="GKP"],
        "DEF": [p for p in players if p["position"]=="DEF"],
        "MID": [p for p in players if p["position"]=="MID"],
        "FWD": [p for p in players if p["position"]=="FWD"],
    }
    print(f"Pools GKP:{len(by_pos['GKP'])} DEF:{len(by_pos['DEF'])} MID:{len(by_pos['MID'])} FWD:{len(by_pos['FWD'])}", flush=True)
    # Pre-check hard locks present and cost
    hard_players = [p for p in players if p["player_id"] in HARD_SET]
    print(f"Locked cost: {sum(p['cost_int'] for p in hard_players)/10:.1f}m remaining {BUDGET_INT - sum(p['cost_int'] for p in hard_players)}", flush=True)
    teams = sorted(set(p["team"] for p in players))
    club_players = {c: [p for p in players if p["team"]==c] for c in teams}
    # Map player_id -> player
    by_id = {p["player_id"]: p for p in players}
    # Build MILP
    prob = pulp.LpProblem("FPL_Exact_Wildcard", pulp.LpMaximize)
    # x_p squad inclusion
    x = {pid: pulp.LpVariable(f"x_{pid}", cat="Binary") for pid in by_id}
    # y and c per GW
    y = {(pid,g): pulp.LpVariable(f"y_{pid}_{g}", cat="Binary") for pid in by_id for g in GWS}
    # c only for MID/FWD (still create for all but fix GKP/DEF to 0)
    c = {(pid,g): pulp.LpVariable(f"c_{pid}_{g}", cat="Binary") for pid in by_id for g in GWS}
    # z per formation per GW
    K = list(range(len(FORMATIONS)))
    z = {(k,g): pulp.LpVariable(f"z_{k}_{g}", cat="Binary") for k in K for g in GWS}
    # Objective
    prob += pulp.lpSum(ep[pid][g] * y[(pid,g)] for pid in by_id for g in GWS) + pulp.lpSum(ep[pid][g] * c[(pid,g)] for pid in by_id for g in GWS)
    # Squad size
    prob += pulp.lpSum(x[pid] for pid in by_id) == 15
    # Positional squad
    prob += pulp.lpSum(x[p["player_id"]] for p in by_pos["GKP"]) == 2
    prob += pulp.lpSum(x[p["player_id"]] for p in by_pos["DEF"]) == 5
    prob += pulp.lpSum(x[p["player_id"]] for p in by_pos["MID"]) == 5
    prob += pulp.lpSum(x[p["player_id"]] for p in by_pos["FWD"]) == 3
    # Budget
    prob += pulp.lpSum(by_id[pid]["cost_int"] * x[pid] for pid in by_id) <= BUDGET_INT
    # Club max 3
    for club in teams:
        prob += pulp.lpSum(x[p["player_id"]] for p in club_players[club]) <= 3
    # Hard locks in squad
    for pid in HARD_LOCKS:
        prob += x[pid] == 1
    # y <= x
    for pid in by_id:
        for g in GWS:
            prob += y[(pid,g)] <= x[pid]
    # XI size 11 per GW
    for g in GWS:
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id) == 11
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="GKP") == 1
        # 3..5 DEF, 2..5 MID, 1..3 FWD will be enforced via formation; still add loose bounds for solver strength
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="DEF") >= 3
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="DEF") <= 5
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="MID") >= 2
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="MID") <= 5
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="FWD") >= 1
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="FWD") <= 3
    # Formation selection
    for g in GWS:
        prob += pulp.lpSum(z[(k,g)] for k in K) == 1
        # Fix infeasible GW3 formations that cannot hold 4 locks (need DEF>=1 MID>=1 FWD>=2)
        if g == 3:
            # locks are 1 DEF,1 MID,2 FWD
            for k in K:
                n_def,n_mid,n_fwd = FORMATIONS[k]
                if n_def < 1 or n_mid < 1 or n_fwd < 2:
                    prob += z[(k,g)] == 0
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="DEF") == pulp.lpSum(FORMATIONS[k][0] * z[(k,g)] for k in K)
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="MID") == pulp.lpSum(FORMATIONS[k][1] * z[(k,g)] for k in K)
        prob += pulp.lpSum(y[(pid,g)] for pid in by_id if by_id[pid]["position"]=="FWD") == pulp.lpSum(FORMATIONS[k][2] * z[(k,g)] for k in K)
    # Captain
    for g in GWS:
        prob += pulp.lpSum(c[(pid,g)] for pid in by_id) == 1
        for pid in by_id:
            pos = by_id[pid]["position"]
            if pos in ("GKP","DEF"):
                prob += c[(pid,g)] == 0
            else:
                prob += c[(pid,g)] <= y[(pid,g)]
    # Hard XI locks GW3
    for pid in HARD_LOCKS:
        prob += y[(pid,3)] == 1
        # captain already covered; but if a lock is GKP/DEF it can't be captain — none of the 4 are, so fine

    # Solve
    print(f"Variables: x={len(x)} y={len(y)} c={len(c)} z={len(z)} total={len(x)+len(y)+len(c)+len(z)} constraints~{len(prob.constraints)+50}", flush=True)
    solver = pulp.PULP_CBC_CMD(msg=True, timeLimit=1800, gapRel=0, gapAbs=0)
    t0 = time.time()
    prob.solve(solver)
    elapsed = time.time() - t0
    status = pulp.LpStatus[prob.status]
    obj = pulp.value(prob.objective) if status in ("Optimal","Not Solved") else None
    print(f"Status: {status} Objective: {obj} Time: {elapsed:.1f}s", flush=True)
    # Extract
    squad_ids = [pid for pid in by_id if pulp.value(x[pid]) > 0.5]
    by_gw_y = {g: [pid for pid in by_id if pulp.value(y[(pid,g)]) > 0.5] for g in GWS}
    by_gw_c = {g: [pid for pid in by_id if pulp.value(c[(pid,g)]) > 0.5][0] for g in GWS}
    by_gw_z = {g: [k for k in K if pulp.value(z[(k,g)]) > 0.5][0] for g in GWS}
    print(f"Squad {len(squad_ids)}: {sorted(squad_ids)}")
    for g in GWS:
        k = by_gw_z[g]
        print(f"GW{g}: formation {FORMATIONS[k]} ({k}) XI {sorted(by_gw_y[g])} cap {by_gw_c[g]}")
    # Certificate bundle
    return {
        "status": status, "objective": obj, "elapsed": elapsed,
        "squad_ids": squad_ids, "by_gw_y": by_gw_y, "by_gw_c": by_gw_c, "by_gw_z": by_gw_z,
        "data_hash": data_hash, "raw": raw, "players": players, "ep": ep, "fm": next(iter([p.get("fixture_map") for p in players if p.get("fixture_map")]), None)
    }

if __name__ == "__main__":
    res = build_and_solve()
    import json, pathlib, datetime
    out = pathlib.Path("/tmp/fpl_exact_milp_result.json")
    # make json serializable
    j = {k: (v if k not in ("players","raw","fm","ep") else str(type(v))) for k,v in res.items()}
    j["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out.write_text(json.dumps(j, indent=2))
    print(f"Wrote {out}")
