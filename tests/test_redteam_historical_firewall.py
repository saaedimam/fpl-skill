#!/usr/bin/env python3
"""Adversarial Red-Team suite targeting Phase 2 Historical Data Layer & Temporal Firewall.

Attempts to defeat:
 1. Direct future-datum injection past cutoff
 2. Future timestamp manipulation & sub-second precision leaks
 3. Timezone / UTC boundary errors (offsets, non-UTC representations)
 4. Naive vs aware datetime inconsistencies
 5. Dataset deserialization bypass with injected payloads
 6. Tampered provenance and hash mismatches
 7. Future data hidden inside nested payloads
 8. Future data introduced after the firewall / mutation of returned state
 9. Mutable-object / reference bypasses
10. Replay-context manipulation
11. Serialization / deserialization temporal bypass
12. Direct InformationSet construction attempting to bypass firewall
13. Empty / missing / malformed timestamps
14. Duplicate / conflicting snapshots at same timestamp
15. Out-of-order historical events
16. Altered future record timestamp vs internal event mismatch
17. Future information encoded indirectly in aggregate fields
"""
import copy
import hashlib
import json
import pytest
from datetime import datetime, timezone, timedelta

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


def make_snap(
    snapshot_id: str,
    observed_at: str,
    event: int,
    data: dict,
    record_type: str = "bootstrap_static",
    source_uri: str = "https://fantasy.premierleague.com/api/bootstrap-static/",
) -> ImmutableSnapshot:
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


# ---------------------------------------------------------------------------
# Vector 1: Direct future-datum injection past cutoff
# ---------------------------------------------------------------------------
def test_redteam_direct_future_injection():
    cutoff = "2026-09-01T10:00:00Z"
    future_time = "2026-09-01T10:00:01Z"  # +1 second
    snap = make_snap("future_1", future_time, 4, {"points": 10})

    fw = TemporalFirewall(cutoff)
    with pytest.raises(TemporalLeakageError):
        fw.validate_snapshot(snap)


# ---------------------------------------------------------------------------
# Vector 2: Future timestamp manipulation & sub-second precision leaks
# ---------------------------------------------------------------------------
def test_redteam_microsecond_future_leak():
    cutoff = "2026-09-01T10:00:00.000000Z"
    micro_future = "2026-09-01T10:00:00.000001Z"
    snap = make_snap("micro_future", micro_future, 4, {"points": 10})

    fw = TemporalFirewall(cutoff)
    with pytest.raises(TemporalLeakageError):
        fw.validate_snapshot(snap)


# ---------------------------------------------------------------------------
# Vector 3: Timezone / UTC boundary errors (e.g. +05:00 vs UTC)
# ---------------------------------------------------------------------------
def test_redteam_timezone_conversion_leak():
    # Cutoff is 10:00:00 UTC
    cutoff = "2026-09-01T10:00:00Z"
    # 15:30:00 +05:00 is 10:30:00 UTC (+30 min leak in local time mask)
    offset_future = "2026-09-01T15:30:00+05:00"
    snap = make_snap("tz_future", offset_future, 4, {"points": 10})

    fw = TemporalFirewall(cutoff)
    with pytest.raises(TemporalLeakageError):
        fw.validate_snapshot(snap)


# ---------------------------------------------------------------------------
# Vector 4: Naive vs Aware datetime parsing
# ---------------------------------------------------------------------------
def test_redteam_naive_datetime_handling():
    dt_aware = parse_iso_utc("2026-09-01T10:00:00Z")
    assert dt_aware.tzinfo is not None
    assert dt_aware.tzinfo == timezone.utc

    # Raw parsing of string without tz must safely normalize to UTC
    dt_normalized = parse_iso_utc("2026-09-01T10:00:00")
    assert dt_normalized.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# Vector 5: Dataset deserialization bypass with tampered future payloads
# ---------------------------------------------------------------------------
def test_redteam_deserialization_tampered_hash_fails():
    ds = VersionedHistoricalDataset("v1")
    snap = make_snap("s1", "2026-09-01T08:00:00Z", 4, {"x": 1})
    ds.add_snapshot(snap)

    ds_dict = ds.to_dict()
    # Maliciously modify the snapshot data inside serialized dict without updating content_hash
    ds_dict["snapshots"][0]["data"]["x"] = 999

    with pytest.raises(SnapshotIntegrityError):
        VersionedHistoricalDataset.from_dict(ds_dict)


