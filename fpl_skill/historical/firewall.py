"""Temporal firewall interceptors and adversarial validation harness."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .exceptions import TemporalLeakageError
from .provenance import Provenance, ProvenancedDatum, parse_iso_utc
from .replay import InformationSet
from .snapshot import ImmutableSnapshot, VersionedHistoricalDataset


class TemporalFirewall:
    """Pre-model firewall intercepting any attempted data access past cutoff t."""

    def __init__(self, cutoff_utc: str):
        self.cutoff_utc = cutoff_utc
        self.cutoff_dt = parse_iso_utc(cutoff_utc)

    def validate_snapshot(self, snapshot: ImmutableSnapshot) -> ImmutableSnapshot:
        """Verify snapshot was observed <= cutoff_t. Raises TemporalLeakageError if > cutoff_t."""
        s_dt = parse_iso_utc(snapshot.observed_at)
        if s_dt > self.cutoff_dt:
            raise TemporalLeakageError(
                f"FIREWALL BLOCKED LEAKAGE: Snapshot {snapshot.snapshot_id} observed at {snapshot.observed_at} "
                f"is strictly after decision cutoff t={self.cutoff_utc}!"
            )
        return snapshot

    def validate_datum(self, datum: ProvenancedDatum) -> ProvenancedDatum:
        """Verify datum was observed <= cutoff_t. Raises TemporalLeakageError if > cutoff_t."""
        return datum.enforce_temporal_cutoff(self.cutoff_utc)

    def filter_dataset(self, dataset: VersionedHistoricalDataset) -> List[ImmutableSnapshot]:
        """Return strictly filtered list of snapshots satisfying I_t ⊆ D_≤t."""
        filtered = []
        for s in dataset.snapshots:
            s_dt = parse_iso_utc(s.observed_at)
            if s_dt <= self.cutoff_dt:
                filtered.append(s)
        return filtered

    def intercept_query(self, query_fn: Callable[..., Any], datum: ProvenancedDatum, *args, **kwargs) -> Any:
        """Execute a data query only if datum passes the temporal firewall."""
        self.validate_datum(datum)
        return query_fn(datum, *args, **kwargs)
