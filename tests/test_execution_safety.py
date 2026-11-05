"""Regression tests for fail-closed writes, sandbox rejection, and solver certificates.

No test in this module may contact fantasy.premierleague.com. urllib and any
injected session are asserted unused whenever a write is refused.
"""
from __future__ import annotations

import copy
import importlib.util
import urllib.request
from pathlib import Path

import pytest

from fpl_skill.approval_gate import ExecutionDenied
from fpl_skill.certification import generate_certificate, prove_upper_bound_admissible
from fpl_skill.execution import execute_account_mutation, expected_approval_token
from fpl_skill.historical import ImmutableSnapshot, Provenance, compute_sha256
from fpl_skill.optimality import certificate_from_solve
from fpl_skill.prediction_engine import PredictionEngine


REPO = Path(__file__).resolve().parent.parent
ENDPOINT = "/my-team/1/"
TEAM_ID = "1"


class RecordingSession:
    def __init__(self):
        self.calls = []

    def post(self, url, data=None, headers=None, **kwargs):
        self.calls.append({"url": url, "data": data, "headers": headers or {}, "kwargs": kwargs})
        return {"status": 200}


def _no_lookup():
    raise AssertionError("account lookup must not run for this refusal")


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError(f"unexpected network call args={args!r} kwargs={kwargs!r}")

    monkeypatch.setattr(urllib.request, "urlopen", explode)


def _roles():
    return (
        ["GKP"]
        + ["DEF"] * 4
        + ["MID"] * 4
        + ["FWD"] * 2
        + ["GKP", "DEF", "MID", "FWD"]
    )


def legal_picks():
    element_type = {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}
    picks = []
    for index, role in enumerate(_roles(), start=1):
        picks.append({
            "element": index,
            "element_type": element_type[role],
            "position": index,
            "team": f"Club{index}",
            "now_cost": 45,
            "is_captain": index == 6,
            "is_vice_captain": index == 10,
        })
    return picks


def _payload(picks):
    return {"chip": None, "picks": picks}


def _run(picks=None, *, token="valid", mode="approval", state="VERIFIED_CURRENT", **kwargs):
    picks = legal_picks() if picks is None else picks
    payload = kwargs.pop("payload", _payload(picks))
    if token == "valid":
        approval = expected_approval_token(TEAM_ID, ENDPOINT, payload)
    elif token == "missing":
        approval = None
    else:
        approval = token
    session = kwargs.pop("session", RecordingSession())
    execute_account_mutation(
        team_id=TEAM_ID,
        endpoint=ENDPOINT,
        payload=payload,
        picks=picks,
        approval_token=approval,
        ownership_state=state,
        mode=mode,
        session=session,
        state_provider=kwargs.pop("state_provider", _no_lookup),
        budget=kwargs.pop("budget", 100.0),
        **kwargs,
    )
    return session


def test_missing_approval_sends_nothing():
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="approval"):
        _run(token="missing", session=session)
    assert session.calls == []


def test_empty_approval_sends_nothing():
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="approval"):
        _run(token="   ", session=session)
    assert session.calls == []


@pytest.mark.parametrize("mode", ["advisory", "execute", "auto", ""])
def test_mode_that_does_not_permit_writes_sends_nothing(mode):
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="FPL_MODE"):
        _run(mode=mode, session=session)
    assert session.calls == []


def test_autonomous_without_token_sends_nothing():
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="approval"):
        _run(mode="autonomous", token="missing", session=session)
    assert session.calls == []


def test_tampered_payload_sends_nothing():
    picks = legal_picks()
    original = _payload(picks)
    token = expected_approval_token(TEAM_ID, ENDPOINT, original)
    tampered = copy.deepcopy(original)
    tampered["chip"] = "wildcard"
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="does not match"):
        _run(picks=picks, payload=tampered, token=token, session=session)
    assert session.calls == []


def test_tampered_token_sends_nothing():
    picks = legal_picks()
    token = expected_approval_token(TEAM_ID, ENDPOINT, _payload(picks))
    flipped = token[:-1] + ("0" if token[-1] != "0" else "1")
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="does not match"):
        _run(picks=picks, token=flipped, session=session)
    assert session.calls == []


