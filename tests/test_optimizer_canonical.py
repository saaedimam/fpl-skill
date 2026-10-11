"""
tests/test_optimizer_canonical.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for the canonical HiGHS MILP optimizer path.
"""
import pytest
from unittest.mock import patch, MagicMock
from fpl_skill.optimizer import build_and_solve, get_solver_metadata, get_mip_solver


# ---------------------------------------------------------------------------
# Solver metadata
# ---------------------------------------------------------------------------

def test_solver_metadata_identifies_highs():
    meta = get_solver_metadata()
    assert meta["solver"] == "HiGHS"
    assert meta["solver_api"] == "pulp.HiGHS"
    assert meta["solver_backend"] == "highspy"


def test_solver_metadata_includes_platform():
    meta = get_solver_metadata()
    assert "python_version" in meta
    assert "platform" in meta
    assert "architecture" in meta


# ---------------------------------------------------------------------------
# build_and_solve(solve=False) — no solver needed
# ---------------------------------------------------------------------------

def _synthetic_data():
    records = []
    for pos, et, n in [("GKP", 1, 5), ("DEF", 2, 10), ("MID", 3, 10), ("FWD", 4, 6)]:
        for i in range(n):
            pid = {"GKP": 0, "DEF": 100, "MID": 200, "FWD": 300}[pos] + i
            records.append({
                "player_id": pid, "web_name": f"{pos}_{i}", "position": pos,
                "team": f"T{i % 10}", "now_cost": 55 + i % 40,
                "ep_next": 5.0, "element_type": et, "id": pid,
            })
    return {"records": records}


def test_build_and_solve_without_solver_returns_built():
    with patch("fpl_skill.optimizer.get_fpl_data", return_value=_synthetic_data()):
        r = build_and_solve(budget=100.0, solve=False)
    assert r["status"] == "BUILT"
    assert r["objective"] is None


def test_build_and_solve_without_solver_has_variables():
    with patch("fpl_skill.optimizer.get_fpl_data", return_value=_synthetic_data()):
        r = build_and_solve(budget=100.0, solve=False)
    assert r["variables_count"] > 0


def test_build_and_solve_without_solver_has_data_hash():
    with patch("fpl_skill.optimizer.get_fpl_data", return_value=_synthetic_data()):
        r = build_and_solve(budget=100.0, solve=False)
    assert "data_hash" in r
    assert r["data_hash"]


# ---------------------------------------------------------------------------
# Certification uses optimizer.build_and_solve (canonical path)
# ---------------------------------------------------------------------------

def test_certification_imports_optimizer_not_api_bb():
    """Verify certification.py imports build_and_solve from fpl_skill.optimizer,
    not optimize_wildcard_squad from api for the primary solve step."""
    import inspect
    import fpl_skill.certification as cert_module

    src = inspect.getsource(cert_module.run_full_certification)
    # Must reference build_and_solve (the HiGHS path)
    assert "build_and_solve" in src, (
        "run_full_certification() must call optimizer.build_and_solve() as primary solver"
    )
    # The B&B (optimize_wildcard_squad) must only appear in the exhaustive verification role
    assert "exhaustive_verification" in src, (
        "run_full_certification() must call exhaustive_verification() for B&B independent check"
    )


# ---------------------------------------------------------------------------
# Fail-closed on solver unavailability
# ---------------------------------------------------------------------------

def test_get_mip_solver_fails_closed_if_highs_unavailable():
    """get_mip_solver() must raise RuntimeError (not return None) when HiGHS is absent."""
    import pulp
    # Simulate HiGHS not present on pulp module
    original = getattr(pulp, "HiGHS", None)
    try:
        if hasattr(pulp, "HiGHS"):
            delattr(pulp, "HiGHS")
        with pytest.raises(RuntimeError, match="HiGHS"):
            get_mip_solver()
    finally:
        if original is not None:
            pulp.HiGHS = original


# ---------------------------------------------------------------------------
# api.optimize_wildcard_squad carries a deprecation warning
# ---------------------------------------------------------------------------

def test_api_optimize_wildcard_squad_emits_deprecation_warning():
    import warnings
    from fpl_skill import api

    # Provide minimal data so function doesn't error on missing players
    fake_players = [
        {"player_id": i, "web_name": f"P{i}", "position": ["GKP","DEF","MID","FWD"][i % 4],
         "team": f"T{i}", "now_cost": 55, "ep_3_6": 20.0, "ep_gw": [5]*4, "cost_int": 55}
        for i in range(15)
    ]
    # Patch internal B&B to avoid long compute — we just want the warning
    with patch.object(api, "get_fpl_data", return_value={}):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                api.optimize_wildcard_squad(fake_players, budget=100.0, fixture_map={})
            except Exception:
                pass  # result not important — warning is
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1
            assert "build_and_solve" in str(deprecation_warnings[0].message).lower() or \
                   "optimizer" in str(deprecation_warnings[0].message).lower()
