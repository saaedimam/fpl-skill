"""Evidence-backed optimality certificates for the CBC MILP.

``optimality_proven`` is true only when the solver status is ``Optimal``,
an objective value was returned, and the squad/lineup/captain constraints
hold on that solution. Any other status is reported as not certified.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from fpl_skill.execution_sandbox import validate_lineup, validate_squad_players


def certificate_from_solve(
    *,
    solver_status: str,
    objective_value: Optional[float],
    squad: Sequence[Mapping[str, Any]] = (),
    lineups: Optional[Mapping[Any, Sequence[int]]] = None,
    captains: Optional[Mapping[Any, int]] = None,
    budget: float = 100.0,
) -> Dict[str, Any]:
    """Build a certificate from a solver result and a constraint re-check."""
    if solver_status != "Optimal":
        return {
            "solver_status": solver_status,
            "objective_value": None,
            "constraint_recheck": {
                "valid": False,
                "checked": False,
                "violations": [f"solver status is {solver_status}, not Optimal"],
            },
            "admissible": False,
            "optimality_proven": False,
            "certificate": "NOT_CERTIFIED",
        }

    recheck = recheck_milp_solution(
        squad,
        lineups or {},
        captains or {},
        budget=budget,
    )
    proven = objective_value is not None and recheck["valid"]
    return {
        "solver_status": solver_status,
        "objective_value": objective_value,
        "constraint_recheck": recheck,
        "admissible": proven,
        "optimality_proven": proven,
        "certificate": "OPTIMAL" if proven else "NOT_CERTIFIED",
    }


def recheck_milp_solution(
    squad: Sequence[Mapping[str, Any]],
    lineups: Mapping[Any, Sequence[int]],
    captains: Mapping[Any, int],
    *,
    budget: float = 100.0,
) -> Dict[str, Any]:
    """Re-apply squad, formation, and attacking-captain constraints to a solution."""
    violations = validate_squad_players(squad, budget=budget)
    if not lineups:
        violations.append("lineup: solver returned no starting XI")
    for gameweek, xi_ids in lineups.items():
        captain_id = captains.get(gameweek)
        if captain_id is None:
            violations.append(f"captain: missing for gameweek {gameweek}")
        violations.extend(
            validate_lineup(
                squad,
                xi_ids,
                captain_id,
                vice_id=None,
                require_captain=captain_id is not None,
                require_vice=False,
                attacking_captain=True,
            )
        )
    extra_captains = [gw for gw in captains if gw not in lineups]
    for gameweek in extra_captains:
        violations.append(f"captain: gameweek {gameweek} has no lineup")
    deduped = list(dict.fromkeys(violations))
    return {"valid": not deduped, "checked": True, "violations": deduped}


def prove_bound_checks(bound_checks: Optional[Iterable[Mapping[str, Any]]] = None) -> Dict[str, Any]:
    """Return whether every supplied upper bound is >= the evaluated score.

    With no checks, the bound is not admissible. A constant ``True`` is not
    evidence.
    """
    checks = [dict(check) for check in (bound_checks or [])]
    failures = []
    for index, check in enumerate(checks):
        bound = check.get("bound")
        true_score = check.get("true_score")
        if bound is None or true_score is None:
            failures.append({"index": index, "reason": "missing bound or true_score"})
            continue
        if float(bound) + 1e-6 < float(true_score):
            failures.append({
                "index": index,
                "bound": bound,
                "true_score": true_score,
                "reason": "bound underestimated the evaluated score",
            })
    admissible = bool(checks) and not failures
    return {
        "checks": len(checks),
        "failures": failures,
        "admissible": admissible,
        "verified": admissible,
    }
