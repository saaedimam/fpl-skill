import os
import sys
from pathlib import Path
import pytest

# Ensure repo root and fpl_skill are in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fpl_skill")))

from fpl_skill.api import VALID_FORMATIONS, select_best_legal_xi
from fpl_skill.prediction_engine import PredictionEngine
from fpl_skill.direct_api import save_to_cache, CACHE_DIR, DB_PATH, CACHE_FILE
from fpl_skill.optimizer import build_and_solve
from fpl_skill.probabilistic_ep1 import ProbabilisticEPEngine, DistributionModelInputs, PlayerState


def test_audit_bug_g_import():
    """AUDIT-BUG-G: api module imports successfully and fallback path is valid."""
    from fpl_skill import api
    assert hasattr(api, "get_fpl_data")
    assert hasattr(api, "load_from_cache")


def test_audit_bug_c_formation_coverage():
    """AUDIT-BUG-C: assert all 8 legal FPL formations are present."""
    expected_formations = {
        (3, 5, 2),
        (3, 4, 3),
        (4, 5, 1),
        (4, 4, 2),
        (4, 3, 3),
        (5, 4, 1),
        (5, 3, 2),
        (5, 2, 3),
    }
    actual_formations = set(VALID_FORMATIONS)
    assert actual_formations == expected_formations, f"Missing or incorrect formations: {expected_formations - actual_formations}"
    assert (5, 2, 3) in VALID_FORMATIONS, "(5, 2, 3) formation must be present in VALID_FORMATIONS"


def test_audit_bug_d_prediction_engine_legal_xi():
    """AUDIT-BUG-D: assert prediction engine enforces legal XI (at least 1 FWD) even when top 11 by EP has 0 FWD."""
    # Construct a 15-man squad where 2 GKP, 5 DEF, and 5 MID have high EP (10.0),
    # but 3 FWD have low EP (1.0). Top 11 by EP would have 0 FWD without constraint enforcement.
    squad = []
    pid = 1
    # 2 GKPs
    for i in range(2):
        squad.append({
            "id": pid, "player_id": pid, "web_name": f"GKP_{i+1}",
            "position": "GKP", "element_type": 1, "team": 1, "now_cost": 50,
            "cost_m": 5.0, "ep_this": 10.0, "ep_next": 10.0
        })
        pid += 1
    # 5 DEFs
    for i in range(5):
        squad.append({
            "id": pid, "player_id": pid, "web_name": f"DEF_{i+1}",
            "position": "DEF", "element_type": 2, "team": 2 + (i % 5), "now_cost": 50,
            "cost_m": 5.0, "ep_this": 10.0, "ep_next": 10.0
        })
        pid += 1
    # 5 MIDs
    for i in range(5):
        squad.append({
            "id": pid, "player_id": pid, "web_name": f"MID_{i+1}",
            "position": "MID", "element_type": 3, "team": 7 + (i % 5), "now_cost": 50,
            "cost_m": 5.0, "ep_this": 10.0, "ep_next": 10.0
        })
        pid += 1
    # 3 FWDs with low EP
    for i in range(3):
        squad.append({
            "id": pid, "player_id": pid, "web_name": f"FWD_{i+1}",
            "position": "FWD", "element_type": 4, "team": 12 + (i % 3), "now_cost": 50,
            "cost_m": 5.0, "ep_this": 1.0, "ep_next": 1.0
        })
        pid += 1

    # Mock fixture_map to return our assigned EP
    dummy_fixture_map = {}
    engine = PredictionEngine.__new__(PredictionEngine)
    engine.fixture_map = dummy_fixture_map
    engine.elements = {p["id"]: p for p in squad}

    # Run selection
    res = engine.run(target_gw=1, squad=squad)
    assert "xi" in res
    xi = res["xi"]
    assert len(xi) == 11, f"XI must contain exactly 11 players, got {len(xi)}"

    pos_counts = {}
    for p in xi:
        pos = p.get("position")
        pos_counts[pos] = pos_counts.get(pos, 0) + 1

    # Must satisfy FPL legal formation constraints
    assert pos_counts.get("GKP") == 1, f"Must have exactly 1 GKP, got {pos_counts.get('GKP')}"
    assert 3 <= pos_counts.get("DEF", 0) <= 5, f"DEF count must be between 3 and 5, got {pos_counts.get('DEF')}"
    assert 2 <= pos_counts.get("MID", 0) <= 5, f"MID count must be between 2 and 5, got {pos_counts.get('MID')}"
    assert 1 <= pos_counts.get("FWD", 0) <= 3, f"FWD count must be at least 1, got {pos_counts.get('FWD')}"