@pytest.mark.parametrize("state", ["PUBLISHED_EVENT_PICKS", "HISTORICAL_FALLBACK", "UNAVAILABLE", ""])
def test_unverified_account_state_sends_nothing(state):
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="VERIFIED_CURRENT"):
        _run(state=state, session=session)
    assert session.calls == []


def test_missing_account_state_sends_nothing():
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="VERIFIED_CURRENT"):
        _run(state=None, session=session, state_provider=lambda: None)
    assert session.calls == []


def test_over_budget_squad_sends_nothing():
    picks = legal_picks()
    picks[0]["now_cost"] = 9000
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="budget"):
        _run(picks=picks, session=session)
    assert session.calls == []


def test_four_from_one_club_sends_nothing():
    picks = legal_picks()
    for pick in picks[:4]:
        pick["team"] = "ARS"
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="club"):
        _run(picks=picks, session=session)
    assert session.calls == []


def test_wrong_position_counts_send_nothing():
    picks = legal_picks()
    picks[1]["element_type"] = 1
    picks[2]["element_type"] = 1
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="positions"):
        _run(picks=picks, session=session)
    assert session.calls == []


def test_captain_outside_xi_sends_nothing():
    picks = legal_picks()
    for pick in picks:
        pick["is_captain"] = False
    picks[12]["is_captain"] = True
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="captain"):
        _run(picks=picks, session=session)
    assert session.calls == []


def test_vice_outside_xi_sends_nothing():
    picks = legal_picks()
    for pick in picks:
        pick["is_vice_captain"] = False
    picks[12]["is_vice_captain"] = True
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="vice"):
        _run(picks=picks, session=session)
    assert session.calls == []


def test_signal_only_evidence_sends_nothing():
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="evidence"):
        _run(
            session=session,
            evidence_claims=[{
                "level": "L5",
                "claim": "Player is essential",
                "fact_key": "transfer",
                "source": "podcast",
            }],
            proposed_action="TRANSFER",
        )
    assert session.calls == []


def test_future_snapshot_sends_nothing():
    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="firewall"):
        _run(
            session=session,
            decision_cutoff_utc="2026-09-01T10:00:00Z",
            historical_snapshots=[_snapshot("2026-09-01T10:00:01Z")],
        )
    assert session.calls == []


def test_authorized_write_uses_the_mock_session_once():
    session = _run(mode="approval")
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"].endswith(ENDPOINT)
    assert "Cookie" not in call["headers"]
    assert "cookie" not in {key.lower() for key in call["headers"]}


def test_autonomous_with_matching_token_uses_the_mock_session_once():
    session = _run(mode="autonomous")
    assert len(session.calls) == 1


def test_library_refuses_to_open_its_own_connection():
    picks = legal_picks()
    payload = _payload(picks)
    with pytest.raises(ExecutionDenied, match="network"):
        execute_account_mutation(
            team_id=TEAM_ID,
            endpoint=ENDPOINT,
            payload=payload,
            picks=picks,
            approval_token=expected_approval_token(TEAM_ID, ENDPOINT, payload),
            ownership_state="VERIFIED_CURRENT",
            mode="approval",
            state_provider=_no_lookup,
        )


def test_direct_script_post_is_refused_when_the_gate_is_closed():
    module = _load_all_python()
    with pytest.raises(ExecutionDenied, match="direct POST"):
        module._api_post("sessionid=test-session", "test-csrf", ENDPOINT, {"chip": None, "picks": []})


def test_script_transport_posts_only_after_the_gate(monkeypatch, tmp_path):
    module = _load_all_python()
    cookies = tmp_path / "cookies.txt"
    _write_fake_cookies(cookies)
    calls = []

    class _Response:
        status = 200

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=20):
        calls.append(req)
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    picks = legal_picks()
    payload = _payload(picks)
    transport = module._build_transport(str(cookies))
    with pytest.raises(ExecutionDenied, match="direct POST"):
        transport(ENDPOINT, payload)
    assert calls == []

    result = execute_account_mutation(
        team_id=TEAM_ID,
        endpoint=ENDPOINT,
        payload=payload,
        picks=picks,
        approval_token=expected_approval_token(TEAM_ID, ENDPOINT, payload),
        ownership_state="VERIFIED_CURRENT",
        mode="approval",
        transport=transport,
        state_provider=_no_lookup,
    )
    assert result["status"] == 200
    assert len(calls) == 1
    assert calls[0].get_method() == "POST"
    assert calls[0].full_url.endswith(ENDPOINT)


