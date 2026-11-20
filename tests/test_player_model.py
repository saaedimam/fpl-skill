"""
tests/test_player_model.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for the canonical FPL player model boundary.
"""
import pytest
from fpl_skill.player_model import (
    from_bootstrap_element, from_bootstrap_list,
    FPLPlayer, ELEMENT_TYPE_MAP, VALID_POSITIONS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk_element(**kwargs):
    """Build a minimal bootstrap element dict."""
    base = {
        "id": 1,
        "element_type": 1,
        "web_name": "Test",
        "team_short_name": "TST",
        "now_cost": 65,
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# ELEMENT_TYPE_MAP constants
# ---------------------------------------------------------------------------

def test_element_type_map_covers_all_four_positions():
    assert ELEMENT_TYPE_MAP == {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def test_valid_positions_matches_map():
    assert VALID_POSITIONS == {"GKP", "DEF", "MID", "FWD"}


# ---------------------------------------------------------------------------
# from_bootstrap_element — field mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("element_type,expected_position", [
    (1, "GKP"),
    (2, "DEF"),
    (3, "MID"),
    (4, "FWD"),
])
def test_element_type_maps_to_position(element_type, expected_position):
    el = _mk_element(element_type=element_type)
    player = from_bootstrap_element(el)
    assert player.position == expected_position


def test_player_id_mapped_from_id():
    el = _mk_element(id=999, element_type=2)
    player = from_bootstrap_element(el)
    assert player.player_id == 999


def test_web_name_preserved():
    el = _mk_element(web_name="Haaland")
    player = from_bootstrap_element(el)
    assert player.web_name == "Haaland"


def test_now_cost_preserved():
    el = _mk_element(now_cost=140)
    player = from_bootstrap_element(el)
    assert player.now_cost == 140


def test_team_from_team_short_name():
    el = _mk_element(team_short_name="MCI")
    player = from_bootstrap_element(el)
    assert player.team == "MCI"


def test_team_fallback_to_team_field():
    el = _mk_element()
    del el["team_short_name"]
    el["team"] = 1  # raw int team code
    player = from_bootstrap_element(el)
    assert player.team == "1"


def test_ep_next_parsed():
    el = _mk_element(ep_next="7.2")
    player = from_bootstrap_element(el)
    assert abs(player.ep_next - 7.2) < 1e-9


def test_element_type_preserved():
    el = _mk_element(element_type=3)
    player = from_bootstrap_element(el)
    assert player.element_type == 3


def test_to_dict_contains_required_keys():
    el = _mk_element(element_type=4)
    player = from_bootstrap_element(el)
    d = player.to_dict()
    assert "player_id" in d
    assert "position" in d
    assert "now_cost" in d
    assert "cost_int" in d
    assert d["cost_int"] == d["now_cost"]


# ---------------------------------------------------------------------------
# from_bootstrap_element — error cases
# ---------------------------------------------------------------------------

def test_missing_id_raises_value_error():
    with pytest.raises(ValueError, match="missing 'id'"):
        from_bootstrap_element({"element_type": 1, "web_name": "X"})


def test_unknown_element_type_raises_value_error():
    el = _mk_element(element_type=5)
    with pytest.raises(ValueError, match="Unknown element_type=5"):
        from_bootstrap_element(el)


def test_zero_element_type_raises_value_error():
    el = _mk_element(element_type=0)
    with pytest.raises(ValueError, match="Unknown element_type=0"):
        from_bootstrap_element(el)


# ---------------------------------------------------------------------------
# from_bootstrap_list — batch processing
# ---------------------------------------------------------------------------

def test_from_bootstrap_list_returns_players():
    elements = [_mk_element(id=i, element_type=(i % 4) + 1) for i in range(1, 5)]
    players = from_bootstrap_list(elements)
    assert len(players) == 4


def test_from_bootstrap_list_skips_bad_elements(capsys):
    elements = [
        _mk_element(id=1, element_type=1),   # valid
        _mk_element(id=2, element_type=99),  # invalid — should be skipped
        _mk_element(id=3, element_type=2),   # valid
    ]
    players = from_bootstrap_list(elements)
    assert len(players) == 2
    captured = capsys.readouterr()
    assert "SKIP" in captured.err


def test_from_bootstrap_list_empty_input():
    assert from_bootstrap_list([]) == []


# ---------------------------------------------------------------------------
# Round-trip stability
# ---------------------------------------------------------------------------

def test_to_dict_round_trip_position():
    el = _mk_element(element_type=3)
    p = from_bootstrap_element(el)
    d = p.to_dict()
    assert d["position"] == "MID"
    assert d["player_id"] == p.player_id
