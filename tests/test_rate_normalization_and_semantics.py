import inspect
import math
import os
from unittest.mock import patch

import pytest

from fpl_skill.probabilistic_ep1 import DistributionModelInputs, PlayerState, ProbabilisticEPEngine
from fpl_skill.rate_normalization import gw_expected_contributions, normalize_player_rates
from fpl_skill.optimizer import load


def haaland():
    return {"player_id":411,"web_name":"Haaland","position":"FWD","status":"a","team":"MCI","minutes":270,"starts":3,"expected_goals":2.46,"expected_assists":0.50,"expected_goals_conceded":2.68,"form":6.0,"selected_by_percent":71.6,"chance_of_playing_next_round":None}


def make_inputs(p, gw_xg, gw_xa, expected_minutes, position=None):
    return DistributionModelInputs(
        player_id=p["player_id"], position=position or p["position"], status=PlayerState.AVAILABLE,
        team=p["team"], opponent="SUN", gw=5, minutes_played_last_3=p["minutes"],
        chance_of_playing_next_round=p.get("chance_of_playing_next_round"), expected_minutes=expected_minutes,
        form=p["form"], selected_by_percent=p["selected_by_percent"], fixture_difficulty=2, is_home=True,
        opponent_strength_attack=1000.0, opponent_strength_defence=1000.0,
        team_goals_per_gw=1.5, team_conceded_per_gw=1.0, gw_xg=gw_xg, gw_xa=gw_xa,
    )


def test_cumulative_xg_is_normalized_to_per90_rate():
    r=normalize_player_rates(haaland())
    assert r.xg90==pytest.approx(0.82,abs=0.001)
    assert r.xa90==pytest.approx(0.1666667,abs=0.001)


def test_gw_xg_scales_linearly_with_expected_minutes():
    p=haaland(); r=normalize_player_rates(p)
    x90,a90,_=gw_expected_contributions(p,90)
    x45,a45,_=gw_expected_contributions(p,45)
    assert x90==pytest.approx(r.xg90); assert x45==pytest.approx(r.xg90*0.5); assert a45==pytest.approx(a90*0.5)


def test_probability_and_expected_minutes_are_distinct():
    r=normalize_player_rates(haaland())
    assert 0<=r.p_start<=1 and 0<=r.p_sub<=1 and 0<=r.expected_minutes<=90
    assert not math.isclose(r.expected_minutes,r.p_start)


def test_unavailable_distribution_collapses():
    e=ProbabilisticEPEngine(); p=haaland(); r=normalize_player_rates(p)
    i=make_inputs({**p,"status":"i"},0,0,0); i.status=PlayerState.INJURED
    d=e.generate_distribution(i)
    assert d.mean==0 and d.p10==d.p25==d.p50==d.p75==d.p90==0 and d.p_zero==1


def test_optimizer_source_is_bound_to_probabilistic_engine():
    import fpl_skill.optimizer as m
    s=inspect.getsource(m)
    assert "ProbabilisticEPEngine" in s and "diag[\"mean\"]" in s
    assert "calculate_player_gw_ep" not in s


def test_optimizer_load_binds_mean_not_p50():
    records=[{
        "player_id":411,"web_name":"Haaland","team":"MCI","position":"FWD","status":"a","now_cost":155,
        "minutes":270,"starts":3,"expected_goals":2.46,"expected_assists":0.5,"expected_goals_conceded":2.68,
        "form":6.0,"selected_by_percent":71.6,"chance_of_playing_next_round":None,"gameweek_history":"[]"},
        {"player_id":412,"web_name":"Dummy","team":"SUN","position":"DEF","status":"a","now_cost":40,"minutes":0,"starts":0,
         "expected_goals":0,"expected_assists":0,"expected_goals_conceded":0,"form":0,"selected_by_percent":0,"chance_of_playing_next_round":None,"gameweek_history":"[]"},
        {"position":"FIXTURE","player_id":None,"gameweek_history":{"fixture_id":1,"gameweek":5,"home_team":"MCI","away_team":"SUN"},"team_h_difficulty":2,"team_a_difficulty":5}]
    with patch("fpl_skill.optimizer.get_fpl_data",return_value={"records":records}):
        players,_,ep,_,_,_=load(horizon=(5,5))
    p=next(x for x in players if x["player_id"]==411); d=p["_distribution_diagnostics"][5]
    assert ep[411][5]==pytest.approx(d["mean"]); assert d["mean"]!=d["p50"]; assert d["mean"]>0


def test_gw5_sanity_benchmarks():
    e=ProbabilisticEPEngine(); p=haaland(); r=normalize_player_rates(p); x,a,_=gw_expected_contributions(p,r.expected_minutes)
    d=e.generate_distribution(make_inputs(p,x,a,r.expected_minutes))
    f={**p,"player_id":398,"web_name":"Foden","position":"MID","minutes":195,"starts":2,"expected_goals":1.61,"expected_assists":0.86,"form":2.8,"selected_by_percent":3.9}
    rf=normalize_player_rates(f); xf,af,_=gw_expected_contributions(f,rf.expected_minutes); df=e.generate_distribution(make_inputs(f,xf,af,rf.expected_minutes,"MID"))
    assert 5.5<=d.mean<=7.5
    assert 2.5<=df.mean<=4.5


def test_standard_non_dgw_ep_sanity_guard():
    p=haaland(); r=normalize_player_rates(p); x,a,_=gw_expected_contributions(p,r.expected_minutes); d=ProbabilisticEPEngine().generate_distribution(make_inputs(p,x,a,r.expected_minutes))
    assert 0.0<=d.mean<=12.0


def test_calibration_gate_is_not_falsely_ready():
    from fpl_skill.forecast_scorecard import ForecastScorecard
    s=ForecastScorecard(); assert not s.sample_gate_passed(); assert s.compute_metrics()["status"]=="NO_TRACK_RECORD_YET"


@pytest.mark.skipif(os.getenv("FPL_LIVE_TEST")!="1",reason="Set FPL_LIVE_TEST=1 to exercise the live FPL data path")
def test_live_fpl_gw5_rate_normalization():
    from fpl_skill.api import get_fpl_data
    raw=get_fpl_data(); p=next(x for x in raw.get("records",[]) if x.get("player_id")==411); r=normalize_player_rates(p)
    assert r.xg90 < float(p.get("expected_goals") or 0.0) or r.xg90==0.0
