"""P3-01/P3-02 deterministic tests for cohort EO and rank simulation."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fpl_skill.phase3_cohort_rank import CohortSnapshot, cohort_ownership, simulate_rank


def _p(pid, pos, cap=False, vice=False, mult=1):
    return {"element": pid, "position": pos, "multiplier": mult,
            "is_captain": cap, "is_vice_captain": vice}


def _snapshot():
    return CohortSnapshot(
        cohort_id="top-2",
        event=4,
        captured_at="2026-11-08T10:00:00Z",
        entries=(
            {"entry_id": 10, "picks": [_p(1, 1, True), _p(2, 2, vice=True), _p(3, 12, mult=0)]},
            {"entry_id": 11, "picks": [_p(1, 1, vice=True), _p(2, 2, True), _p(4, 12, mult=0)]},
        ),
        coverage=0.8,
        content_hash="sha256:test",
    )


def test_cohort_ownership_denominator_and_captain_exposure():
    result = cohort_ownership(_snapshot())
    assert result["sample_size"] == 2
    players = result["players"]
    assert players[1]["ownership_pct"] == 100.0
    assert players[1]["starter_pct"] == 100.0
    assert players[1]["captain_pct"] == 50.0
    assert players[1]["expected_effective_ownership_pct"] == 150.0
    assert players[2]["expected_effective_ownership_pct"] == 150.0


def test_expected_eo_accounts_for_captain_and_vice_fallback():
    result = cohort_ownership(_snapshot(), {1: 0.5, 2: 0.8})
    # player 1: two starter exposures (0.5 each), one captain extra (0.5),
    # and vice fallback only when player 2 fails (0.2 * 0.5).
    assert result["players"][1]["expected_effective_ownership_pct"] == pytest.approx(80.0)
    # player 2: two starter exposures (0.8 each), one captain extra (0.8),
    # and vice fallback only when player 1 fails (0.5 * 0.8).
    assert result["players"][2]["expected_effective_ownership_pct"] == pytest.approx(140.0)


def test_snapshot_rejects_duplicate_entries_and_bad_coverage():
    with pytest.raises(ValueError):
        CohortSnapshot("x", 1, "now", ({"entry_id": 1}, {"entry_id": 1}))
    with pytest.raises(ValueError):
        CohortSnapshot("x", 1, "now", ({"entry_id": 1},), coverage=1.1)


def test_cohort_rejects_missing_captain_and_duplicate_position():
    bad = CohortSnapshot("bad", 1, "now", ({"entry_id": 1, "picks": [_p(1, 1, cap=True)]},))
    with pytest.raises(ValueError, match="vice-captain"):
        cohort_ownership(bad)


def test_rank_simulation_is_reproducible_and_separates_observed_rank():
    cohort = CohortSnapshot(
        "sample", 5, "2026-11-08T10:00:00Z",
        (
            {"entry_id": 2, "current_points": 100, "current_rank": 2,
             "picks": [_p(1, 1, True), _p(2, 2, vice=True)]},
            {"entry_id": 3, "current_points": 90, "current_rank": 3,
             "picks": [_p(2, 1, True), _p(1, 2, vice=True)]},
        ),
        coverage=0.5,
    )
    own = {"entry_id": 1, "current_points": 95, "current_rank": 2,
           "picks": [_p(1, 1, True), _p(2, 2, vice=True)]}
    dists = {1: {"mean": 6, "variance": 0}, 2: {"mean": 4, "variance": 0}}
    a = simulate_rank(own, cohort, dists, simulations=100, seed=42)
    b = simulate_rank(own, cohort, dists, simulations=100, seed=42)
    assert a == b
    assert a["observed_rank"] == 2
    assert a["forecast_rank"]["p50"] >= 1
    assert a["comparison_sample_size"] == 2


def test_rank_simulation_fails_closed_on_missing_distribution():
    cohort = CohortSnapshot("sample", 1, "now", (
        {"entry_id": 2, "current_points": 10, "current_rank": 2,
         "picks": [_p(2, 1, True)]},
    ))
    own = {"entry_id": 1, "current_points": 10, "current_rank": 1,
           "picks": [_p(1, 1, True)]}
    with pytest.raises(ValueError, match="missing player distributions"):
        simulate_rank(own, cohort, {1: {"mean": 5, "variance": 1}}, simulations=100)
