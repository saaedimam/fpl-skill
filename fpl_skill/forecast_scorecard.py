from dataclasses import dataclass, asdict
from typing import Dict, Optional, List, Any
from pathlib import Path
import os
import json

CALIBRATION_FILE = Path(os.path.expanduser("~/.cache/fpl-skill/calibration_records.json"))

@dataclass
class CalibrationRecord:
    """Single forecast vs actual outcome."""
    gw: int
    player_id: int
    forecast_type: str  # "expected_points" | "goal" | "assist" | "clean_sheet"
    predicted_expected_points: float
    predicted_distribution: Dict  # {P10, P25, P50, P75, P90}
    actual_points: float
    absolute_error: float  # |predicted - actual|
    signed_error: float  # predicted - actual

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalibrationRecord":
        return cls(
            gw=int(data["gw"]),
            player_id=int(data["player_id"]),
            forecast_type=str(data.get("forecast_type", "expected_points")),
            predicted_expected_points=float(data["predicted_expected_points"]),
            predicted_distribution=dict(data.get("predicted_distribution", {})),
            actual_points=float(data["actual_points"]),
            absolute_error=float(data.get("absolute_error", abs(data["predicted_expected_points"] - data["actual_points"]))),
            signed_error=float(data.get("signed_error", data["predicted_expected_points"] - data["actual_points"]))
        )

class ForecastScorecard:
    """Track forecasts vs outcomes; detect systematic bias."""
    
    def __init__(self):
        self.records: List[CalibrationRecord] = []
        self.sample_gate = 6  # minimum completed GWs OR 20 player-forecast pairs
    
    def add_record(self, record: CalibrationRecord) -> None:
        """Record one forecast vs actual outcome."""
        self.records.append(record)
    
    def completed_gameweeks(self, records: Optional[List[CalibrationRecord]] = None) -> set:
        """Return set of unique completed GWs in records."""
        recs = records if records is not None else self.records
        return {r.gw for r in recs}
    
    def total_records(self, records: Optional[List[CalibrationRecord]] = None) -> int:
        """Return total number of records."""
        recs = records if records is not None else self.records
        return len(recs)
    
    def sample_gate_passed(self, records: Optional[List[CalibrationRecord]] = None) -> bool:
        """Return True if N >= 6 completed GWs OR >= 20 player-forecast pairs."""
        completed_gw_count = len(self.completed_gameweeks(records))
        total_pairs = self.total_records(records)
        return completed_gw_count >= 6 or total_pairs >= 20

    def save(self, path: Optional[Path] = None) -> None:
        """Persist calibration records to JSON file."""
        target_path = path or CALIBRATION_FILE
        target_path.parent.mkdir(parents=True, exist_ok=True)
        data = [r.to_dict() for r in self.records]
        with open(target_path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ForecastScorecard":
        """Load calibration records from JSON file."""
        scorecard = cls()
        target_path = path or CALIBRATION_FILE
        if target_path.exists():
            try:
                with open(target_path, "r") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        scorecard.add_record(CalibrationRecord.from_dict(item))
            except Exception:
                pass
        return scorecard

    def compute_metrics(self, gw: Optional[int] = None, by_category: bool = False) -> Dict:
        """
        Compute calibration metrics.
        
        Returns:
        - If insufficient sample: {"status": "INSUFFICIENT_SAMPLE", "reason": "..."}
        - If fresh season: {"status": "NO_TRACK_RECORD_YET"}
        - If ready: {"status": "READY", "mae": ..., "rmse": ..., ...}
        """
        records = self.records
        if gw is not None:
            records = [r for r in records if r.gw == gw]

        completed_gws = len(self.completed_gameweeks(records))
        
        if not records:
            return {
                "status": "NO_TRACK_RECORD_YET",
                "reason": f"No completed records found{' for GW ' + str(gw) if gw is not None else ' — season is fresh'}"
            }
        
        if not self.sample_gate_passed(records) and gw is None:
            return {
                "status": "INSUFFICIENT_SAMPLE",
                "reason": f"Need 6 completed GWs or 20 pairs; have {completed_gws} GWs, {len(records)} pairs"
            }
        
        # Compute aggregate metrics
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
            "completed_gameweeks": completed_gws
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
            for cat, data in categories.items():
                cat_abs = data["abs_errors"]
                cat_signed = data["signed_errors"]
                cat_mae = sum(cat_abs) / len(cat_abs) if cat_abs else 0.0
                cat_rmse = (sum(e**2 for e in cat_abs) / len(cat_abs)) ** 0.5 if cat_abs else 0.0
                cat_bias = sum(cat_signed) / len(cat_signed) if cat_signed else 0.0
                breakdown[cat] = {
                    "count": len(cat_abs),
                    "mae": round(cat_mae, 3),
                    "rmse": round(cat_rmse, 3),
                    "signed_bias": round(cat_bias, 3)
                }
            result["by_category"] = breakdown

        return result
