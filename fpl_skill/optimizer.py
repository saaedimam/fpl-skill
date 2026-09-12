"""Public optimizer bound to the Phase-2 probabilistic forecast engine."""
from __future__ import annotations
import hashlib, json
from typing import Any, Dict, Tuple
from . import optimizer_legacy as _legacy
from .api import get_fpl_data, normalize_dataset, VALID_FORMATIONS, select_best_legal_xi, evaluate_squad_multi_gw
from .probabilistic_ep1 import DistributionModelInputs, ProbabilisticEPEngine, normalize_player_state, normalize_position
from .rate_normalization import normalize_player_rates, gw_expected_contributions

FORMATIONS=list(VALID_FORMATIONS)

def _fixtures_for(fm,team,gw):
    x=fm.get(gw,{}).get(team,[]); return [x] if isinstance(x,dict) else list(x or [])

def _distribution_for_fixture(player,gw,fix,engine,idx=0):
    rates=normalize_player_rates(player); expected_minutes=rates.expected_minutes*(0.90 if idx>0 else 1.0); gx,ga,_=gw_expected_contributions(player,expected_minutes)
    inp=DistributionModelInputs(
        player_id=int(player["player_id"]), position=normalize_position(player.get("position","MID")), status=normalize_player_state(player.get("status","available")),
        team=str(player.get("team","")), opponent=str(fix.get("opp","")), gw=int(gw), minutes_played_last_3=float(player.get("minutes",0) or 0),
        chance_of_playing_next_round=player.get("chance_of_playing_next_round"), form=float(player.get("form",0) or 0), selected_by_percent=float(player.get("selected_by_percent",0) or 0),
        fixture_difficulty=int(fix.get("fdr",3) or 3), is_home=bool(fix.get("is_home",True)), opponent_strength_attack=float(player.get("opponent_strength_attack",1000) or 1000),
        opponent_strength_defence=float(player.get("opponent_strength_defence",1000) or 1000), team_goals_per_gw=float(player.get("team_goals_per_gw",1.5) or 1.5),
        team_conceded_per_gw=float(player.get("team_conceded_per_gw",1.2) or 1.2), expected_minutes=expected_minutes, gw_xg=gx, gw_xa=ga, ict_index=float(player.get("ict_index",0) or 0),
    )
    return engine.generate_distribution(inp)

def _gw_distribution(player,gw,fm,engine):
    fixtures=_fixtures_for(fm,player.get("team",""),gw)
    if not fixtures: return {"mean":0.0,"p10":0.0,"p25":0.0,"p50":0.0,"p75":0.0,"p90":0.0,"variance":0.0,"p_haul":0.0,"p_zero":1.0,"fixtures":0}
    ds=[_distribution_for_fixture(player,gw,f,engine,i) for i,f in enumerate(fixtures)]
    return {"mean":round(sum(d.mean for d in ds),6),"p10":round(sum(d.p10 for d in ds),6),"p25":round(sum(d.p25 for d in ds),6),"p50":round(sum(d.p50 for d in ds),6),"p75":round(sum(d.p75 for d in ds),6),"p90":round(sum(d.p90 for d in ds),6),"variance":round(sum(d.variance for d in ds),6),"p_haul":round(max(d.p_haul for d in ds),6),"p_zero":round(min(d.p_zero for d in ds),6),"fixtures":len(ds)}

def load(horizon:Tuple[int,int]=(3,6)):
    raw=get_fpl_data(); norm=normalize_dataset(raw.get("records",[])); players=norm["players"]; fm=norm["fixture_map"]; gws=list(range(horizon[0],horizon[1]+1)) if isinstance(horizon,tuple) else list(horizon)
    engine=ProbabilisticEPEngine(); ep={}
    for p in players:
        pid=int(p["player_id"]); p["cost_int"]=p.get("now_cost") or 0; ep[pid]={}; p["_distribution_diagnostics"]={}
        for gw in gws:
            diag=_gw_distribution(p,gw,fm,engine); ep[pid][gw]=diag["mean"]; p["_distribution_diagnostics"][gw]=diag
    data_repr=[{"id":p["player_id"],"name":p.get("web_name"),"team":p.get("team"),"pos":p.get("position"),"cost":p.get("cost_int"),"ep_mean":round(sum(ep[p["player_id"]][g] for g in gws),6)} for p in sorted(players,key=lambda x:x["player_id"])]
    data_hash=hashlib.sha256(json.dumps(data_repr,sort_keys=True,separators=(",",":")).encode()).hexdigest()[:16]
    return players,fm,ep,data_hash,raw,gws

_legacy.load=load

def build_and_solve(*args,**kwargs): return _legacy.build_and_solve(*args,**kwargs)

if __name__=="__main__":
    result=build_and_solve(budget=100.0)
    from pathlib import Path
    out=Path("/tmp/fpl_exact_milp_result.json")
    out.write_text(json.dumps({k:v for k,v in result.items() if k not in {"players","raw","fm","ep","prob"}},indent=2))
    print(f"Wrote {out}")
