import json
import math
from pathlib import Path
from datetime import datetime, timezone

import pytest

from fpl_skill.backtest import CaptainBacktest, BenchBacktest, TransferBacktest
from fpl_skill.forecast_scorecard import ForecastScorecard

ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "schemas/predeadline-snapshot.schema.json").read_text())


def snapshot():
    return {"target_gameweek": 1, "cutoff_timestamp": "2026-08-01T10:00:00Z", "source_identity": "test", "retrieval_timestamp": "UNKNOWN", "source_version": "test-1", "missing_data_status": "none", "expected_points": 5.0, "start_probability": 0.8, "expected_minutes": 80.0, "predicted_squad": [], "starting_xi": [], "bench": [], "captain": 1, "vice_captain": 2, "chip": None, "model_version": "test", "input_hash": "abc"}


def validate_snapshot(item):
    required = {"target_gameweek", "cutoff_timestamp", "source_identity", "retrieval_timestamp", "source_version", "missing_data_status", "expected_points", "start_probability", "expected_minutes", "predicted_squad", "starting_xi", "bench", "captain", "vice_captain", "chip", "model_version", "input_hash"}
    if not required.issubset(item):
        raise ValueError("missing required snapshot field")
    for key in ("cutoff_timestamp", "retrieval_timestamp"):
        value = item[key]
        if value == "UNKNOWN" and key == "retrieval_timestamp":
            continue
        if not isinstance(value, str) or not (value.endswith("Z") or value[-6] in "+-"):
            raise ValueError("timestamp must be timezone-aware")
    for key in ("expected_points", "start_probability", "expected_minutes"):
        if not isinstance(item[key], (int, float)) or not math.isfinite(float(item[key])):
            raise ValueError("forecast must be finite")


def test_snapshot_schema_rejects_missing_and_naive_timestamps():
    for key in ("cutoff_timestamp", "retrieval_timestamp"):
        item = snapshot(); item.pop(key)
        with pytest.raises(ValueError): validate_snapshot(item)
    item = snapshot(); item["cutoff_timestamp"] = "2026-08-01T10:00:00"
    with pytest.raises(ValueError): validate_snapshot(item)


def test_snapshot_rejects_nonfinite_forecasts():
    for value in (math.nan, math.inf, -math.inf):
        item = snapshot(); item["expected_points"] = value
        with pytest.raises(ValueError): validate_snapshot(item)


def test_missing_actuals_do_not_score():
    score = ForecastScorecard().compute_metrics()
    assert score["status"] == "NO_TRACK_RECORD_YET"


def bare(cls):
    obj = cls.__new__(cls); obj.decisions = []; return obj


@pytest.mark.parametrize("cls", [CaptainBacktest, BenchBacktest, TransferBacktest])
def test_certificates_refuse_caller_ready_without_actuals(cls):
    obj = bare(cls)
    cert = obj.generate_certificate({"metrics": {"status": "READY", "sample_size": 0}}, "hash")
    assert cert["status"] != "CALIBRATED"
    assert "predictive" not in json.dumps(cert).lower()


def test_captain_missing_actual_is_withheld():
    obj = bare(CaptainBacktest)
    obj.decisions = [type("D", (), {"gw": 1, "recommended_captain_id": 1, "captain_ep_at_decision": 5.0})()]
    result = obj.compute_backtest({})
    assert result["metrics"]["status"] == "NO_TRACK_RECORD_YET"


def test_transfer_missing_actual_is_withheld():
    obj = bare(TransferBacktest)
    obj.decisions = [type("D", (), {"gw": 1, "player_in_id": 2, "player_out_id": 1, "ep_gain_projected": 3.0})()]
    result = obj.compute_backtest({})
    assert result["metrics"]["status"] == "NO_TRACK_RECORD_YET"