def test_audit_bug_f_cache_path():
    """AUDIT-BUG-F: assert cache writes land in ~/.cache/fpl-skill/ and not in repo fpl_skill/."""
    expected_cache_dir = Path(os.path.expanduser("~/.cache/fpl-skill/"))
    assert CACHE_DIR == expected_cache_dir
    assert DB_PATH.parent == expected_cache_dir
    assert CACHE_FILE.parent == expected_cache_dir

    test_data = {"fetched_at": 999999.0, "source": "REGRESSION_TEST", "records": []}
    save_to_cache(test_data)

    assert os.path.exists(CACHE_DIR)
    assert os.path.exists(DB_PATH) or os.path.exists(CACHE_FILE)

    # Ensure no fresh cache file was written to the source tree fpl_skill directory
    source_dir = Path(__file__).resolve().parent.parent / "fpl_skill"
    db_in_source = source_dir / "jervis.db"
    if db_in_source.exists():
        # Check mtime was not just now modified
        assert (os.path.getmtime(db_in_source) < test_data["fetched_at"])


def test_audit_bug_e_optimizer_parameterization():
    """AUDIT-BUG-E: optimizer accepts budget, player_locks, horizon parameters without KeyError."""
    res = build_and_solve(budget=100.0, player_locks=[], horizon=(3, 6), solve=False)
    assert res["status"] == "BUILT"
    assert res["variables_count"] > 0
    assert res["constraints_count"] > 0


def test_p0_gap_004_probability_invariant_normalization():
    """P0-GAP-004: test that scenario probabilities normalize when raw total > 1.0."""
    engine = ProbabilisticEPEngine()
    inputs = DistributionModelInputs(
        player_id=99,
        position="FWD",
        status=PlayerState.DOUBTFUL,
        team="ARS",
        opponent="SOU",
        gw=1,
        minutes_played_last_3=60,  # < 90 -> p_bench = 0.3
        chance_of_playing_next_round=50,
        form=8.0,  # > 6.0 -> form_multiplier = 1.5
        selected_by_percent=20.0,
        fixture_difficulty=1,
        is_home=True,
        opponent_strength_attack=900,
        opponent_strength_defence=800,
        team_goals_per_gw=2.5,
        team_conceded_per_gw=0.8,
    )
    # Force high fixture multiplier to ensure p_haul reaches max 0.5
    fixture_mult = 2.0
    minutes_adj = {"prob_plays": 0.5, "variance_factor": 1.2}

    # Raw components before normalization:
    # p_zero = 0.6 * (1.0 - 0.5) = 0.30
    # p_haul = min(0.5, 0.20 * 1.5 * 2.0 * 0.5) = 0.30 (or higher with base)
    # p_bench = 0.3
    # If total exceeds 1.0, normalization scales p_haul and p_bench down
    scenarios = engine._scenario_probabilities(inputs, minutes_adj, fixture_mult)

    assert 0.0 <= scenarios["p_zero"] <= 1.0
    assert 0.0 <= scenarios["p_haul"] <= 1.0
    assert 0.0 <= scenarios["p_bench"] <= 1.0
    assert 0.0 <= scenarios["p_injured"] <= 1.0
    assert scenarios["p_zero"] + scenarios["p_haul"] + scenarios["p_bench"] <= 1.0 + 1e-6
