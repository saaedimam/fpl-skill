"""Immutable source snapshot and dataset versioning."""
from __future__ import annotations

import copy
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .exceptions import ProvenanceError, SnapshotIntegrityError, TemporalLeakageError
from .provenance import (
    Provenance,
    ProvenancedDatum,
    _canonical_json_dumps,
    compute_sha256,
    parse_iso_utc,
)


@dataclass(frozen=True)
class ImmutableSnapshot:
    """An immutable, content-hashed snapshot of historical state at a specific point in time."""
    snapshot_id: str
    observed_at: str          # Timestamp of observation/capture (ISO8601 UTC)
    event: Optional[int]      # Gameweek / event ID if applicable
    data: Dict[str, Any]      # Raw payload dictionary
    provenance: Provenance
    content_hash: str = field(init=False)

    def __post_init__(self):
        # Validate that observed_at matches provenance
        if self.observed_at != self.provenance.observed_at:
            raise ValueError(f"Snapshot observed_at ({self.observed_at}) != provenance ({self.provenance.observed_at})")

        # Deep defensive copy on data to prevent mutation
        object.__setattr__(self, "data", copy.deepcopy(self.data))

        # Validate that provenance source_hash matches data if this is an authoritative raw payload
        computed_data_hash = compute_sha256(self.data)
        if self.provenance.source_hash != computed_data_hash:
            raise SnapshotIntegrityError(
                f"Provenance source_hash ({self.provenance.source_hash}) does not match "
                f"computed data hash ({computed_data_hash}) for snapshot {self.snapshot_id}"
            )

        c_hash = compute_sha256({
            "snapshot_id": self.snapshot_id,
            "observed_at": self.observed_at,
            "event": self.event,
            "data": self.data,
            "provenance": asdict(self.provenance),
        })
        object.__setattr__(self, "content_hash", c_hash)

    def verify_integrity(self) -> bool:
        """Verify snapshot content matches its content hash and provenance source hash."""
        computed_data_hash = compute_sha256(self.data)
        if self.provenance.source_hash != computed_data_hash:
            raise SnapshotIntegrityError(f"Provenance source_hash mismatch for snapshot {self.snapshot_id}")

        expected = compute_sha256({
            "snapshot_id": self.snapshot_id,
            "observed_at": self.observed_at,
            "event": self.event,
            "data": self.data,
            "provenance": asdict(self.provenance),
        })
        if expected != self.content_hash:
            raise SnapshotIntegrityError(f"Integrity check failed for snapshot {self.snapshot_id}")
        return True

    def to_datum(self) -> ProvenancedDatum:
        return ProvenancedDatum(
            datum_id=self.snapshot_id,
            data=copy.deepcopy(self.data),
            provenance=self.provenance,
        )


@dataclass
class VersionedHistoricalDataset:
    """Container for an immutable collection of provenanced historical snapshots with dataset-level hash."""
    data_version: str
    snapshots: List[ImmutableSnapshot] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    dataset_hash: str = field(init=False, default="")

    def __post_init__(self):
        object.__setattr__(self, "metadata", copy.deepcopy(self.metadata))
        self._recompute_dataset_hash()

    def _recompute_dataset_hash(self):
        # Sort snapshots by (parse_iso_utc(observed_at), snapshot_id) for accurate chronological sorting
        sorted_snaps = sorted(self.snapshots, key=lambda s: (parse_iso_utc(s.observed_at), s.snapshot_id))
        hash_payload = {
            "data_version": self.data_version,
            "metadata": self.metadata,
            "snapshots": [s.content_hash for s in sorted_snaps]
        }
        self.dataset_hash = compute_sha256(hash_payload)

    def add_snapshot(self, snapshot: ImmutableSnapshot) -> None:
        """Add an immutable snapshot and update dataset hash."""
        snapshot.verify_integrity()
        self.snapshots.append(snapshot)
        self._recompute_dataset_hash()

    def get_snapshots_before(self, cutoff_utc: str) -> List[ImmutableSnapshot]:
        """Retrieve snapshots strictly observed on or before cutoff_utc (I_t ⊆ D_≤t), sorted chronologically by instant."""
        cutoff_dt = parse_iso_utc(cutoff_utc)
        valid = []
        for s in self.snapshots:
            s_dt = parse_iso_utc(s.observed_at)
            if s_dt <= cutoff_dt:
                valid.append(s)
        return sorted(valid, key=lambda s: (parse_iso_utc(s.observed_at), s.snapshot_id))

    def to_dict(self) -> Dict[str, Any]:
        sorted_snaps = sorted(self.snapshots, key=lambda s: (parse_iso_utc(s.observed_at), s.snapshot_id))
        return {
            "data_version": self.data_version,
            "dataset_hash": self.dataset_hash,
            "metadata": copy.deepcopy(self.metadata),
            "snapshots": [
                {
                    "snapshot_id": s.snapshot_id,
                    "observed_at": s.observed_at,
                    "event": s.event,
                    "data": copy.deepcopy(s.data),
                    "provenance": asdict(s.provenance),
                    "content_hash": s.content_hash,
                }
                for s in sorted_snaps
            ]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VersionedHistoricalDataset:
        version = data.get("data_version", "unknown")
        meta = data.get("metadata", {})
        ds = cls(data_version=version, metadata=meta)
        for s_dict in data.get("snapshots", []):
            prov_dict = s_dict["provenance"]
            prov = Provenance(
                source_uri=prov_dict["source_uri"],
                observed_at=prov_dict["observed_at"],
                source_hash=prov_dict["source_hash"],
                record_type=prov_dict["record_type"],
                authoritative=prov_dict.get("authoritative", True),
                metadata=prov_dict.get("metadata", {}),
            )
            snap = ImmutableSnapshot(
                snapshot_id=s_dict["snapshot_id"],
                observed_at=s_dict["observed_at"],
                event=s_dict.get("event"),
                data=s_dict["data"],
                provenance=prov,
            )
            # Verify given content hash if present
            if "content_hash" in s_dict and s_dict["content_hash"] != snap.content_hash:
                raise SnapshotIntegrityError(f"Stored content_hash does not match recomputed hash for {snap.snapshot_id}")
            snap.verify_integrity()
            ds.snapshots.append(snap)
        ds._recompute_dataset_hash()

        # Verify top-level dataset_hash if provided
        if "dataset_hash" in data and data["dataset_hash"] != ds.dataset_hash:
            raise SnapshotIntegrityError(
                f"Stored dataset_hash ({data['dataset_hash']}) does not match computed dataset_hash ({ds.dataset_hash})"
            )
        return ds
