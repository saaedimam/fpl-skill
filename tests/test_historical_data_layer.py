#!/usr/bin/env python3
"""Adversarial validation tests for Phase 2 Leakage-Proof Historical Data Layer.

Enforces:
1. Mandatory Temporal Invariant: I_t ⊆ D_≤t AND I_t ∩ D_>t = ∅
2. Adversarial Future-Data Injection -> Fail-Stop TemporalLeakageError
3. 8-Element Reproducibility Tuple & Deterministic Replay
4. Immutable Provenance & Content Hash Integrity
5. Temporal Firewall Pre-Model Interception
"""
import copy
import hashlib
import json
import os
import pytest
from datetime import datetime, timezone

from fpl_skill.historical import (
    DeterministicReplayAPI,
    ImmutableSnapshot,
    InformationSet,
    InformationSetBuilder,
    Provenance,
    ProvenancedDatum,
    ProvenanceError,
    ReplayContext,
    SnapshotIntegrityError,
    TemporalFirewall,
    TemporalLeakageError,
    VersionedHistoricalDataset,
    compute_environment_fingerprint,
    compute_sha256,
    format_iso_utc,
    parse_iso_utc,
)


def make_snapshot(
    snapshot_id: str,
    observed_at: str,
    event: int,
    data: dict,
    record_type: str = "elements",
    source_uri: str = "https://fantasy.premierleague.com/api/bootstrap-static/",
) -> ImmutableSnapshot:
    """Helper to construct a valid ImmutableSnapshot."""
    src_hash = compute_sha256(data)
    prov = Provenance(
        source_uri=source_uri,
        observed_at=observed_at,
        source_hash=src_hash,
        record_type=record_type,
        authoritative=True,
    )
    return ImmutableSnapshot(
        snapshot_id=snapshot_id,
        observed_at=observed_at,
        event=event,
        data=data,
        provenance=prov,
    )


@pytest.fixture
def sample_season_dataset() -> VersionedHistoricalDataset:
    """Construct a multi-gameweek synthetic historical dataset."""
    ds = VersionedHistoricalDataset(data_version="2026-27-synthetic-v1.0")

    # GW1 deadline: 2026-08-15T10:00:00Z
    # GW1 pre-deadline data
    ds.add_snapshot(
        make_snapshot(
            snapshot_id="gw1_bootstrap_0814",
            observed_at="2026-08-14T12:00:00Z",
            event=1,
            data={"elements": [{"id": 101, "web_name": "Haaland", "now_cost": 150, "status": "a"}]},
            record_type="bootstrap_static",
        )
    )
    ds.add_snapshot(
        make_snapshot(
            snapshot_id="gw1_fixtures_0814",
            observed_at="2026-08-14T12:05:00Z",
            event=1,
            data={"fixtures": [{"id": 1, "event": 1, "team_h": 1, "team_a": 2}]},
            record_type="fixtures",
        )
    )

    # GW1 post-deadline / match outcomes (2026-08-15T18:00:00Z)
    ds.add_snapshot(
        make_snapshot(
            snapshot_id="gw1_actual_results_0815",
            observed_at="2026-08-15T18:00:00Z",
            event=1,
            data={"elements": [{"id": 101, "total_points": 13, "goals_scored": 2}]},
            record_type="bootstrap_static",
        )
    )

    # GW2 deadline: 2026-08-22T10:00:00Z
    # GW2 pre-deadline injury news observed at 2026-08-21T15:00:00Z
    ds.add_snapshot(
        make_snapshot(
            snapshot_id="gw2_injury_0821",
            observed_at="2026-08-21T15:00:00Z",
            event=2,
            data={"elements": [{"id": 101, "status": "d", "chance_of_playing": 75}]},
            record_type="bootstrap_static",
        )
    )

    # GW2 post-deadline actual points (2026-08-22T20:00:00Z)
    ds.add_snapshot(
        make_snapshot(
            snapshot_id="gw2_actual_results_0822",
            observed_at="2026-08-22T20:00:00Z",
            event=2,
            data={"elements": [{"id": 101, "total_points": 2, "minutes": 45}]},
            record_type="bootstrap_static",
        )
    )

    return ds


