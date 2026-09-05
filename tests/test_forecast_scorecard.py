import pytest
from fpl_skill.forecast_scorecard import ForecastScorecard, CalibrationRecord

def test_insufficient_sample():
    """Gate should block verdict if fewer than 6 GWs."""
    scorecard = ForecastScorecard()
    record = CalibrationRecord(gw=1, player_id=1, forecast_type="expected_points",
                                predicted_expected_points=5.0, predicted_distribution={},
                                actual_points=3.0, absolute_error=2.0, signed_error=-2.0)
    scorecard.add_record(record)
    
    result = scorecard.compute_metrics()
    assert result["status"] == "INSUFFICIENT_SAMPLE"

def test_sample_gate_six_gws():
    """Gate should pass at 6 completed GWs."""
    scorecard = ForecastScorecard()
    for gw in range(1, 7):
        record = CalibrationRecord(gw=gw, player_id=1, forecast_type="expected_points",
                                    predicted_expected_points=5.0, predicted_distribution={},
                                    actual_points=5.0, absolute_error=0.0, signed_error=0.0)
        scorecard.add_record(record)
    
    result = scorecard.compute_metrics()
    assert result["status"] == "READY"
    assert result["mae"] == 0.0

def test_no_track_record_fresh_season():
    """Fresh season should return NO_TRACK_RECORD_YET."""
    scorecard = ForecastScorecard()
    result = scorecard.compute_metrics()
    assert result["status"] == "NO_TRACK_RECORD_YET"
