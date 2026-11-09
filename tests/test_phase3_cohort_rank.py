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
        source_url="https://fantasy.premierleague.com/api/leagues-classic/314/standings/",
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
        CohortSnapshot("x", 1, "2026-11-08T10:00:00Z", ({"entry_id": 1}, {"entry_id": 1}),
            source_url="https://fantasy.premierleague.com/api/leagues-classic/314/standings/",
            content_hash="sha256:x")
    with pytest.raises(ValueError):
        CohortSnapshot("x", 1, "2026-11-08T10:00:00Z", ({"entry_id": 1},),
            source_url="https://fantasy.premierleague.com/api/leagues-classic/314/standings/",
            content_hash="sha256:x", coverage=1.1)


def test_cohort_rejects_missing_captain_and_duplicate_position():
    bad = CohortSnapshot("bad", 1, "2026-11-08T10:00:00Z", ({"entry_id": 1, "picks": [_p(1, 1, cap=True)]},),
        source_url="https://fantasy.premierleague.com/api/leagues-classic/314/standings/",
        content_hash="sha256:bad")
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
        source_url="https://fantasy.premierleague.com/api/leagues-classic/314/standings/",
        content_hash="sha256:sample",
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
    cohort = CohortSnapshot("sample", 1, "2026-11-08T10:00:00Z", (
        {"entry_id": 2, "current_points": 10, "current_rank": 2,
         "picks": [_p(2, 1, True)]},
    ), source_url="https://fantasy.premierleague.com/api/leagues-classic/314/standings/",
       content_hash="sha256:sample")
    own = {"entry_id": 1, "current_points": 10, "current_rank": 1,
           "picks": [_p(1, 1, True)]}
    with pytest.raises(ValueError, match="missing player distributions"):
        simulate_rank(own, cohort, {1: {"mean": 5, "variance": 1}}, simulations=100)


def test_start_probability_map_must_be_complete():
    with pytest.raises(ValueError, match="missing start probability"):
        cohort_ownership(_snapshot(), {1: 0.9})


def test_cohort_combinations_use_exact_joint_counts():
    from fpl_skill.phase3_cohort_rank import cohort_player_combinations
    result = cohort_player_combinations(
        _snapshot(), size=2, requested=[[1, 2], [1, 3], [2, 4]],
    )
    rows = {tuple(x["player_ids"]): x for x in result["combinations"]}
    assert rows[(1, 2)]["holding_entries"] == 2
    assert rows[(1, 2)]["cohort_pct"] == 100.0
    assert rows[(1, 3)]["holding_entries"] == 1
    assert "no independence assumption" in result["method"]


def test_cohort_combinations_reject_duplicate_or_invalid_groups():
    from fpl_skill.phase3_cohort_rank import cohort_player_combinations
    with pytest.raises(ValueError, match="unique"):
        cohort_player_combinations(_snapshot(), requested=[[1, 1]])


def test_cohort_combinations_fail_closed_on_malformed_pick_rows():
    from fpl_skill.phase3_cohort_rank import cohort_player_combinations
    snap = CohortSnapshot(
        "bad", 1, "2026-11-08T10:00:00Z",
        ({"entry_id": 1, "picks": [{"element": 1}, None]},),
        source_url="https://fantasy.premierleague.com/api/leagues-classic/314/standings/",
        content_hash="sha256:bad",
    )
    with pytest.raises(ValueError, match="malformed pick row"):
        cohort_player_combinations(snap)


def test_global_ownership_is_kept_separate_from_cohort_eo():
    from fpl_skill.phase3_cohort_rank import attach_global_ownership, cohort_ownership
    cohort = cohort_ownership(_snapshot())
    result = attach_global_ownership(cohort, {
        "source_url": "https://fantasy.premierleague.com/api/bootstrap-static/",
        "captured_at": "2026-11-08T10:00:00Z",
        "content_hash": "sha256:bootstrap",
        "global_ownership_pct": {1: 75.5, 2: 40.0},
    })
    assert result["players"][1]["global_ownership_pct"] == 75.5
    assert result["players"][1]["expected_effective_ownership_pct"] == 150.0
    assert "not rank-cohort ownership" in result["global_ownership"]["semantics"]


def test_cohort_snapshot_deep_freezes_entry_and_pick_data():
    entry = {"entry_id": 77, "picks": [_p(1, 1, cap=True), _p(2, 2, vice=True)]}
    snapshot = CohortSnapshot(
        "immutable", 1, "2026-11-08T10:00:00Z", (entry,),
        source_url="https://fantasy.premierleague.com/api/leagues-classic/314/standings/",
        content_hash="sha256:immutable",
    )
    entry["picks"][0]["element"] = 999
    assert snapshot.entries[0]["picks"][0]["element"] == 1
    with pytest.raises(TypeError):
        snapshot.entries[0]["picks"][0]["element"] = 3


def test_cohort_snapshot_rejects_timezone_naive_capture():
    with pytest.raises(ValueError, match="timezone-aware"):
        CohortSnapshot(
            "naive", 1, "2026-11-08T10:00:00", ({"entry_id": 1, "picks": []},),
            source_url="https://fantasy.premierleague.com/api/leagues-classic/314/standings/",
            content_hash="sha256:naive",
        )