# ---------------------------------------------------------------------------
# TEST 1: Strict Invariant Enforcement (I_t ⊆ D_≤t AND I_t ∩ D_>t = ∅)
# ---------------------------------------------------------------------------
def test_temporal_cutoff_invariant(sample_season_dataset):
    """Verify that I_t contains ONLY data observed on or before cutoff t."""
    cutoff_gw1_deadline = "2026-08-15T10:00:00Z"
    builder = InformationSetBuilder(sample_season_dataset)
    info_set = builder.build_information_set(decision_timestamp_utc=cutoff_gw1_deadline, gameweek=1)

    # Must contain exactly 2 pre-deadline snapshots
    assert len(info_set.provenance_records) == 2
    for prov in info_set.provenance_records:
        obs_dt = parse_iso_utc(prov["observed_at"])
        cutoff_dt = parse_iso_utc(cutoff_gw1_deadline)
        assert obs_dt <= cutoff_dt, f"Observed {prov['observed_at']} > Cutoff {cutoff_gw1_deadline}"

    # Haaland must not have GW1 match outcomes (13 points) or GW2 injury
    el = info_set.get_element(101)
    assert el is not None
    assert el["web_name"] == "Haaland"
    assert el["status"] == "a"
    assert "total_points" not in el  # Outcome occurred post-deadline


# ---------------------------------------------------------------------------
# TEST 2: Adversarial Future-Data Injection -> Fail-Stop TemporalLeakageError
# ---------------------------------------------------------------------------
def test_adversarial_future_injection_raises_leakage_error(sample_season_dataset):
    """Adversary deliberately attempts to inject future match points into GW1 deadline info set."""
    cutoff_gw1_deadline = "2026-08-15T10:00:00Z"

    # Maliciously crafted snapshot with future timestamp (GW1 match result)
    future_snap = make_snapshot(
        snapshot_id="leaked_future_points",
        observed_at="2026-08-15T18:00:00Z",
        event=1,
        data={"elements": [{"id": 101, "total_points": 13}]},
        record_type="bootstrap_static",
    )

    firewall = TemporalFirewall(cutoff_utc=cutoff_gw1_deadline)

    # Firewall must intercept and block with TemporalLeakageError
    with pytest.raises(TemporalLeakageError) as exc_info:
        firewall.validate_snapshot(future_snap)

    assert "FIREWALL BLOCKED LEAKAGE" in str(exc_info.value)
    assert "leaked_future_points" in str(exc_info.value)

    # Test ProvenancedDatum direct cutoff enforcement
    datum = future_snap.to_datum()
    with pytest.raises(TemporalLeakageError) as exc_info2:
        datum.enforce_temporal_cutoff(cutoff_gw1_deadline)
    assert "LEAKAGE DETECTED" in str(exc_info2.value)


def test_adversarial_tampered_info_set_provenance_raises_leakage_error():
    """Adversary attempts to construct an InformationSet with smuggled future provenance."""
    cutoff = "2026-08-15T10:00:00Z"
    future_prov = {
        "source_uri": "https://fantasy.premierleague.com/api/bootstrap-static/",
        "observed_at": "2026-08-15T10:00:01Z",  # 1 second in the future!
        "source_hash": "abc12345",
        "record_type": "elements",
        "authoritative": True,
    }
    replay_ctx = ReplayContext(
        data_version="test-v1",
        feature_version="f-v1",
    )

    with pytest.raises(TemporalLeakageError) as exc_info:
        InformationSet(
            decision_timestamp_utc=cutoff,
            gameweek=1,
            data={"elements": {}},
            provenance_records=[future_prov],
            replay_context=replay_ctx,
        )
    assert "CRITICAL FIREWALL LEAKAGE" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TEST 3: Deterministic Replay & 8-Element Reproducibility Tuple
