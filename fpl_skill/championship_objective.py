"""Deterministic championship objective and horizon evaluation."""
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

@dataclass(frozen=True)
class HorizonEvaluation:
    status: str
    horizon: tuple[int, ...]
    total_ep: Optional[float]
    missing: tuple[int, ...]

def bps_bonus_points(scores: Sequence[int]) -> list[int]:
    """FPL bonus allocation by sorted BPS ranks, including tie positions."""
    if not scores:
        return []
    ordered=sorted(set(scores), reverse=True)
    award={}
    if not ordered: return [0 for _ in scores]
    if len(ordered)>=1: award[ordered[0]]=3
    if len(ordered)>=2: award[ordered[1]]=2
    if len(ordered)>=3: award[ordered[2]]=1
    # Tied ranks consume places: 1st tie -> [3,3,1] by competition ranking.
    # Determine each score's competition rank index.
    return [3 if s==ordered[0] else 2 if len([x for x in scores if x>s])==1 else
            1 if len([x for x in scores if x>s])==2 else 0 for s in scores]

def rank_candidates(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Stable lexicographic tie-break; canonical element_id is final key."""
    def key(c):
        action = str(c.get("action",""))
        keep = 0 if action in ("KEEP","NO_ACTION") else 1
        return (-float(c["value"]), -float(c["downside"]), -float(c["coverage"]),
                float(c["cost"]), keep, int(c["element_id"]))
    return [dict(x) for x in sorted(candidates,key=key)]

def classic_league_transfer_count(history: Iterable[Mapping[str, Any]]) -> int:
    return sum(int(x.get("transfers",0) or 0) for x in history
               if str(x.get("chip") or "").lower() not in {"wildcard","free_hit"})

def evaluate_horizon(expected_points: Mapping[int,float], horizon: Optional[Sequence[int]]) -> HorizonEvaluation:
    if horizon is None:
        raise ValueError("requested horizon must be explicit")
    required=tuple(int(x) for x in horizon)
    if not required:
        raise ValueError("requested horizon cannot be empty")
    missing=tuple(g for g in required if g not in expected_points or expected_points[g] is None)
    if missing:
        return HorizonEvaluation("INSUFFICIENT_DATA",required,None,missing)
    return HorizonEvaluation("READY",required,sum(float(expected_points[g]) for g in required),())

def compare_horizons(left: HorizonEvaluation,right: HorizonEvaluation) -> HorizonEvaluation:
    if left.status!="READY" or right.status!="READY":
        return HorizonEvaluation("INSUFFICIENT_DATA",left.horizon,None,
             tuple(sorted(set(left.missing+right.missing))))
    return HorizonEvaluation("READY",left.horizon,(left.total_ep or 0)-(right.total_ep or 0),())

def evaluate_transfer_horizon(expected_points: Mapping[int,float], horizon: Sequence[int]) -> HorizonEvaluation:
    return evaluate_horizon(expected_points,horizon)