# ---------------------------------------------------------------------------
# Vector 6: Tampered provenance and hash mismatches
# ---------------------------------------------------------------------------
def test_redteam_tampered_provenance_timestamp_mismatch():
    # Attempt to create snapshot with mismatched observed_at vs provenance.observed_at
    src_hash = compute_sha256({"x": 1})
    prov = Provenance(
        source_uri="uri",
        observed_at="2026-09-01T08:00:00Z",
        source_hash=src_hash,
        record_type="test",
    )
    with pytest.raises(ValueError):
        ImmutableSnapshot(
            snapshot_id="s1",
            observed_at="2026-09-01T09:00:00Z",  # mismatch!
            event=4,
            data={"x": 1},
            provenance=prov,
        )


# ---------------------------------------------------------------------------
# Vector 7: Future data hidden inside nested payloads
# ---------------------------------------------------------------------------
def test_redteam_nested_future_data_isolation():
    ds = VersionedHistoricalDataset("v1")
    # Pre-deadline snapshot
    ds.add_snapshot(make_snap("pre", "2026-09-01T08:00:00Z", 4, {
        "elements": [{"id": 1, "now_cost": 100}]
    }))
    # Future snapshot containing nested hidden actuals
    ds.add_snapshot(make_snap("post", "2026-09-01T18:00:00Z", 4, {
        "elements": [{"id": 1, "hidden_future_stats": {"goals": 3, "bonus": 3}}]
    }))

    builder = InformationSetBuilder(ds)
    info_set = builder.build_information_set("2026-09-01T10:00:00Z")

    el = info_set.get_element(1)
    assert el is not None
    assert "hidden_future_stats" not in el
    assert el["now_cost"] == 100


# ---------------------------------------------------------------------------
# Vector 8 & 9: Mutation of returned state / Reference leakage bypass
# ---------------------------------------------------------------------------
def test_redteam_returned_state_mutation_isolation():
    ds = VersionedHistoricalDataset("v1")
    snap = make_snap("s1", "2026-09-01T08:00:00Z", 4, {
        "elements": [{"id": 1, "now_cost": 100}]
    })
    ds.add_snapshot(snap)

    builder = InformationSetBuilder(ds)
    info_set = builder.build_information_set("2026-09-01T10:00:00Z")

    # Consumer attempts to mutate returned element dict in place
    el = info_set.get_element(1)
    el["now_cost"] = 9999

    # Fresh retrieval from same info_set or snapshot must be completely unaffected
    el_fresh = info_set.get_element(1)
    assert el_fresh["now_cost"] == 100
    assert snap.data["elements"][0]["now_cost"] == 100


# ---------------------------------------------------------------------------
# Vector 10: Replay context manipulation
# ---------------------------------------------------------------------------
def test_redteam_replay_context_tampering():
    ctx = ReplayContext(
        data_version="d1",
        feature_version="f1",
        seed=42,
    )
    # Frozen dataclass must reject attribute assignment
    with pytest.raises(AttributeError):
        ctx.seed = 999


# ---------------------------------------------------------------------------
# Vector 11 & 12: Direct InformationSet construction attempting to smuggle future records
# ---------------------------------------------------------------------------
def test_redteam_direct_infoset_construction_firewall():
    cutoff = "2026-09-01T10:00:00Z"
    future_prov = {
        "source_uri": "uri",
        "observed_at": "2026-09-01T11:00:00Z",
        "source_hash": "hash",
        "record_type": "type",
    }
    with pytest.raises(TemporalLeakageError):
        InformationSet(
            decision_timestamp_utc=cutoff,
            gameweek=4,
            data={},
            provenance_records=[future_prov],
            replay_context=ReplayContext("d1", "f1"),
        )


# ---------------------------------------------------------------------------
# Vector 13: Empty / missing / malformed timestamps
# ---------------------------------------------------------------------------
def test_redteam_malformed_timestamps():
    with pytest.raises(ValueError):
        parse_iso_utc("")

    with pytest.raises(ValueError):
        parse_iso_utc("invalid-date-string")