# ---------------------------------------------------------------------------
def test_deterministic_replay_byte_for_byte(sample_season_dataset):
    """Verify that repeated replays on identical tuples yield identical hashes."""
    api = DeterministicReplayAPI(sample_season_dataset)
    cutoff = "2026-08-21T18:00:00Z"
    config = {"optimizer_mode": "test_only", "horizon": 3}

    # Run 1
    run1 = api.replay_decision_state(decision_timestamp_utc=cutoff, gameweek=2, config=config, seed=123)
    # Run 2 (identical parameters)
    run2 = api.replay_decision_state(decision_timestamp_utc=cutoff, gameweek=2, config=config, seed=123)

    # Invariant: Must match exactly byte-for-byte in serialized hash
    assert run1.info_set_hash == run2.info_set_hash
    assert run1.to_dict() == run2.to_dict()
    assert run1.replay_context.data_version == "2026-27-synthetic-v1.0"
    assert run1.replay_context.model_version == "Phase2-data-only"
    assert run1.replay_context.policy_version == "none"
    assert len(run1.replay_context.environment_fingerprint) == 64


def test_reproducibility_diff_on_seed_or_config(sample_season_dataset):
    """Verify that altering seed or config deterministically changes replay context hash."""
    api = DeterministicReplayAPI(sample_season_dataset)
    cutoff = "2026-08-21T18:00:00Z"

    r1 = api.replay_decision_state(decision_timestamp_utc=cutoff, gameweek=2, seed=42)
    r2 = api.replay_decision_state(decision_timestamp_utc=cutoff, gameweek=2, seed=999)

    assert r1.replay_context.seed != r2.replay_context.seed
    assert r1.info_set_hash != r2.info_set_hash


# ---------------------------------------------------------------------------
# TEST 4: Immutable Provenance & Snapshot Integrity
# ---------------------------------------------------------------------------
def test_snapshot_content_hash_integrity():
    """Verify that tampering with snapshot content fails integrity verification."""
    snap = make_snapshot(
        snapshot_id="s1",
        observed_at="2026-08-01T12:00:00Z",
        event=1,
        data={"team": "Arsenal", "rank": 1},
    )
    assert snap.verify_integrity() is True

    # Attempt to tamper with underlying dict
    tampered_data = copy.deepcopy(snap.data)
    tampered_data["rank"] = 2

    # Construct tampered snapshot with original hash
    object.__setattr__(snap, "data", tampered_data)
    with pytest.raises(SnapshotIntegrityError):
        snap.verify_integrity()


def test_dataset_serialization_roundtrip(sample_season_dataset):
    """Verify lossless serialization and deserialization of historical datasets."""
    d_dict = sample_season_dataset.to_dict()
    reconstructed = VersionedHistoricalDataset.from_dict(d_dict)

    assert reconstructed.data_version == sample_season_dataset.data_version
    assert reconstructed.dataset_hash == sample_season_dataset.dataset_hash
    assert len(reconstructed.snapshots) == len(sample_season_dataset.snapshots)
    for s in reconstructed.snapshots:
        assert s.verify_integrity() is True


# ---------------------------------------------------------------------------
# TEST 5: Chronological Progression Across Gameweek Deadlines
# ---------------------------------------------------------------------------
def test_walk_forward_state_evolution(sample_season_dataset):
    """Verify that state monotonically expands over time without backward leakage."""
    api = DeterministicReplayAPI(sample_season_dataset)

    # GW1 deadline state
    info_gw1 = api.replay_decision_state("2026-08-15T10:00:00Z", gameweek=1)
    el_gw1 = info_gw1.get_element(101)
    assert el_gw1["status"] == "a"
    assert info_gw1.data["observed_snapshots_count"] == 2

    # GW2 deadline state (after GW1 results & GW2 pre-deadline injury news)
    info_gw2 = api.replay_decision_state("2026-08-22T09:00:00Z", gameweek=2)
    el_gw2 = info_gw2.get_element(101)
    # Haaland should now have the latest pre-deadline update (injury status 'd', 75%)
    assert el_gw2["status"] == "d"
    assert el_gw2["chance_of_playing"] == 75
    # Should include 4 snapshots (GW1 pre + GW1 match results + GW2 injury news)
    assert info_gw2.data["observed_snapshots_count"] == 4
    # But strictly NOT GW2 match outcomes (which occurred 2026-08-22T20:00:00Z)
    assert "minutes" not in el_gw2
