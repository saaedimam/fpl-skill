"""Evidence-backed optimality certificates for the reduced wildcard MILP.

``optimality_proven`` is always false. A finite CBC objective, a matching
recomputation, and a constraint re-check can mark ``reduced_model_checked``.
That is not proof of full-rule or global optimality. ``full_rule_optimal`` is
always false, and ``certificate`` stays ``NOT_CERTIFIED``.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from fpl_skill.execution_sandbox import validate_lineup, validate_squad_players

WILDCARD_FORMULATION = "FPL_Exact_Wildcard"
WILDCARD_OBJECTIVE = "sum_g (sum_p ep[p,g] * y[p,g] + sum_p ep[p,g] * c[p,g])"
REQUIRED_MODEL_CONSTRAINTS = (
    "squad_size_15",
    "positions_2_5_5_3",
    "budget",
    "club_limit_3",
    "player_locks",
    "lineup_implies_squad",
    "starting_xi_11",
    "positional_xi_bounds",
    "legal_formation",
    "attacking_captain",
)
_LIMITATIONS = (
    "A reduced-model check is not proof of full-rule or global optimality.",
    "Free transfers, hits, selling prices, and vice-captain are not certified.",
    "full_rule_optimal is always false.",
    "optimality_proven is always false.",
)
_OBJECTIVE_TOLERANCE = 1e-4


def wildcard_model(recomputed_objective: float) -> Dict[str, Any]:
    """Declare the encoded wildcard model and an independently recomputed objective."""
    return {
        "formulation": WILDCARD_FORMULATION,
        "objective": WILDCARD_OBJECTIVE,
        "constraints": list(REQUIRED_MODEL_CONSTRAINTS),
        "recomputed_objective": recomputed_objective,
    }


def _as_finite(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number):
        return None
    return number


def certificate_from_solve(
    *,
    solver_status: str,
    objective_value: Optional[float],
    squad: Sequence[Mapping[str, Any]] = (),
    lineups: Optional[Mapping[Any, Sequence[int]]] = None,
    captains: Optional[Mapping[Any, int]] = None,
    budget: float = 100.0,
    model: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Record a reduced-model check. Never issue a full-rule optimality proof."""
    if solver_status != "Optimal":
        return _refused(
            solver_status,
            {
                "valid": False,
                "checked": False,
                "violations": [f"solver status is {solver_status}, not Optimal"],
            },
            {"valid": False, "checked": False, "reason": "solver status is not Optimal"},
        )

    objective = _as_finite(objective_value)
    recheck = recheck_milp_solution(
        squad,
        lineups or {},
        captains or {},
        budget=budget,
    )
    model_check = _check_model(model, objective)
    reduced_checked = objective is not None and recheck["valid"] and model_check["valid"]
    return {
        "solver_status": solver_status,
        "objective_value": objective,
        "constraint_recheck": recheck,
        "model_check": model_check,
        "admissible": False,
        "optimality_proven": False,
        "reduced_model_checked": reduced_checked,
        "full_rule_optimal": False,
        "claim_scope": "reduced_wildcard_milp" if reduced_checked else "none",
        "certificate": "NOT_CERTIFIED",
        "limitations": list(_LIMITATIONS),
    }


def _refused(solver_status: str, recheck: Dict[str, Any], model_check: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "solver_status": solver_status,
        "objective_value": None,
        "constraint_recheck": recheck,
        "model_check": model_check,
        "admissible": False,
        "optimality_proven": False,
        "reduced_model_checked": False,
        "full_rule_optimal": False,
        "claim_scope": "none",
        "certificate": "NOT_CERTIFIED",
        "limitations": list(_LIMITATIONS),
    }


def _check_model(model: Any, objective: Optional[float]) -> Dict[str, Any]:
    if not isinstance(model, Mapping):
        return {
            "valid": False,
            "checked": True,
            "reason": "a declared model and recomputed objective are required",
        }
    reasons = []
    if model.get("formulation") != WILDCARD_FORMULATION:
        reasons.append("formulation is not the encoded wildcard MILP")
    if model.get("objective") != WILDCARD_OBJECTIVE:
        reasons.append("objective expression does not match the encoded wildcard objective")
    constraints = model.get("constraints")
    if not isinstance(constraints, (list, tuple)) or any(not isinstance(item, str) for item in constraints):
        reasons.append("constraints must name the complete reduced model")
    else:
        declared = list(constraints)
        if len(set(declared)) != len(declared) or set(declared) != set(REQUIRED_MODEL_CONSTRAINTS):
            reasons.append("constraint set is not the complete reduced model")
    recomputed = _as_finite(model.get("recomputed_objective"))
    if recomputed is None:
        reasons.append("recomputed objective is missing or not finite")
    elif objective is None:
        reasons.append("solver objective is missing or not finite")
    elif abs(recomputed - objective) > _OBJECTIVE_TOLERANCE:
        reasons.append("recomputed objective does not match the solver objective")
    return {"valid": not reasons, "checked": True, "reason": "; ".join(reasons)}


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
    """Return whether every supplied upper bound is finite and >= the evaluated score.

    NaN and infinities are failures. With no checks, the bound is not admissible.
    A constant ``True`` is not evidence.
    """
    checks = [dict(check) for check in (bound_checks or [])]
    failures = []
    for index, check in enumerate(checks):
        if "bound" not in check or "true_score" not in check:
            failures.append({"index": index, "reason": "missing bound or true_score"})
            continue
        bound = _as_finite(check.get("bound"))
        true_score = _as_finite(check.get("true_score"))
        if bound is None or true_score is None:
            failures.append({
                "index": index,
                "reason": "bound and true_score must be finite numbers",
            })
            continue
        if bound + 1e-6 < true_score:
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
