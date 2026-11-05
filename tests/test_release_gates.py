"""Release gates: current-data gate and regression gate.

Uses the committed synthetic live-schema sample ``tests/data/live_fpl_sample.json``
(public ``/api/bootstrap-static/`` + ``/api/fixtures/`` shape, no personal data).
These tests must never be skipped; ``tests/compute_release_hash.py`` refuses a
release whose manifest does not register this file.
"""
import copy
import json
import math
from pathlib import Path

import pytest

SAMPLE = json.loads((Path(__file__).parent / "data" / "live_fpl_sample.json").read_text(encoding="utf-8"))
POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def _err():
    from fpl_skill.current_data import CurrentDataError
    return CurrentDataError


def _fm():
    from fpl_skill.api import build_fixture_map
    return build_fixture_map(SAMPLE["fixtures"], teams=SAMPLE["teams"])


def _squad():
    by = {}
    for e in SAMPLE["elements"]:
        by.setdefault(e["element_type"], []).append(e)
    picks = by[1][:2] + by[2][:5] + by[3][:5] + by[4][:3]
    return [dict(e, player_id=e["id"], position=POS[e["element_type"]], cost_m=e["now_cost"] / 10) for e in picks]


def _all():
    return [dict(e, player_id=e["id"], position=POS[e["element_type"]], cost_m=e["now_cost"] / 10) for e in SAMPLE["elements"]]


def _engine():
    from fpl_skill.prediction_engine import PredictionEngine
    eng = PredictionEngine.__new__(PredictionEngine)
    eng.bootstrap = {k: SAMPLE[k] for k in ("events", "teams", "elements")}
    eng.fixtures = SAMPLE["fixtures"]
    eng.events = SAMPLE["events"]
    eng.fixture_map = _fm()
    eng.elements = {e["id"]: e for e in SAMPLE["elements"]}
    return eng


# --- live-schema parsing -------------------------------------------------

def test_live_schema_fixture_map_is_correct():
    fm = _fm()
    # GW10: (1 v 3), (2 v 5), (4 v 6)
    assert len(fm[10][1]) == 1 and fm[10][1][0]["opp"] == 3 and fm[10][1][0]["is_home"] is True
    assert fm[10][3][0]["opp"] == 1 and fm[10][3][0]["is_home"] is False
    src = next(f for f in SAMPLE["fixtures"] if f["event"] == 10 and f["team_h"] == 1)
    assert fm[10][1][0]["fdr"] == src["team_h_difficulty"]
    assert fm[10][3][0]["fdr"] == src["team_a_difficulty"]
    assert fm[10][1][0]["kickoff_time"] == src["kickoff_time"] and fm[10][1][0]["finished"] is False
    # team aliases: id, name and short_name resolve to the same fixtures
    assert fm[10]["Alpha"] == fm[10][1] == fm[10]["ALP"]
    # unscheduled fixture (event None) is ignored; DGW preserved
    assert len(fm[12][4]) == 2 and len(fm[12][6]) == 2
    assert sum(len(v) for k, v in fm[9].items() if isinstance(k, int)) == 6


@pytest.mark.parametrize("payload", [None, [], {}, [{"foo": 1}], "nope"])
def test_missing_empty_or_unrecognized_fixtures_raise(payload):
    from fpl_skill.api import build_fixture_map
    with pytest.raises(_err()):
        build_fixture_map(payload)


def test_blank_gameweek_is_explicit():
    from fpl_skill.current_data import blank_teams
    fm = _fm()
    assert blank_teams(fm, 11, [1, 2, 3, 4, 5, 6]) == [4, 6]
    assert blank_teams(fm, 10, [1, 2, 3, 4, 5, 6]) == []
    with pytest.raises(_err()):
        blank_teams(fm, 30, [1])  # GW with no fixtures at all = missing data, not a blank


def test_prediction_reports_blank_players():
    res = _engine().run(11, squad=_squad())
    blank_ids = {p["player_id"] for p in _squad() if p["team"] in (4, 6)}
    assert set(res["blank_gameweek_players"]) == blank_ids


# --- projections ----------------------------------------------------------

def test_projection_pipeline_nonzero_for_players_with_fixtures():
    from fpl_skill.api import calculate_player_gw_ep
    fm = _fm()
    for p in _squad():
        ep = calculate_player_gw_ep(p, 10, fm)
        assert ep > 0 and not math.isnan(ep), (p["web_name"], ep)
    res = _engine().run(10, squad=_squad())
    assert res["total_ep"] > 0 and res["captain"]["ep"] > 0


