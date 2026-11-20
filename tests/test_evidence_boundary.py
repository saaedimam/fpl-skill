import json
import math
from pathlib import Path
from datetime import datetime, timezone

import jsonschema
import pytest

from fpl_skill.backtest import CaptainBacktest, BenchBacktest, TransferBacktest
from fpl_skill.forecast_scorecard import ForecastScorecard

ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "schemas/predeadline-snapshot.schema.json").read_text())


def snapshot():
    return {"target_gameweek": 1, "cutoff_timestamp": "2026-08-01T10:00:00Z", "source_identity": "test", "retrieval_timestamp": "UNKNOWN", "source_version": "test-1", "missing_data_status": "none", "expected_points": 5.0, "start_probability": 0.8, "expected_minutes": 80.0, "predicted_squad": [], "starting_xi": [], "bench": [], "captain": 1, "vice_captain": 2, "chip": None, "model_version": "test", "input_hash": "abc"}


def test_snapshot_schema_rejects_missing_and_naive_timestamps():
    for key in ("cutoff_timestamp", "retrieval_timestamp"):
        item = snapshot(); item.pop(key)
        with pytest.raises(jsonschema.ValidationError): jsonschema.validate(item, SCHEMA, format_checker=jsonschema.FormatChecker())
    item = snapshot(); item["cutoff_timestamp"] = "2026-08-01T10:00:00"
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(item, SCHEMA, format_checker=jsonschema.FormatChecker())


def test_snapshot_rejects_nonfinite_forecasts():
    for value in (math.nan, math.inf, -math.inf):
        item = snapshot(); item["expected_points"] = value
        with pytest.raises((jsonschema.ValidationError, ValueError)):
            jsonschema.validate(item, SCHEMA, format_checker=jsonschema.FormatChecker())
            json.dumps(item, allow_nan=False)


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
