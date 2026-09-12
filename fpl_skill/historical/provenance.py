"""Provenance and datum representations for immutable historical snapshots."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .exceptions import ProvenanceError, SnapshotIntegrityError, TemporalLeakageError


def _normalize_dict_keys(obj: Any) -> Any:
    """Recursively convert dictionary keys to strings to ensure deterministic JSON serialization."""
    if isinstance(obj, dict):
        return {str(k): _normalize_dict_keys(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_normalize_dict_keys(v) for v in obj]
    return obj


def _canonical_json_dumps(obj: Any) -> bytes:
    """Serialize object to deterministic UTF-8 JSON bytes with sorted string keys."""
    normalized = _normalize_dict_keys(obj)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def compute_sha256(data: Any) -> str:
    """Compute SHA256 hex digest of a canonical JSON serialization or raw bytes."""
    if isinstance(data, bytes):
        raw = data
    else:
        raw = _canonical_json_dumps(data)
    return hashlib.sha256(raw).hexdigest()


def parse_iso_utc(ts_str: str) -> datetime:
    """Parse ISO8601 string to timezone-aware UTC datetime."""
    if not ts_str:
        raise ValueError("Timestamp string cannot be empty")
    # Normalize trailing 'Z' to '+00:00'
    normalized = ts_str.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_iso_utc(dt: datetime) -> str:
    """Format timezone-aware datetime into canonical ISO8601 UTC string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Provenance:
    """Immutable provenance metadata attached to every historical record/datum."""
    source_uri: str
    observed_at: str          # ISO8601 UTC timestamp of observation
    source_hash: str          # SHA256 of raw source payload
    record_type: str          # e.g., 'bootstrap_static', 'element_summary', 'fixture', 'lineup'
    authoritative: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.source_uri:
            raise ProvenanceError("source_uri is mandatory")
        if not self.observed_at:
            raise ProvenanceError("observed_at is mandatory")
        if not self.source_hash:
            raise ProvenanceError("source_hash is mandatory")
        # Validate timestamp parseability
        parse_iso_utc(self.observed_at)
        object.__setattr__(self, "metadata", copy.deepcopy(self.metadata))

    @property
    def observed_datetime(self) -> datetime:
        return parse_iso_utc(self.observed_at)


@dataclass(frozen=True)
class ProvenancedDatum:
    """A unit of historical information bound to its immutable provenance."""
    datum_id: str
    data: Dict[str, Any]
    provenance: Provenance
    datum_hash: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "data", copy.deepcopy(self.data))
        d_hash = compute_sha256({
            "datum_id": self.datum_id,
            "data": self.data,
            "provenance": asdict(self.provenance)
        })
        object.__setattr__(self, "datum_hash", d_hash)

    def verify_integrity(self) -> bool:
        """Verify datum content matches its recorded hash and provenance source hash."""
        expected = compute_sha256({
            "datum_id": self.datum_id,
            "data": self.data,
            "provenance": asdict(self.provenance)
        })
        if expected != self.datum_hash:
            raise SnapshotIntegrityError(f"Integrity check failed for datum {self.datum_id}")
        return True

    def enforce_temporal_cutoff(self, cutoff_utc: str) -> ProvenancedDatum:
        """Fail-stop temporal firewall check against decision cutoff t."""
        self.verify_integrity()
        cutoff_dt = parse_iso_utc(cutoff_utc)
        if self.provenance.observed_datetime > cutoff_dt:
            raise TemporalLeakageError(
                f"LEAKAGE DETECTED: Datum '{self.datum_id}' observed at {self.provenance.observed_at} "
                f"is strictly after decision cutoff t={cutoff_utc}. "
                f"Invariant violation: I_t ∩ D_>t ≠ ∅"
            )
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "datum_id": self.datum_id,
            "data": copy.deepcopy(self.data),
            "provenance": asdict(self.provenance),
            "datum_hash": self.datum_hash,
        }