def test_all_zero_projections_raise():
    from fpl_skill.current_data import assert_projections_valid
    with pytest.raises(_err()):
        assert_projections_valid({1: 0.0, 2: 0.0})
    with pytest.raises(_err()):
        assert_projections_valid({1: float("nan"), 2: 3.0})
    with pytest.raises(_err()):
        assert_projections_valid({})
    assert_projections_valid({1: 0.0, 2: 1.2})


def test_prediction_engine_refuses_all_zero_projections():
    eng = _engine()
    sq = [dict(p, team=99) for p in _squad()]  # teams with no fixtures -> all zero
    with pytest.raises(_err()):
        eng.run(10, squad=sq)


def test_prediction_engine_refuses_missing_fixtures_for_gw():
    eng = _engine()
    eng.fixture_map = {g: {} for g in range(1, 39)}
    with pytest.raises(_err()):
        eng.run(10, squad=_squad())


# --- planning horizon / already-played gameweeks ----------------------------

def test_planning_horizon_comes_from_live_events():
    from fpl_skill.current_data import planning_horizon
    assert planning_horizon(SAMPLE["events"]) == [10, 11, 12, 13]


@pytest.mark.parametrize("gws", [[3, 4, 5, 6], [9, 10], [8]])
def test_transfer_recommendations_for_played_gameweeks_rejected(gws):
    from fpl_skill.api import find_best_one_ft
    with pytest.raises(_err()):
        find_best_one_ft(_squad(), _all(), bank=1.0, fixture_map=_fm(), gameweeks=gws, events=SAMPLE["events"])


def test_transfer_recommendation_uses_live_horizon():
    from fpl_skill.api import find_best_one_ft
    res = find_best_one_ft(_squad(), _all(), bank=1.0, fixture_map=_fm(), events=SAMPLE["events"])
    assert res["horizon"] == [10, 11, 12, 13]
    assert res["horizon_ep"] > 0


def test_prediction_refuses_played_gameweek():
    with pytest.raises(_err()):
        _engine().run(9, squad=_squad())


def test_transfer_intelligence_refuses_played_gameweek():
    from fpl_skill.transfer_intelligence import TransferIntelligence
    ti = TransferIntelligence.__new__(TransferIntelligence)
    ti.bootstrap = {k: SAMPLE[k] for k in ("events", "teams", "elements")}
    with pytest.raises(_err()):
        ti.evaluate_transfers(4)


def test_no_hardcoded_gw3_6_horizon_in_planning_paths():
    root = Path(__file__).resolve().parent.parent / "fpl_skill"
    for rel in ("transfer_intelligence.py", "optimizer.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert "[3, 4, 5, 6]" not in src and "(3,6)" not in src.replace(" ", ""), rel


# --- user-facing surface ---------------------------------------------------

def test_cli_predict_surfaces_gate_failure(monkeypatch):
    from click.testing import CliRunner
    import fpl_skill.prediction_engine as pe
    from fpl_skill import cli as cli_mod

    def boom(*a, **k):
        raise _err()("All 15 player projections are zero for GW10 prediction")
    monkeypatch.setattr(pe, "PredictionEngine", boom)
    res = CliRunner().invoke(cli_mod.cli, ["predict", "--gw", "10", "--squad-ids", "1,2"])
    assert res.exit_code == cli_mod.CURRENT_DATA_EXIT
    assert "CURRENT-DATA GATE FAILED" in res.output


def test_cli_predict_refuses_played_gameweek(monkeypatch):
    from click.testing import CliRunner
    import fpl_skill.prediction_engine as pe
    from fpl_skill import cli as cli_mod
    eng = _engine()
    monkeypatch.setattr(pe, "PredictionEngine", lambda team_id: eng)
    ids = ",".join(str(p["id"]) for p in _squad())
    res = CliRunner().invoke(cli_mod.cli, ["predict", "--gw", "9", "--squad-ids", ids])
    assert res.exit_code == cli_mod.CURRENT_DATA_EXIT and "already-played" in res.output
    ok = CliRunner().invoke(cli_mod.cli, ["predict", "--squad-ids", ids])
    assert ok.exit_code == 0, ok.output
    assert '"target_gw": 10' in ok.output
