"""Optimality claims require the encoded model, a matching objective, and finite inputs."""
import math

from fpl_skill.optimality import (
    REQUIRED_MODEL_CONSTRAINTS,
    certificate_from_solve,
    prove_bound_checks,
    wildcard_model,
)
from tests.test_execution_safety import _milp_players


def _legal_solution():
    squad = _milp_players()
    xi = [1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15]
    return squad, {1: xi}, {1: 8}


def test_non_finite_bounds_are_rejected():
    for bound, score in (
        (math.nan, 1.0),
        (1.0, math.nan),
        (math.inf, 1.0),
        (1.0, math.inf),
        (-math.inf, 1.0),
        ("nan", 1.0),
        (True, 1.0),
    ):
        proof = prove_bound_checks([{"bound": bound, "true_score": score}])
        assert proof["admissible"] is False
        assert proof["verified"] is False
        assert proof["failures"]


def test_finite_bound_checks_still_compare():
    failed = prove_bound_checks([{"bound": 1.0, "true_score": 2.0}])
    assert failed["verified"] is False
    passed = prove_bound_checks([{"bound": 5.0, "true_score": 5.0}])
    assert passed["verified"] is True


def test_objective_without_the_model_is_not_optimal():
    squad, lineups, captains = _legal_solution()
    certificate = certificate_from_solve(
        solver_status="Optimal",
        objective_value=12.0,
        squad=squad,
        lineups=lineups,
        captains=captains,
    )
    assert certificate["optimality_proven"] is False
    assert certificate["certificate"] == "NOT_CERTIFIED"
    assert certificate["full_rule_optimal"] is False
    assert certificate["claim_scope"] == "none"
    assert certificate["model_check"]["valid"] is False


def test_partial_constraint_set_is_not_the_model():
    squad, lineups, captains = _legal_solution()
    model = wildcard_model(12.0)
    model["constraints"] = ["squad_size_15", "budget"]
    certificate = certificate_from_solve(
        solver_status="Optimal",
        objective_value=12.0,
        squad=squad,
        lineups=lineups,
        captains=captains,
        model=model,
    )
    assert certificate["optimality_proven"] is False
    assert "complete reduced model" in certificate["model_check"]["reason"]


def test_mismatched_objective_is_not_optimal():
    squad, lineups, captains = _legal_solution()
    certificate = certificate_from_solve(
        solver_status="Optimal",
        objective_value=12.0,
        squad=squad,
        lineups=lineups,
        captains=captains,
        model=wildcard_model(99.0),
    )
    assert certificate["optimality_proven"] is False
    assert "does not match" in certificate["model_check"]["reason"]


def test_non_finite_objective_is_not_optimal():
    squad, lineups, captains = _legal_solution()
    certificate = certificate_from_solve(
        solver_status="Optimal",
        objective_value=math.nan,
        squad=squad,
        lineups=lineups,
        captains=captains,
        model=wildcard_model(math.nan),
    )
    assert certificate["optimality_proven"] is False
    assert certificate["objective_value"] is None


def test_complete_reduced_model_can_certify_without_claiming_full_rules():
    squad, lineups, captains = _legal_solution()
    certificate = certificate_from_solve(
        solver_status="Optimal",
        objective_value=12.0,
        squad=squad,
        lineups=lineups,
        captains=captains,
        model=wildcard_model(12.0),
    )
    assert certificate["optimality_proven"] is False
    assert certificate["certificate"] == "NOT_CERTIFIED"
    assert certificate["claim_scope"] == "reduced_wildcard_milp"
    assert certificate["full_rule_optimal"] is False
    assert certificate["reduced_model_checked"] is True
    assert certificate["admissible"] is False
    assert set(REQUIRED_MODEL_CONSTRAINTS) == set(wildcard_model(12.0)["constraints"])
    assert certificate["model_check"]["valid"] is True
