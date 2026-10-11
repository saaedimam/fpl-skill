"""
fpl_skill/forecast_scorecard.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tracks forecast vs outcome calibration records.

Two distinct failure states:
  CORRUPT_STORE   — malformed JSON, wrong types, missing required fields
  NO_TRACK_RECORD_YET — file absent or structurally valid but empty

Legacy records (pre-v1.0) missing the optional fields introduced in v1.0
are migrated on load with deterministic defaults; they are NOT treated as
corrupt unless their foundational fields are missing or wrong-typed.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, List, Any
from pathlib import Path
import os
import json
import tempfile

CALIBRATION_FILE = Path(os.path.expanduser("~/.cache/fpl-skill/calibration_records.json"))


class CalibrationStoreError(RuntimeError):
    """Raised when persisted calibration state cannot be loaded safely."""


# Schema required keys that must be present + correct type for a record to be
# considered structurally valid (not corrupt).
_REQUIRED_FIELDS = {
    "gw": int,
    "player_id": int,
    "forecast_type": str,
    "predicted_expected_points": (int, float),
    "actual_points": (int, float),
    "absolute_error": (int, float),
    "signed_error": (int, float),
}

_VALID_FORECAST_TYPES = {"expected_points", "probability", "ranking",
                         "captain_expected_points"}


def _derive_within_p10_p90(
    predicted_distribution: Dict,
    actual_points: float,
) -> Optional[bool]:
    """Derive within_P10_P90 when the distribution has P10/P90 keys."""
    p10 = predicted_distribution.get("P10")
    p90 = predicted_distribution.get("P90")
    if p10 is None or p90 is None:
        return None
    try:
        return float(p10) <= float(actual_points) <= float(p90)
    except (TypeError, ValueError):
        return None


def _derive_calibration_bucket(predicted_ep: float) -> str:
    """Assign EP bucket; returns UNCATEGORIZED for invalid inputs."""
    try:
        ep = float(predicted_ep)
    except (TypeError, ValueError):
        return "UNCATEGORIZED"
    if ep < 2.0:
        return "LOW"
    if ep < 5.0:
        return "MID"
    if ep < 8.0:
        return "HIGH"
    return "HAUL"


@dataclass
class CalibrationRecord:
    """Single forecast vs actual outcome, schema-aligned with calibration-record.schema.json."""

    # --- Required foundational fields ---
    gw: int
    player_id: int
    forecast_type: str          # "expected_points" | "probability" | "ranking" | "captain_expected_points"
    predicted_expected_points: float
    predicted_distribution: Dict     # {P10, P25, P50, P75, P90}
    actual_points: float
    absolute_error: float            # |predicted - actual|
    signed_error: float              # predicted - actual

    # --- Optional fields introduced in v1.0 (migrated from legacy records) ---
    predicted_probabilities: Dict = field(default_factory=dict)
    within_P10_P90: Optional[bool] = None
    calibration_bucket: str = "UNCATEGORIZED"
    actual_events: Optional[Dict] = None

    def __post_init__(self):
        # Derive within_P10_P90 if not set but derivable
        if self.within_P10_P90 is None and self.predicted_distribution:
            self.within_P10_P90 = _derive_within_p10_p90(
                self.predicted_distribution, self.actual_points
            )
        # Derive calibration_bucket if still UNCATEGORIZED
        if self.calibration_bucket == "UNCATEGORIZED":
            self.calibration_bucket = _derive_calibration_bucket(
                self.predicted_expected_points
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gw": self.gw,
            "player_id": self.player_id,
            "forecast_type": self.forecast_type,
            "predicted_expected_points": self.predicted_expected_points,
            "predicted_distribution": self.predicted_distribution,
            "predicted_probabilities": self.predicted_probabilities,
            "actual_points": self.actual_points,
            "actual_events": self.actual_events,
            "absolute_error": self.absolute_error,
            "signed_error": self.signed_error,
            "within_P10_P90": self.within_P10_P90,
            "calibration_bucket": self.calibration_bucket,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalibrationRecord":
        """
        Construct a CalibrationRecord from a dict.

        Distinguishes two cases:
          - LEGACY MIGRATION: structurally valid old record missing v1.0 optional fields
            → migrated with deterministic defaults/derivation
          - CORRUPT: missing or wrong-typed foundational fields → raises ValueError
        """
        # Validate required foundational fields
        for key, expected_type in _REQUIRED_FIELDS.items():
            val = data.get(key)
            if val is None:
                raise ValueError(f"CalibrationRecord missing required field '{key}'")
            if not isinstance(val, expected_type):
                raise ValueError(
                    f"CalibrationRecord field '{key}' has wrong type "
                    f"(expected {expected_type}, got {type(val).__name__})"
                )

        # Validate forecast_type against allowed set
        ft = str(data.get("forecast_type", ""))
        if ft not in _VALID_FORECAST_TYPES:
            raise ValueError(
                f"CalibrationRecord has unknown forecast_type='{ft}'. "
                f"Allowed: {sorted(_VALID_FORECAST_TYPES)}"
            )

        # Derive/migrate optional v1.0 fields
        predicted_dist = dict(data.get("predicted_distribution", {}))
        actual_pts = float(data["actual_points"])

        within = data.get("within_P10_P90")
        if within is None:
            within = _derive_within_p10_p90(predicted_dist, actual_pts)

        bucket = data.get("calibration_bucket")
        if not bucket or bucket == "UNCATEGORIZED":
            bucket = _derive_calibration_bucket(float(data["predicted_expected_points"]))

        return cls(
            gw=int(data["gw"]),
            player_id=int(data["player_id"]),
            forecast_type=ft,
            predicted_expected_points=float(data["predicted_expected_points"]),
            predicted_distribution=predicted_dist,
            predicted_probabilities=dict(data.get("predicted_probabilities") or {}),
            actual_points=actual_pts,
            actual_events=data.get("actual_events"),
            absolute_error=float(data.get("absolute_error",
                abs(float(data["predicted_expected_points"]) - actual_pts))),
            signed_error=float(data.get("signed_error",
                float(data["predicted_expected_points"]) - actual_pts)),
            within_P10_P90=within,
            calibration_bucket=bucket or "UNCATEGORIZED",
        )


def validate_record(record: CalibrationRecord) -> bool:
    """
    Validate a CalibrationRecord against the JSON schema.
    Returns True if valid; raises jsonschema.ValidationError if not.
    """
    try:
        import jsonschema
        schema_path = Path(__file__).parent.parent / "schemas" / "calibration-record.schema.json"
        if schema_path.exists():
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(record.to_dict(), schema)
    except ImportError:
        pass  # jsonschema not installed; skip schema validation
    return True


class ForecastScorecard:
    """Track forecasts vs outcomes; detect systematic bias."""

    def __init__(self):
        self.records: List[CalibrationRecord] = []
        self.sample_gate = 6      # minimum completed GWs OR 20 player-forecast pairs
        self._corrupt: bool = False
        self._corrupt_reason: str = ""

    def add_record(self, record: CalibrationRecord) -> None:
        """Record one forecast vs actual outcome."""
        self.records.append(record)

    def completed_gameweeks(self, records: Optional[List[CalibrationRecord]] = None) -> set:
        recs = records if records is not None else self.records
        return {r.gw for r in recs}

    def total_records(self, records: Optional[List[CalibrationRecord]] = None) -> int:
        recs = records if records is not None else self.records
        return len(recs)

    def sample_gate_passed(self, records: Optional[List[CalibrationRecord]] = None) -> bool:
        completed_gw_count = len(self.completed_gameweeks(records))
        total_pairs = self.total_records(records)
        return completed_gw_count >= 6 or total_pairs >= 20

    def save(self, path: Optional[Path] = None) -> None:
        """Persist calibration records atomically to JSON."""
        target_path = path or CALIBRATION_FILE
        target_path.parent.mkdir(parents=True, exist_ok=True)
        data = [r.to_dict() for r in self.records]
        fd, temp_name = tempfile.mkstemp(prefix=f".{target_path.name}.", suffix=".tmp", dir=target_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, target_path)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ForecastScorecard":
        """Load calibration records from JSON; fail closed on corruption."""
        scorecard = cls()
        target_path = path or CALIBRATION_FILE
        if not target_path.exists():
            return scorecard
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("calibration store root must be a JSON array")
            for index, item in enumerate(data):
                if not isinstance(item, dict):
                    raise ValueError(f"record {index} must be an object")
                scorecard.add_record(CalibrationRecord.from_dict(item))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise CalibrationStoreError(f"Invalid calibration store {target_path}: {exc}") from exc
        return scorecard

    def compute_metrics(self, gw: Optional[int] = None, by_category: bool = False) -> Dict:
        """
        Compute calibration metrics.

        Returns:
          - CORRUPT_STORE if the scorecard loaded a corrupt file
          - NO_TRACK_RECORD_YET if no records exist
          - INSUFFICIENT_SAMPLE if below gate
          - READY with metrics
        """
        if self._corrupt:
            return {
                "status": "CORRUPT_STORE",
                "reason": self._corrupt_reason,
            }

        records = self.records
        if gw is not None:
            records = [r for r in records if r.gw == gw]

        completed_gws = len(self.completed_gameweeks(records))

        if not records:
            return {
                "status": "NO_TRACK_RECORD_YET",
                "reason": (
                    f"No completed records found{' for GW ' + str(gw) if gw is not None else ' — season is fresh'}"
                )
            }

        # The gate is applied to the complete scorecard, not the filtered
        # view, so a per-GW diagnostic cannot masquerade as certification.
        gate_gw_count = len(self.completed_gameweeks())
        gate_pair_count = len(self.records)
        if not self.sample_gate_passed():
            return {
                "status": "INSUFFICIENT_SAMPLE",
                "reason": (
                    f"Need 6 completed GWs or 20 pairs; have "
                    f"{gate_gw_count} GWs, {gate_pair_count} pairs"
                )
            }

        abs_errors = [abs(r.signed_error) for r in records]
        signed_errors = [r.signed_error for r in records]

        mae = sum(abs_errors) / len(abs_errors) if abs_errors else 0.0
        rmse = (sum(e**2 for e in abs_errors) / len(abs_errors)) ** 0.5 if abs_errors else 0.0
        signed_bias = sum(signed_errors) / len(signed_errors) if signed_errors else 0.0

        result = {
            "status": "READY",
            "mae": round(mae, 3),
            "rmse": round(rmse, 3),
            "signed_bias": round(signed_bias, 3),
            "brier": None,
            "log_loss": None,
            "sample_size": len(records),
            "completed_gameweeks": completed_gws,
        }

        if by_category:
            categories: Dict[str, Dict[str, Any]] = {}
            for r in records:
                cat = r.forecast_type
                if cat not in categories:
                    categories[cat] = {"abs_errors": [], "signed_errors": []}
                categories[cat]["abs_errors"].append(abs(r.signed_error))
                categories[cat]["signed_errors"].append(r.signed_error)

            breakdown = {}
            for cat, d in categories.items():
                cat_abs = d["abs_errors"]
                cat_signed = d["signed_errors"]
                cat_mae = sum(cat_abs) / len(cat_abs) if cat_abs else 0.0
                cat_rmse = (sum(e**2 for e in cat_abs) / len(cat_abs)) ** 0.5 if cat_abs else 0.0
                cat_bias = sum(cat_signed) / len(cat_signed) if cat_signed else 0.0
                breakdown[cat] = {
                    "count": len(cat_abs),
                    "mae": round(cat_mae, 3),
                    "rmse": round(cat_rmse, 3),
                    "signed_bias": round(cat_bias, 3),
                }
            result["by_category"] = breakdown

        return result