def test_all_python_apply_without_approval_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("FPL_MODE", "approval")
    module = _load_all_python()
    cookies = tmp_path / "cookies.txt"
    _write_fake_cookies(cookies)
    assert module.main(["--apply", "--cookies", str(cookies)]) != 0


def test_all_python_apply_in_advisory_mode_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("FPL_MODE", raising=False)
    module = _load_all_python()
    cookies = tmp_path / "cookies.txt"
    _write_fake_cookies(cookies)
    assert module.main(["--apply", "--cookies", str(cookies)]) != 0


def test_all_python_dry_run_does_not_apply():
    module = _load_all_python()
    assert module.main([]) == 0


def test_prediction_blocks_future_snapshots():
    engine = PredictionEngine.__new__(PredictionEngine)
    result = engine.run(
        1,
        squad=[],
        decision_cutoff_utc="2026-09-01T10:00:00Z",
        historical_snapshots=[_snapshot("2026-09-01T11:00:00Z")],
    )
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "TEMPORAL_LEAKAGE"


def test_prediction_admits_snapshots_at_or_before_cutoff():
    engine = PredictionEngine.__new__(PredictionEngine)
    engine.fixture_map = {}
    result = engine.run(
        1,
        squad=[{"player_id": 1, "position": "MID", "web_name": "A"}],
        decision_cutoff_utc="2026-09-01T10:00:00Z",
        historical_snapshots=[_snapshot("2026-09-01T09:00:00Z")],
        evidence_claims=[{
            "level": "L6",
            "claim": "Captain this player",
            "fact_key": "captain",
            "source": "social",
        }],
        proposed_action="CAPTAIN",
    )
    assert result.get("status") != "BLOCKED"
    assert result["historical_snapshots_admitted"] == 1
    assert result["executable"] is False
    assert result["action"] == "HOLD"
    assert result["evidence"]["confidence"] == "signal_only"


def test_optimality_certificate_follows_cbc_status(monkeypatch):
    from fpl_skill.optimizer import build_and_solve
    import fpl_skill.optimizer_legacy as legacy

    players = _milp_players()
    monkeypatch.setattr(legacy, "load", lambda horizon=(3, 6): _milp_load(players))
    solved = build_and_solve(budget=100.0, horizon=(1, 1), time_limit=30, msg=False)
    certificate = solved["optimality_certificate"]
    assert solved["status"] == "Optimal"
    assert certificate["solver_status"] == "Optimal"
    assert certificate["optimality_proven"] is True
    assert certificate["admissible"] is True
    assert certificate["certificate"] == "OPTIMAL"
    assert isinstance(certificate["objective_value"], float)
    assert certificate["constraint_recheck"]["valid"] is True

    monkeypatch.setattr(legacy, "load", lambda horizon=(3, 6): _milp_load(players))
    infeasible = build_and_solve(budget=0.1, horizon=(1, 1), time_limit=30, msg=False)
    refused = infeasible["optimality_certificate"]
    assert infeasible["status"] == "Infeasible"
    assert refused["solver_status"] == "Infeasible"
    assert refused["optimality_proven"] is False
    assert refused["admissible"] is False
    assert refused["objective_value"] is None
    assert refused["certificate"] == "NOT_CERTIFIED"


def test_optimal_status_with_illegal_squad_is_not_certified():
    squad = _milp_players()
    for player in squad[:4]:
        player["team"] = "ARS"
    xi = [player["player_id"] for player in squad[:11]]
    captain = next(player["player_id"] for player in squad if player["position"] == "MID")
    certificate = certificate_from_solve(
        solver_status="Optimal",
        objective_value=12.0,
        squad=squad,
        lineups={1: xi},
        captains={1: captain},
        budget=100.0,
    )
    assert certificate["optimality_proven"] is False
    assert certificate["admissible"] is False
    assert certificate["certificate"] == "NOT_CERTIFIED"
    assert any(item.startswith("club:") for item in certificate["constraint_recheck"]["violations"])


def test_non_optimal_status_is_not_certified_even_with_a_legal_squad():
    squad = _milp_players()
    xi = [player["player_id"] for player in squad[:11]]
    captain = next(player["player_id"] for player in squad if player["position"] == "FWD")
    certificate = certificate_from_solve(
        solver_status="Infeasible",
        objective_value=99.0,
        squad=squad,
        lineups={1: xi},
        captains={1: captain},
        budget=100.0,
    )
    assert certificate["solver_status"] == "Infeasible"
    assert certificate["objective_value"] is None
    assert certificate["optimality_proven"] is False


