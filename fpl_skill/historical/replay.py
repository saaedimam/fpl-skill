"""Decision-time information-set builder, temporal firewall, and deterministic replay."""
from __future__ import annotations

import copy
import platform
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set

from .exceptions import ProvenanceError, SnapshotIntegrityError, TemporalLeakageError
from .provenance import (
    Provenance,
    ProvenancedDatum,
    compute_sha256,
    format_iso_utc,
    parse_iso_utc,
)
from .snapshot import ImmutableSnapshot, VersionedHistoricalDataset


def compute_environment_fingerprint() -> str:
    """Generate deterministic environment fingerprint for reproducibility."""
    env_info = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "byteorder": sys.byteorder,
    }
    return compute_sha256(env_info)


@dataclass(frozen=True)
class ReplayContext:
    """Immutable 8-element context identifying exact replay configuration."""
    data_version: str
    feature_version: str
    model_version: str = "Phase2-data-only"
    policy_version: str = "none"
    config_hash: str = ""
    solver_version: str = "none"
    environment_fingerprint: str = field(default_factory=compute_environment_fingerprint)
    seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InformationSet:
    """The complete, immutable information set I_t available at decision time t."""
    decision_timestamp_utc: str       # Cutoff t (ISO8601 UTC)
    gameweek: Optional[int]
    data: Dict[str, Any]             # Aggregated state payload
    provenance_records: List[Dict[str, Any]] # Provenance of every incorporated datum
    replay_context: ReplayContext
    info_set_hash: str = field(init=False)

    def __post_init__(self):
        # Validate decision timestamp
        cutoff_dt = parse_iso_utc(self.decision_timestamp_utc)

        # Enforce that if data has snapshots/elements, provenance_records cannot be empty
        observed_count = self.data.get("observed_snapshots_count", 0)
        if observed_count > 0 and not self.provenance_records:
            raise ProvenanceError("InformationSet contains data but zero provenance records")

        # Enforce temporal verification on all provenance records
        for p in self.provenance_records:
            obs_dt = parse_iso_utc(p["observed_at"])
            if obs_dt > cutoff_dt:
                raise TemporalLeakageError(
                    f"CRITICAL FIREWALL LEAKAGE: Provenance record observed at {p['observed_at']} "
                    f"exceeds decision cutoff t={self.decision_timestamp_utc}!"
                )

        # Defensive deep copies
        object.__setattr__(self, "data", copy.deepcopy(self.data))
        object.__setattr__(self, "provenance_records", copy.deepcopy(self.provenance_records))

        h_payload = {
            "decision_timestamp_utc": self.decision_timestamp_utc,
            "gameweek": self.gameweek,
            "data": self.data,
            "provenance_records": sorted(self.provenance_records, key=lambda r: (parse_iso_utc(r["observed_at"]), r["source_uri"])),
            "replay_context": self.replay_context.to_dict(),
        }
        object.__setattr__(self, "info_set_hash", compute_sha256(h_payload))

    def get_element(self, element_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve defensive copy of element data within I_t."""
        elements = self.data.get("elements", {})
        res = elements.get(str(element_id)) or elements.get(element_id)
        return copy.deepcopy(res) if res is not None else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_timestamp_utc": self.decision_timestamp_utc,
            "gameweek": self.gameweek,
            "data": copy.deepcopy(self.data),
            "provenance_records": copy.deepcopy(self.provenance_records),
            "replay_context": self.replay_context.to_dict(),
            "info_set_hash": self.info_set_hash,
        }


class InformationSetBuilder:
    """Builder that reconstructs I_t from a VersionedHistoricalDataset subject to strict cutoff t."""

    def __init__(self, dataset: VersionedHistoricalDataset, feature_version: str = "v1.0-raw"):
        self.dataset = dataset
        self.feature_version = feature_version

    def build_information_set(
        self,
        decision_timestamp_utc: str,
        gameweek: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None,
        seed: int = 42,
    ) -> InformationSet:
        """Reconstruct I_t strictly from snapshots observed on or before decision_timestamp_utc.

        Enforces:
        I_t ⊆ D_≤t
        I_t ∩ D_>t = ∅
        """
        cutoff_dt = parse_iso_utc(decision_timestamp_utc)
        valid_snapshots = self.dataset.get_snapshots_before(decision_timestamp_utc)

        # Adversarial check: Verify no snapshot with observed_at > cutoff exists in candidate pool
        for snap in valid_snapshots:
            snap_dt = parse_iso_utc(snap.observed_at)
            if snap_dt > cutoff_dt:
                raise TemporalLeakageError(
                    f"Temporal leakage violation: Snapshot {snap.snapshot_id} (observed at {snap.observed_at}) "
                    f"is after decision cutoff {decision_timestamp_utc}"
                )

        # Aggregate state chronologically so latest pre-deadline observations take precedence
        aggregated_data: Dict[str, Any] = {
            "elements": {},
            "fixtures": [],
            "events": {},
            "teams": {},
            "observed_snapshots_count": len(valid_snapshots),
        }
        provenance_records: List[Dict[str, Any]] = []

        for snap in valid_snapshots:
            snap.verify_integrity()
            p_dict = asdict(snap.provenance)
            provenance_records.append(p_dict)

            payload = copy.deepcopy(snap.data)
            rec_type = snap.provenance.record_type

            if rec_type in ("bootstrap_static", "elements"):
                if "elements" in payload and isinstance(payload["elements"], list):
                    for el in payload["elements"]:
                        el_id = str(el["id"])
                        if el_id not in aggregated_data["elements"]:
                            aggregated_data["elements"][el_id] = copy.deepcopy(el)
                        else:
                            # Merge updates so previous fields (name, price, etc.) are preserved
                            aggregated_data["elements"][el_id].update(copy.deepcopy(el))
                elif "elements" in payload and isinstance(payload["elements"], dict):
                    for k, v in payload["elements"].items():
                        el_id = str(k)
                        if el_id not in aggregated_data["elements"]:
                            aggregated_data["elements"][el_id] = copy.deepcopy(v)
                        else:
                            if isinstance(v, dict):
                                aggregated_data["elements"][el_id].update(copy.deepcopy(v))
                            else:
                                aggregated_data["elements"][el_id] = copy.deepcopy(v)

                if "events" in payload:
                    if isinstance(payload["events"], list):
                        for ev in payload["events"]:
                            aggregated_data["events"][str(ev["id"])] = copy.deepcopy(ev)
                    elif isinstance(payload["events"], dict):
                        for k, v in payload["events"].items():
                            aggregated_data["events"][str(k)] = copy.deepcopy(v)

                if "teams" in payload:
                    if isinstance(payload["teams"], list):
                        for tm in payload["teams"]:
                            aggregated_data["teams"][str(tm["id"])] = copy.deepcopy(tm)
                    elif isinstance(payload["teams"], dict):
                        for k, v in payload["teams"].items():
                            aggregated_data["teams"][str(k)] = copy.deepcopy(v)

            elif rec_type == "fixtures":
                fixtures_list = payload.get("fixtures", payload if isinstance(payload, list) else [])
                aggregated_data["fixtures"] = copy.deepcopy(fixtures_list)

            elif rec_type == "element_summary":
                el_id = payload.get("element_id")
                if el_id:
                    el_key = str(el_id)
                    if el_key not in aggregated_data["elements"]:
                        aggregated_data["elements"][el_key] = {}
                    aggregated_data["elements"][el_key]["summary"] = copy.deepcopy(payload)

            elif rec_type == "lineup_leak":
                match_id = payload.get("match_id")
                if "lineups" not in aggregated_data:
                    aggregated_data["lineups"] = {}
                aggregated_data["lineups"][str(match_id)] = copy.deepcopy(payload)

            else:
                # Generic record type aggregation
                if rec_type not in aggregated_data:
                    aggregated_data[rec_type] = {}
                aggregated_data[rec_type][snap.snapshot_id] = copy.deepcopy(payload)

        # Config hash
        c_hash = compute_sha256(config or {})

        replay_ctx = ReplayContext(
            data_version=self.dataset.data_version,
            feature_version=self.feature_version,
            model_version="Phase2-data-only",
            policy_version="none",
            config_hash=c_hash,
            solver_version="none",
            seed=seed,
        )

        return InformationSet(
            decision_timestamp_utc=decision_timestamp_utc,
            gameweek=gameweek,
            data=aggregated_data,
            provenance_records=provenance_records,
            replay_context=replay_ctx,
        )


class DeterministicReplayAPI:
    """Deterministic Replay Engine guaranteeing bit-identical / invariant results given replay tuple."""

    def __init__(self, dataset: VersionedHistoricalDataset):
        self.dataset = dataset
        self.builder = InformationSetBuilder(dataset)

    def replay_decision_state(
        self,
        decision_timestamp_utc: str,
        gameweek: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None,
        seed: int = 42,
    ) -> InformationSet:
        """Execute deterministic reconstruction of I_t for given decision parameters."""
        return self.builder.build_information_set(
            decision_timestamp_utc=decision_timestamp_utc,
            gameweek=gameweek,
            config=config,
            seed=seed,
        )
