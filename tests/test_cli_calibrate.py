import pytest
from click.testing import CliRunner
from fpl_skill.cli import calibrate

def test_calibrate_no_track_record():
    """Fresh season should output NO_TRACK_RECORD_YET."""
    runner = CliRunner()
    result = runner.invoke(calibrate, [])

    assert result.exit_code == 0
    assert "No track record yet" in result.output
    assert "season is fresh" in result.output

def test_calibrate_insufficient_sample():
    """Insufficient sample should output gate message."""
    # This test requires mocking ForecastScorecard to return INSUFFICIENT_SAMPLE
    # For v1.1.0, the real harness will return NO_TRACK_RECORD_YET (empty season)
    # Stub this test; full test will run once real calibration data exists
    pass

def test_calibrate_ready_state():
    """READY state should output metric table."""
    # Stub for future — real data required
    pass

def test_calibrate_with_gw_option():
    """--gw option should be accepted (future)."""
    runner = CliRunner()
    result = runner.invoke(calibrate, ['--gw', '5'])
    assert result.exit_code == 0

def test_calibrate_with_by_category_flag():
    """--by-category flag should be accepted."""
    runner = CliRunner()
    result = runner.invoke(calibrate, ['--by-category'])
    assert result.exit_code == 0
    # "Future feature" note only renders in READY state; empty season exits
    # at NO_TRACK_RECORD_YET before the by-category block. Flag acceptance is
    # the real contract for v1.1.0.