def test_upper_bound_admissibility_requires_checks():
    assert prove_upper_bound_admissible()["admissible"] is False
    assert prove_upper_bound_admissible()["verified"] is False
    failed = prove_upper_bound_admissible([{"bound": 1.0, "true_score": 2.0}])
    assert failed["admissible"] is False
    passed = prove_upper_bound_admissible([
        {"bound": 5.0, "true_score": 5.0},
        {"bound": 4.0, "true_score": 3.5},
    ])
    assert passed["admissible"] is True
    assert passed["verified"] is True


def test_generate_certificate_does_not_trust_a_hardcoded_flag():
    certificate = generate_certificate(
        {
            "squad": [],
            "optimization_metadata": {
                "candidate_space_size": 1,
                "branches_explored": 1,
                "branches_pruned": 0,
                "pruning_bound": "unchecked",
                "best_score": 1.0,
                "exhaustive": True,
                "optimality_proven": True,
                "solver_status": "NOT_SOLVED_BY_CBC",
            },
        },
        {
            "total_combinations": 1,
            "total_evaluated": 1,
            "total_pruned": 0,
            "best_score": 1.0,
            "elapsed_seconds": 0,
            "max_mid_ub": 0,
            "best_squad": [],
        },
        {"valid": False, "violations": ["no squad"]},
        {"formation_valid": False},
        {},
        "abc",
    )
    assert certificate["optimality_proven"] is False
    assert certificate["upper_bound_proof"]["admissible"] is False
    assert certificate["branch_and_bound"]["claimed_optimality_proven"] is True


def test_adapter_modules_do_not_post():
    for relative in ("fpl_skill/direct_api.py", "fpl_skill/account_adapter.py"):
        text = (REPO / relative).read_text(encoding="utf-8")
        assert 'method="POST"' not in text
        assert "method='POST'" not in text


def test_skill_frontmatter_has_description():
    text = (REPO / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1]
    assert "description:" in frontmatter


def test_mit_license_names_the_copyright_holder():
    text = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in text
    assert "Saaed Imam" in text
    assert "2026" in text


def test_packaged_manifest_matches_root_registry():
    root = (REPO / "MANIFEST.v2.json").read_text(encoding="utf-8")
    packaged = (REPO / "fpl_skill" / "MANIFEST.v2.json").read_text(encoding="utf-8")
    assert packaged == root


def _milp_players():
    players = []
    pid = 1
    for position, count, team_base in (("GKP", 2, 0), ("DEF", 5, 10), ("MID", 5, 20), ("FWD", 3, 30)):
        for offset in range(count):
            players.append({
                "player_id": pid,
                "web_name": f"{position}{offset}",
                "position": position,
                "team": f"T{team_base + offset}",
                "cost_int": 40,
                "now_cost": 40,
            })
            pid += 1
    return players


def _milp_load(players):
    ep = {player["player_id"]: {1: 2.0 if player["position"] == "FWD" else 1.0} for player in players}
    return players, {}, ep, "testhash", {}, [1]


def _snapshot(observed_at):
    data = {"points": 1}
    provenance = Provenance(
        source_uri="https://example.test/snapshot",
        observed_at=observed_at,
        source_hash=compute_sha256(data),
        record_type="bootstrap_static",
        authoritative=True,
    )
    return ImmutableSnapshot(
        snapshot_id="snap-" + observed_at.replace(":", ""),
        observed_at=observed_at,
        event=1,
        data=data,
        provenance=provenance,
    )


def _load_all_python():
    import importlib.machinery

    path = REPO / "all.python"
    loader = importlib.machinery.SourceFileLoader("all_python_script", str(path))
    spec = importlib.util.spec_from_loader("all_python_script", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _write_fake_cookies(path: Path) -> None:
    path.write_text(
        "# Netscape HTTP Cookie File\n"
        "example.test\tFALSE\t/\tFALSE\t0\tcsrftoken\ttest-csrf\n"
        "example.test\tFALSE\t/\tFALSE\t0\tsessionid\ttest-session\n",
        encoding="utf-8",
    )