# ---------------------------------------------------------------------------
# Vector 14 & 15: Out-of-order historical events & Timezone Instant Sorting
# ---------------------------------------------------------------------------
def test_redteam_out_of_order_snapshot_sorting():
    ds = VersionedHistoricalDataset("v1")
    # Add snapshots in reverse chronological order
    ds.add_snapshot(make_snap("s2", "2026-09-01T09:00:00Z", 4, {"elements": [{"id": 1, "price": 105}]}))
    ds.add_snapshot(make_snap("s1", "2026-09-01T08:00:00Z", 4, {"elements": [{"id": 1, "price": 100}]}))

    builder = InformationSetBuilder(ds)
    info_set = builder.build_information_set("2026-09-01T10:00:00Z")

    # Chronological sort must ensure s2 (latest pre-deadline) takes precedence over s1
    el = info_set.get_element(1)
    assert el["price"] == 105


def test_redteam_timezone_offset_lexical_vs_instant_sorting():
    ds = VersionedHistoricalDataset("v1")
    # 09:00:00Z is 09:00 UTC
    # 13:30:00+05:00 is 08:30 UTC (earlier instant, but lexical string starts with '13'!)
    snap_earlier = make_snap("s_early", "2026-09-01T13:30:00+05:00", 4, {"elements": [{"id": 1, "status": "d"}]})
    snap_later = make_snap("s_late", "2026-09-01T09:00:00Z", 4, {"elements": [{"id": 1, "status": "a"}]})

    ds.add_snapshot(snap_earlier)
    ds.add_snapshot(snap_later)

    builder = InformationSetBuilder(ds)
    info_set = builder.build_information_set("2026-09-01T10:00:00Z")

    # Latest instant (09:00 UTC) must override earlier instant (08:30 UTC)
    el = info_set.get_element(1)
    assert el["status"] == "a"


# ---------------------------------------------------------------------------
# Vector 16: Future record with altered timestamp (Provenance vs snapshot check)
# ---------------------------------------------------------------------------
def test_redteam_altered_provenance_hash_check():
    # If an attacker alters the payload to include future points but keeps original hash, integrity check fails
    data_orig = {"points": 0}
    data_tampered = {"points": 20}  # future leak

    prov = Provenance(
        source_uri="uri",
        observed_at="2026-09-01T08:00:00Z",
        source_hash=compute_sha256(data_orig),  # original hash!
        record_type="test",
    )

    with pytest.raises(SnapshotIntegrityError):
        ImmutableSnapshot(
            snapshot_id="s_tamper",
            observed_at="2026-09-01T08:00:00Z",
            event=4,
            data=data_tampered,
            provenance=prov,
        )


# ---------------------------------------------------------------------------
# Vector 17: Tampered Top-Level Dataset Hash & Heterogeneous Key Serialization
# ---------------------------------------------------------------------------
def test_redteam_dataset_hash_tamper_detection():
    ds = VersionedHistoricalDataset("v1")
    ds.add_snapshot(make_snap("s1", "2026-09-01T08:00:00Z", 4, {"x": 1}))
    d_dict = ds.to_dict()

    # Tamper with dataset_hash
    d_dict["dataset_hash"] = "tampered_dataset_hash_value"
    with pytest.raises(SnapshotIntegrityError):
        VersionedHistoricalDataset.from_dict(d_dict)


def test_redteam_heterogeneous_key_normalization():
    ds = VersionedHistoricalDataset("v1")
    # Add snapshot with integer keys in dict form
    ds.add_snapshot(make_snap("s1", "2026-09-01T08:00:00Z", 4, {
        "elements": {101: {"name": "Saka"}, "102": {"name": "Saliba"}}
    }))
    builder = InformationSetBuilder(ds)
    info_set = builder.build_information_set("2026-09-01T10:00:00Z")

    assert info_set.get_element(101)["name"] == "Saka"
    assert info_set.get_element("102")["name"] == "Saliba"
    # Invariant: Hashing must succeed without TypeError
    assert len(info_set.info_set_hash) == 64
