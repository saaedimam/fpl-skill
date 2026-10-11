"""
tests/test_calibration_schema.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for CalibrationRecord schema alignment and migration behaviour.
"""
import json
import pytest
from pathlib import Path
from fpl_skill.forecast_scorecard import (
    CalibrationRecord, ForecastScorecard, CalibrationStoreError,
    _derive_within_p10_p90, _derive_calibration_bucket,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk_record(**kwargs):
    base = {
        "gw": 5,
        "player_id": 123,
        "forecast_type": "expected_points",
        "predicted_expected_points": 6.0,
        "predicted_distribution": {"P10": 2.0, "P25": 4.0, "P50": 6.0, "P75": 8.0, "P90": 10.0},
        "actual_points": 7.0,
        "absolute_error": 1.0,
        "signed_error": -1.0,
    }
    base.update(kwargs)
    return CalibrationRecord(**base)


# ---------------------------------------------------------------------------
# CalibrationRecord — field derivation
# ---------------------------------------------------------------------------

def test_within_p10_p90_derived_when_inside_range():
    r = _mk_record(predicted_distribution={"P10": 2.0, "P25": 4.0, "P50": 6.0, "P75": 8.0, "P90": 10.0},
                   actual_points=7.0)
    assert r.within_P10_P90 is True


def test_within_p10_p90_derived_when_outside_range():
    r = _mk_record(predicted_distribution={"P10": 2.0, "P25": 4.0, "P50": 6.0, "P75": 8.0, "P90": 10.0},
                   actual_points=12.0)
    assert r.within_P10_P90 is False


def test_within_p10_p90_none_when_no_distribution():
    r = CalibrationRecord(
        gw=1, player_id=1, forecast_type="expected_points",
        predicted_expected_points=5.0, predicted_distribution={},
        actual_points=4.0, absolute_error=1.0, signed_error=1.0,
    )
    assert r.within_P10_P90 is None


def test_calibration_bucket_derived():
    r = _mk_record(predicted_expected_points=6.5)
    assert r.calibration_bucket == "HIGH"


@pytest.mark.parametrize("ep,expected_bucket", [
    (0.5, "LOW"), (1.9, "LOW"),
    (2.0, "MID"), (4.9, "MID"),
    (5.0, "HIGH"), (7.9, "HIGH"),
    (8.0, "HAUL"), (15.0, "HAUL"),
])
def test_calibration_bucket_boundaries(ep, expected_bucket):
    assert _derive_calibration_bucket(ep) == expected_bucket


# ---------------------------------------------------------------------------
# CalibrationRecord.to_dict() — required schema keys
# ---------------------------------------------------------------------------

def test_to_dict_has_all_schema_required_keys():
    r = _mk_record()
    d = r.to_dict()
    required = {
        "gw", "player_id", "forecast_type",
        "predicted_expected_points", "predicted_distribution", "predicted_probabilities",
        "actual_points", "absolute_error", "signed_error",
        "within_P10_P90", "calibration_bucket",
    }
    assert required.issubset(set(d.keys()))


# ---------------------------------------------------------------------------
# CalibrationRecord.from_dict() — legacy migration
# ---------------------------------------------------------------------------

def test_from_dict_legacy_missing_optional_fields():
    """Legacy record without v1.0 optional fields → LEGACY_MIGRATION, not corrupt."""
    legacy = {
        "gw": 3,
        "player_id": 55,
        "forecast_type": "expected_points",
        "predicted_expected_points": 5.0,
        "predicted_distribution": {"P10": 1.0, "P25": 3.0, "P50": 5.0, "P75": 7.0, "P90": 9.0},
        "actual_points": 4.0,
        "absolute_error": 1.0,
        "signed_error": 1.0,
        # within_P10_P90, calibration_bucket, predicted_probabilities absent
    }
    rec = CalibrationRecord.from_dict(legacy)
    assert rec.within_P10_P90 is True   # derived from distribution + actual_points
    assert rec.calibration_bucket == "HIGH"
    assert rec.predicted_probabilities == {}


def test_from_dict_missing_required_field_raises():
    bad = {
        # gw missing
        "player_id": 1,
        "forecast_type": "expected_points",
        "predicted_expected_points": 5.0,
        "predicted_distribution": {},
        "actual_points": 4.0,
        "absolute_error": 1.0,
        "signed_error": 1.0,
    }
    with pytest.raises(ValueError, match="missing required field 'gw'"):
        CalibrationRecord.from_dict(bad)


def test_from_dict_wrong_type_raises():
    bad = {
        "gw": "five",  # must be int
        "player_id": 1,
        "forecast_type": "expected_points",
        "predicted_expected_points": 5.0,
        "predicted_distribution": {},
        "actual_points": 4.0,
        "absolute_error": 1.0,
        "signed_error": 1.0,
    }
    with pytest.raises(ValueError, match="wrong type"):
        CalibrationRecord.from_dict(bad)


def test_from_dict_unknown_forecast_type_raises():
    bad = {
        "gw": 1,
        "player_id": 1,
        "forecast_type": "goal",  # not in schema enum
        "predicted_expected_points": 5.0,
        "predicted_distribution": {},
        "actual_points": 4.0,
        "absolute_error": 1.0,
        "signed_error": 1.0,
    }
    with pytest.raises(ValueError, match="unknown forecast_type"):
        CalibrationRecord.from_dict(bad)


# ---------------------------------------------------------------------------
# ForecastScorecard.load() — corrupt file detection
# ---------------------------------------------------------------------------

def test_load_absent_file_returns_empty_not_corrupt(tmp_path):
    sc = ForecastScorecard.load(tmp_path / "nonexistent.json")
    assert not sc._corrupt
    assert sc.total_records() == 0


def test_load_malformed_json_returns_corrupt_store(tmp_path):
    f = tmp_path / "cal.json"
    f.write_text("this is not json")
    with pytest.raises(CalibrationStoreError):
        ForecastScorecard.load(f)


def test_load_wrong_root_type_returns_corrupt_store(tmp_path):
    f = tmp_path / "cal.json"
    f.write_text(json.dumps({"records": []}))  # dict, not list
    with pytest.raises(CalibrationStoreError):
        ForecastScorecard.load(f)


def test_load_corrupt_record_returns_corrupt_store(tmp_path):
    f = tmp_path / "cal.json"
    f.write_text(json.dumps([{"gw": "BAD", "player_id": 1, "forecast_type": "expected_points",
                               "predicted_expected_points": 5.0, "predicted_distribution": {},
                               "actual_points": 4.0, "absolute_error": 1.0, "signed_error": 1.0}]))
    with pytest.raises(CalibrationStoreError):
        ForecastScorecard.load(f)


def test_load_valid_legacy_records_succeeds(tmp_path):
    """Structurally valid legacy records (missing optional fields) load without error."""
    records = [
        {
            "gw": i,
            "player_id": i,
            "forecast_type": "expected_points",
            "predicted_expected_points": 5.0,
            "predicted_distribution": {"P10": 1.0, "P25": 3.0, "P50": 5.0, "P75": 7.0, "P90": 9.0},
            "actual_points": 4.0,
            "absolute_error": 1.0,
            "signed_error": 1.0,
        }
        for i in range(1, 8)
    ]
    f = tmp_path / "cal.json"
    f.write_text(json.dumps(records))
    sc = ForecastScorecard.load(f)
    assert not sc._corrupt
    assert sc.total_records() == 7


def test_corrupt_store_status_returned_by_compute_metrics(tmp_path):
    f = tmp_path / "cal.json"
    f.write_text("null")  # JSON null is not a list
    with pytest.raises(CalibrationStoreError):
        ForecastScorecard.load(f)


# ---------------------------------------------------------------------------
# No-track-record-yet
# ---------------------------------------------------------------------------

def test_empty_scorecard_returns_no_track_record_yet():
    sc = ForecastScorecard()
    m = sc.compute_metrics()
    assert m["status"] == "NO_TRACK_RECORD_YET"
