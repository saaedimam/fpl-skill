import math
import pytest
from fpl_skill.elite_adapter import fetch_cohort, build_observation_records, standings_url, picks_url, transfers_url, bootstrap_url
from fpl_skill.observation import ingest
from fpl_skill.probabilistic_ep1 import PlayerDistribution, DistributionModelInputs, PlayerState


class FakeResp:
    def __init__(self, status=200, body=b""):
        self.status = status
        self.headers = {}
        self.body = body


class FakeTransport(ingest.Transport):
    def __init__(self):
        self.responses = {}
        self.hits = {}

    def set(self, url, payload):
        import json
        body = json.dumps(payload).encode()
        self.responses[url] = FakeResp(200, body)

    def set_bytes(self, url, body):
        self.responses[url] = FakeResp(200, body)

    def get(self, url):
        self.hits[url] = self.hits.get(url, 0) + 1
        return self.responses.get(url, FakeResp(404, b""))


def test_fetch_cohort_paginates_beyond_5_pages():
    t = FakeTransport()
    # Mock bootstrap
    t.set(bootstrap_url(), {"events": [{"id": 1, "is_current": True}]})
    # Mock 10 pages with 50 entries each = 500 managers
    for page in range(1, 11):
        results = [{"entry": (page - 1) * 50 + i + 1} for i in range(50)]
        has_next = page < 10
        t.set(standings_url(314, page), {"standings": {"results": results, "has_next": has_next}})

    cohort = fetch_cohort(t, top_n=500)
    assert len(cohort["entry_ids"]) == 500
    assert cohort["pagination"]["pages_fetched"] == 10
    assert cohort["pagination"]["has_next"] is False


def test_discover_top_paginates_beyond_5_pages():
    t = FakeTransport()
    # Mock 7 pages with 50 entries each = 350 rows
    for page in range(1, 8):
        results = [{"entry": (page - 1) * 50 + i + 1, "player_name": f"Manager {(page - 1) * 50 + i + 1}"} for i in range(50)]
        has_next = page < 7
        t.set(standings_url(314, page), {"standings": {"results": results, "has_next": has_next}})

    discovered = ingest.discover_top(t, n=320, league=314)
    assert len(discovered) == 320


def test_build_observation_records_fails_closed_on_missing_deadline():
    t = FakeTransport()
    cohort = {"entry_ids": [101]}
    bootstrap = {"events": []}  # Missing GW 1 deadline
    records = build_observation_records(t, cohort, gw=1, bootstrap=bootstrap, observed_at="2026-08-20T10:00:00Z")
    assert records == []


def test_build_observation_records_fails_closed_on_malformed_timestamp():
    t = FakeTransport()
    cohort = {"entry_ids": [101]}
    bootstrap = {"events": [{"id": 1, "deadline_time": "2026-08-20T10:00:00Z"}]}
    # Malformed observed_at
    records = build_observation_records(t, cohort, gw=1, bootstrap=bootstrap, observed_at="malformed-datetime")
    assert records == []


def test_build_observation_records_fails_closed_on_naive_timestamp():
    t = FakeTransport()
    cohort = {"entry_ids": [101]}
    bootstrap = {"events": [{"id": 1, "deadline_time": "2026-08-20T10:00:00"}]}  # Naive (no Z or tz)
    records = build_observation_records(t, cohort, gw=1, bootstrap=bootstrap, observed_at="2026-08-20T09:00:00Z")
    assert records == []


def test_build_observation_records_rejects_lookahead():
    t = FakeTransport()
    cohort = {"entry_ids": [101]}
    bootstrap = {"events": [{"id": 1, "deadline_time": "2026-08-20T10:00:00Z"}]}
    # observed_at is post-deadline
    records = build_observation_records(t, cohort, gw=1, bootstrap=bootstrap, observed_at="2026-08-20T10:00:01Z")
    assert records == []


def test_player_distribution_rejects_nonfinite():
    valid_args = dict(
        player_id=1,
        player_name="Salah",
        gw=5,
        team="LIV",
        position="MID",
        p10=2.0,
        p25=4.0,
        p50=6.0,
        p75=8.0,
        p90=10.0,
        mean=6.5,
        variance=4.0,
    )
    # Valid works
    dist = PlayerDistribution(**valid_args)
    assert dist.mean == 6.5

    # NaN in quantile
    with pytest.raises(ValueError, match="p50 must be finite"):
        PlayerDistribution(**{**valid_args, "p50": float("nan")})

    # Inf in variance
    with pytest.raises(ValueError, match="variance must be finite"):
        PlayerDistribution(**{**valid_args, "variance": float("inf")})

    # NaN in p_haul
    with pytest.raises(ValueError, match="p_haul must be finite"):
        PlayerDistribution(**{**valid_args, "p_haul": float("nan")})


def test_distribution_model_inputs_rejects_nonfinite():
    valid_args = dict(
        player_id=1,
        position="MID",
        status=PlayerState.AVAILABLE,
        team="LIV",
        opponent="CHE",
        gw=5,
        minutes_played_last_3=270.0,
        chance_of_playing_next_round=100.0,
        form=7.5,
        selected_by_percent=45.0,
        fixture_difficulty=3,
        is_home=True,
        opponent_strength_attack=1100.0,
        opponent_strength_defence=1050.0,
        team_goals_per_gw=2.0,
        team_conceded_per_gw=1.0,
    )
    # Valid works
    inputs = DistributionModelInputs(**valid_args)
    assert inputs.player_id == 1

    # NaN in form
    with pytest.raises(ValueError, match="form must be finite"):
        DistributionModelInputs(**{**valid_args, "form": float("nan")})

    # Inf in expected_goals
    with pytest.raises(ValueError, match="expected_goals must be finite"):
        DistributionModelInputs(**{**valid_args, "expected_goals": float("inf")})

    # NaN in chance_of_playing_next_round
    with pytest.raises(ValueError, match="chance_of_playing_next_round must be finite"):
        DistributionModelInputs(**{**valid_args, "chance_of_playing_next_round": float("nan")})
