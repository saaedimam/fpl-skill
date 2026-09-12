from pathlib import Path
from unittest.mock import patch

import pytest

import fpl_skill.direct_api as direct_api
import fpl_skill.optimizer as optimizer
from fpl_skill.forecast_scorecard import CalibrationStoreError, ForecastScorecard


def test_expired_cache_never_returns_as_usable_data():
    cached = {
        "fetched_at": 100.0,
        "cache_timestamp": 100.0,
        "records": [{"player_id": 1}],
    }
    with patch.object(direct_api, "load_from_cache", return_value=cached), \
         patch.object(direct_api, "fetch_direct_fpl_data", return_value=None), \
         patch.object(direct_api.time, "time", return_value=100.0 + direct_api.CACHE_TTL_SECONDS + 1):
        result = direct_api.get_fpl_data()

    assert result["error"] == "FPL API unavailable and cached data is stale"
    assert result["is_stale"] is True
    assert "records" not in result


def test_optimizer_rejects_unavailable_data_instead_of_optimizing_empty_input():
    with patch.object(optimizer, "get_fpl_data", return_value={"error": "FPL API unavailable and cached data is stale"}):
        with pytest.raises(RuntimeError, match="FPL data loading failed"):
            optimizer.load(horizon=(5, 5))


def test_optimizer_rejects_empty_dataset():
    with patch.object(optimizer, "get_fpl_data", return_value={"records": []}):
        with pytest.raises(RuntimeError, match="empty dataset"):
            optimizer.load(horizon=(5, 5))


def test_corrupt_calibration_store_fails_closed(tmp_path: Path):
    path = tmp_path / "calibration.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(CalibrationStoreError, match="Invalid calibration store"):
        ForecastScorecard.load(path)


def test_non_array_calibration_store_fails_closed(tmp_path: Path):
    path = tmp_path / "calibration.json"
    path.write_text('{"records": []}', encoding="utf-8")

    with pytest.raises(CalibrationStoreError, match="root must be a JSON array"):
        ForecastScorecard.load(path)
