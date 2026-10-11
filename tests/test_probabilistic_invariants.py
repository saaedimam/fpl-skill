"""
tests/test_probabilistic_invariants.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for PlayerDistribution invariant enforcement.
"""
import pytest
from fpl_skill.probabilistic_ep1 import PlayerDistribution


def _mk_dist(**kwargs):
    base = dict(
        player_id=1, player_name="Test", gw=5, team="ARS", position="MID",
        p10=1.0, p25=3.0, p50=5.0, p75=7.0, p90=9.0,
        mean=5.0, variance=4.0,
    )
    base.update(kwargs)
    return PlayerDistribution(**base)


# ---------------------------------------------------------------------------
# Monotonicity: P10 <= P25 <= P50 <= P75 <= P90
# ---------------------------------------------------------------------------

def test_valid_monotonic_distribution_created():
    d = _mk_dist()
    assert d.p10 <= d.p25 <= d.p50 <= d.p75 <= d.p90


def test_p10_gt_p25_raises():
    with pytest.raises(ValueError, match="monotonic"):
        _mk_dist(p10=5.0, p25=3.0)


def test_p25_gt_p50_raises():
    with pytest.raises(ValueError, match="monotonic"):
        _mk_dist(p25=6.0, p50=5.0)


def test_p50_gt_p75_raises():
    with pytest.raises(ValueError, match="monotonic"):
        _mk_dist(p50=8.0, p75=7.0)


def test_p75_gt_p90_raises():
    with pytest.raises(ValueError, match="monotonic"):
        _mk_dist(p75=10.0, p90=9.0)


def test_equal_percentiles_valid():
    # All same value is technically monotonically non-decreasing
    d = _mk_dist(p10=5.0, p25=5.0, p50=5.0, p75=5.0, p90=5.0, mean=5.0, variance=0.0)
    assert d.p10 == d.p90 == 5.0


# ---------------------------------------------------------------------------
# Variance >= 0
# ---------------------------------------------------------------------------

def test_negative_variance_raises():
    with pytest.raises(ValueError, match="variance must be >= 0"):
        _mk_dist(variance=-1.0)


def test_zero_variance_valid():
    d = _mk_dist(variance=0.0, p10=5.0, p25=5.0, p50=5.0, p75=5.0, p90=5.0, mean=5.0)
    assert d.variance == 0.0
    assert d.std_dev == 0.0


# ---------------------------------------------------------------------------
# Mean >= 0
# ---------------------------------------------------------------------------

def test_negative_mean_raises():
    with pytest.raises(ValueError, match="mean must be >= 0"):
        _mk_dist(mean=-1.0)


def test_zero_mean_valid():
    d = _mk_dist(mean=0.0, p10=0.0, p25=0.0, p50=0.0, p75=0.0, p90=0.0, variance=0.0)
    assert d.mean == 0.0


# ---------------------------------------------------------------------------
# Probability fields in [0, 1]
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["p_zero", "p_haul", "p_bench", "p_injured"])
def test_probability_below_zero_raises(field):
    with pytest.raises(ValueError, match=f"{field} must be in \\[0, 1\\]"):
        _mk_dist(**{field: -0.01})


@pytest.mark.parametrize("field", ["p_zero", "p_haul", "p_bench", "p_injured"])
def test_probability_above_one_raises(field):
    with pytest.raises(ValueError, match=f"{field} must be in \\[0, 1\\]"):
        _mk_dist(**{field: 1.01})


@pytest.mark.parametrize("field,val", [
    ("p_zero", 0.0), ("p_zero", 1.0),
    ("p_haul", 0.0), ("p_haul", 0.5),
    ("p_bench", 0.0), ("p_bench", 1.0),
    ("p_injured", 0.0), ("p_injured", 0.99),
])
def test_probability_boundary_values_valid(field, val):
    # Ensure these do not raise
    _mk_dist(**{field: val})


# ---------------------------------------------------------------------------
# Position normalization: GK → GKP
# ---------------------------------------------------------------------------

def test_position_gk_normalized_to_gkp():
    d = _mk_dist(position="GK")
    assert d.position == "GKP"


def test_position_gkp_preserved():
    d = _mk_dist(position="GKP")
    assert d.position == "GKP"


def test_position_def_mid_fwd_preserved():
    for pos in ("DEF", "MID", "FWD"):
        d = _mk_dist(position=pos)
        assert d.position == pos


# ---------------------------------------------------------------------------
# std_dev computed from variance
# ---------------------------------------------------------------------------

def test_std_dev_computed_from_variance():
    d = _mk_dist(variance=9.0)
    assert abs(d.std_dev - 3.0) < 1e-9
