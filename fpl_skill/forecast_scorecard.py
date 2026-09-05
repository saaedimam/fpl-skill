from dataclasses import dataclass
from typing import Dict, Optional, List
import json

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

class ForecastScorecard:
    """Track forecasts vs outcomes; detect systematic bias."""
    
    def __init__(self):
        self.records: List[CalibrationRecord] = []
        self.sample_gate = 6  # minimum completed GWs OR 20 player-forecast pairs
    
    def add_record(self, record: CalibrationRecord) -> None:
        """Record one forecast vs actual outcome."""
        self.records.append(record)
    
    def completed_gameweeks(self) -> set:
        """Return set of unique completed GWs in records."""
        return {r.gw for r in self.records}
    
    def total_records(self) -> int:
        """Return total number of records."""
        return len(self.records)
    
    def sample_gate_passed(self) -> bool:
        """Return True if N >= 6 completed GWs OR >= 20 player-forecast pairs."""
        completed_gw_count = len(self.completed_gameweeks())
        total_pairs = self.total_records()
        return completed_gw_count >= 6 or total_pairs >= 20
    
    def compute_metrics(self) -> Dict:
        """
        Compute calibration metrics.
        
        Returns:
        - If insufficient sample: {"status": "INSUFFICIENT_SAMPLE", "reason": "..."}
        - If fresh season: {"status": "NO_TRACK_RECORD_YET"}
        - If ready: {"status": "READY", "mae": ..., "rmse": ..., ...}
        """
        completed_gws = len(self.completed_gameweeks())
        
        if not self.records:
            return {"status": "NO_TRACK_RECORD_YET", "reason": "Fresh season — no completed GW results"}
        
        if not self.sample_gate_passed():
            return {
                "status": "INSUFFICIENT_SAMPLE",
                "reason": f"Need 6 completed GWs or 20 pairs; have {completed_gws} GWs, {self.total_records()} pairs"
            }
        
        # Compute metrics
        abs_errors = [abs(r.signed_error) for r in self.records]
        signed_errors = [r.signed_error for r in self.records]
        
        mae = sum(abs_errors) / len(abs_errors) if abs_errors else 0.0
        rmse = (sum(e**2 for e in abs_errors) / len(abs_errors)) ** 0.5 if abs_errors else 0.0
        signed_bias = sum(signed_errors) / len(signed_errors) if signed_errors else 0.0
        
        return {
            "status": "READY",
            "mae": round(mae, 3),
            "rmse": round(rmse, 3),
            "signed_bias": round(signed_bias, 3),
            "brier": None,  # TODO: compute for probability forecasts
            "log_loss": None,  # TODO: compute for probability forecasts
            "sample_size": self.total_records(),
            "completed_gameweeks": completed_gws
        }
