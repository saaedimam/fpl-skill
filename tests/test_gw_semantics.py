"""
tests/test_gw_semantics.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for the five explicit gameweek accessors in FPLAccountAdapter.
No network calls — all bootstrap data is mocked.
"""
import datetime
import pytest
from unittest.mock import patch
from fpl_skill.account_adapter import FPLAccountAdapter, DataMode


def _mk_bootstrap(events: list) -> dict:
    return {"events": events, "elements": [], "teams": []}


def _future(offset_hours: int = 24) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=offset_hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _past(offset_hours: int = 24) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=offset_hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture()
def adapter():
    return FPLAccountAdapter("99999")


# ---------------------------------------------------------------------------
# current_gameweek()
# ---------------------------------------------------------------------------

def test_current_gameweek_returns_is_current_gw(adapter):
    bootstrap = _mk_bootstrap([
        {"id": 4, "deadline_time": _past(120), "is_current": False, "is_next": False, "finished": True},
        {"id": 5, "deadline_time": _past(48), "is_current": True, "is_next": False, "finished": False},
        {"id": 6, "deadline_time": _future(48), "is_current": False, "is_next": True, "finished": False},
    ])
    with patch.object(adapter, "get_bootstrap", return_value=bootstrap):
        assert adapter.current_gameweek() == 5


def test_current_gameweek_fallback_when_no_is_current(adapter):
    # If no event has is_current=True, falls back to most recent past deadline
    bootstrap = _mk_bootstrap([
        {"id": 1, "deadline_time": _past(200), "is_current": False, "is_next": False, "finished": True},
        {"id": 2, "deadline_time": _past(100), "is_current": False, "is_next": False, "finished": True},
        {"id": 3, "deadline_time": _future(50), "is_current": False, "is_next": False, "finished": False},
    ])
    with patch.object(adapter, "get_bootstrap", return_value=bootstrap):
        gw = adapter.current_gameweek()
        assert gw == 2  # most recent past event


# ---------------------------------------------------------------------------
# next_gameweek()
# ---------------------------------------------------------------------------

def test_next_gameweek_returns_is_next_gw(adapter):
    bootstrap = _mk_bootstrap([
        {"id": 5, "deadline_time": _past(48), "is_current": True, "is_next": False},
        {"id": 6, "deadline_time": _future(48), "is_current": False, "is_next": True},
    ])
    with patch.object(adapter, "get_bootstrap", return_value=bootstrap):
        assert adapter.next_gameweek() == 6


def test_next_gameweek_fallback_current_plus_one(adapter):
    bootstrap = _mk_bootstrap([
        {"id": 5, "deadline_time": _past(48), "is_current": True, "is_next": False},
        {"id": 6, "deadline_time": _future(48), "is_current": False, "is_next": False},
    ])
    with patch.object(adapter, "get_bootstrap", return_value=bootstrap):
        # No is_next flag → current+1
        assert adapter.next_gameweek() == 6


# ---------------------------------------------------------------------------
# next_deadline()
# ---------------------------------------------------------------------------

def test_next_deadline_returns_first_future_deadline(adapter):
    future_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=72)
    future_str = future_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    bootstrap = _mk_bootstrap([
        {"id": 5, "deadline_time": _past(48)},
        {"id": 6, "deadline_time": future_str},
    ])
    with patch.object(adapter, "get_bootstrap", return_value=bootstrap):
        dl = adapter.next_deadline()
        assert isinstance(dl, datetime.datetime)
        assert dl > datetime.datetime.now(datetime.timezone.utc)


# ---------------------------------------------------------------------------
# latest_completed_gameweek()
# ---------------------------------------------------------------------------

def test_latest_completed_gameweek_returns_max_finished(adapter):
    bootstrap = _mk_bootstrap([
        {"id": 3, "deadline_time": _past(200), "finished": True},
        {"id": 4, "deadline_time": _past(100), "finished": True},
        {"id": 5, "deadline_time": _past(48), "finished": False, "is_current": True},
    ])
    with patch.object(adapter, "get_bootstrap", return_value=bootstrap):
        assert adapter.latest_completed_gameweek() == 4


def test_latest_completed_gameweek_zero_when_none_finished(adapter):
    bootstrap = _mk_bootstrap([
        {"id": 1, "deadline_time": _future(100), "finished": False},
    ])
    with patch.object(adapter, "get_bootstrap", return_value=bootstrap):
        assert adapter.latest_completed_gameweek() == 0


# ---------------------------------------------------------------------------
# latest_published_picks_gameweek()
# ---------------------------------------------------------------------------

def test_latest_published_picks_gw_equals_current(adapter):
    bootstrap = _mk_bootstrap([
        {"id": 5, "deadline_time": _past(48), "is_current": True},
        {"id": 6, "deadline_time": _future(48), "is_current": False, "is_next": True},
    ])
    with patch.object(adapter, "get_bootstrap", return_value=bootstrap):
        assert adapter.latest_published_picks_gameweek() == adapter.current_gameweek()


# ---------------------------------------------------------------------------
# get_active_event_id() is a documented alias for current_gameweek()
# ---------------------------------------------------------------------------

def test_get_active_event_id_is_alias_for_current_gameweek(adapter):
    bootstrap = _mk_bootstrap([
        {"id": 5, "deadline_time": _past(48), "is_current": True},
    ])
    with patch.object(adapter, "get_bootstrap", return_value=bootstrap):
        assert adapter.get_active_event_id() == adapter.current_gameweek()


# ---------------------------------------------------------------------------
# DataMode in get_state()
# ---------------------------------------------------------------------------

def test_get_state_includes_data_mode_authenticated(adapter):
    bootstrap = _mk_bootstrap([
        {"id": 5, "deadline_time": _past(48), "is_current": True},
    ])
    with patch.object(adapter, "get_bootstrap", return_value=bootstrap):
        with patch.object(adapter, "_fetch_authenticated") as mock_fetch:
            mock_fetch.return_value = {"picks": [{"element": i} for i in range(1, 16)]}
            state = adapter.get_state(5)
            assert state["data_mode"] == DataMode.AUTHENTICATED_CURRENT.value


def test_get_state_includes_data_mode_public_published(adapter):
    bootstrap = _mk_bootstrap([
        {"id": 5, "deadline_time": _past(48), "is_current": True},
    ])
    with patch.object(adapter, "get_bootstrap", return_value=bootstrap):
        with patch.object(adapter, "_fetch_authenticated") as mock_fetch:
            def side(path):
                if "/my-team/" in path:
                    return None
                if "/event/5/picks/" in path:
                    return {"picks": [{"element": i} for i in range(1, 16)]}
                return None
            mock_fetch.side_effect = side
            state = adapter.get_state(5)
            assert state["data_mode"] == DataMode.PUBLIC_PUBLISHED.value


def test_get_state_includes_data_mode_unavailable(adapter):
    bootstrap = _mk_bootstrap([
        {"id": 5, "deadline_time": _past(48), "is_current": True},
    ])
    with patch.object(adapter, "get_bootstrap", return_value=bootstrap):
        with patch.object(adapter, "_fetch_authenticated", return_value=None):
            state = adapter.get_state(5)
            assert state["data_mode"] == DataMode.UNAVAILABLE.value
