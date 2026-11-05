"""Prove the test-only network guard rejects FPL write paths.

Covers the approved ``execute_account_mutation`` refusal path and lower-level
clients (raw ``http.client``, ``urllib.request.Request`` with method=POST,
raw ``socket``). These tests require the autouse guard from
``tests/conftest.py``.

Monkeypatch limits are documented in ``tests/README.md`` and
``tests/network_isolation.py``. CI additionally runs under ``unshare --net``.
"""
from __future__ import annotations

import http.client
import io
import socket
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fpl_skill.approval_gate import ExecutionDenied
from fpl_skill.approval_issuer import issue_approval
from fpl_skill.approval_verify import NonceStore
from fpl_skill.execution import execute_account_mutation
from tests.network_isolation import (
    NetworkGuardError,
    assert_connect_allowed,
    is_fpl_host,
    is_loopback_host,
)


FPL_HOST = "fantasy.premierleague.com"
ENDPOINT = "/my-team/1/"
TEAM_ID = "1"
FIXED_NOW = datetime(2026, 11, 5, 16, 0, tzinfo=timezone.utc)


def _openssl_keys(directory: Path):
    private_path = directory / "sign.pem"
    public_path = directory / "verify.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["openssl", "pkey", "-in", str(private_path), "-pubout", "-out", str(public_path)],
        check=True,
        capture_output=True,
    )
    return private_path.read_text(encoding="utf-8"), public_path.read_text(encoding="utf-8")


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


def bootstrap_for(picks):
    return {
        pick["element"]: {
            "id": pick["element"],
            "element_type": pick["element_type"],
            "team": pick["team"],
            "now_cost": pick["now_cost"],
        }
        for pick in picks
    }


def test_loopback_helpers():
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("::1")
    assert is_loopback_host("localhost")
    assert not is_loopback_host(FPL_HOST)
    assert is_fpl_host(FPL_HOST)
    assert is_fpl_host("www.fantasy.premierleague.com")
    assert not is_fpl_host("example.com")


def test_assert_connect_allowed_blocks_external():
    with pytest.raises(NetworkGuardError, match="non-loopback"):
        assert_connect_allowed((FPL_HOST, 443))
    with pytest.raises(NetworkGuardError, match="non-loopback"):
        assert_connect_allowed(("1.1.1.1", 443))
    assert_connect_allowed(("127.0.0.1", 9))


def test_execute_account_mutation_sends_nothing_under_guard(tmp_path, monkeypatch):
    """Approved path must still refuse and never open a transport."""
    calls = []

    def boom(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("urlopen must not be reached")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    picks = legal_picks()
    payload = _payload(picks)
    private_pem, public_pem = _openssl_keys(tmp_path)
    approval = issue_approval(
        team_id=TEAM_ID,
        endpoint=ENDPOINT,
        payload=payload,
        private_key_pem=private_pem,
        stdin=io.StringIO("approve\n"),
        stdout=io.StringIO(),
        now=FIXED_NOW,
    )

    class RecordingSession:
        def __init__(self):
            self.calls = []

        def post(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"status": 200}

    session = RecordingSession()
    with pytest.raises(ExecutionDenied, match="does not authorize"):
        execute_account_mutation(
            team_id=TEAM_ID,
            endpoint=ENDPOINT,
            payload=payload,
            picks=picks,
            approval=approval,
            public_key_pem=public_pem,
            mode="approval",
            session=session,
            account_state_reader=lambda: "VERIFIED_CURRENT",
            bootstrap_reader=lambda: bootstrap_for(picks),
            nonce_store=NonceStore(tmp_path / "nonces"),
            clock=lambda: FIXED_NOW,
        )
    assert session.calls == []
    assert calls == []


def test_raw_socket_connect_to_fpl_host_rejected():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(NetworkGuardError, match="non-loopback"):
            sock.connect((FPL_HOST, 443))
    finally:
        sock.close()


def test_socket_create_connection_to_external_rejected():
    with pytest.raises(NetworkGuardError, match="non-loopback"):
        socket.create_connection((FPL_HOST, 443), timeout=1)


def test_http_client_post_to_fpl_host_rejected():
    conn = http.client.HTTPSConnection(FPL_HOST, timeout=1)
    try:
        with pytest.raises(NetworkGuardError, match="blocked POST to FPL host"):
            conn.request("POST", "/api/my-team/1/")
    finally:
        conn.close()


def test_urllib_request_post_to_fpl_host_rejected():
    req = urllib.request.Request(
        f"https://{FPL_HOST}/api/my-team/1/",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(NetworkGuardError):
        urllib.request.urlopen(req, timeout=1)


def test_urllib_request_put_to_fpl_host_rejected():
    req = urllib.request.Request(
        f"https://{FPL_HOST}/a/api/event/1/chip/",
        data=b"{}",
        method="PUT",
    )
    with pytest.raises(NetworkGuardError):
        urllib.request.urlopen(req, timeout=1)


def test_http_client_mutation_via_loopback_host_header_rejected():
    """Method+host check must fire even when the TCP peer is loopback."""
    conn = http.client.HTTPConnection("127.0.0.1", 9, timeout=0.2)
    try:
        with pytest.raises(NetworkGuardError, match="blocked POST to FPL host"):
            conn.request(
                "POST",
                "/api/my-team/1/",
                body=b"{}",
                headers={"Host": FPL_HOST},
            )
    finally:
        conn.close()


def test_egress_blocked_under_guard():
    with pytest.raises(NetworkGuardError, match="non-loopback"):
        socket.create_connection(("1.1.1.1", 53), timeout=1)


def test_netns_only_loopback_when_flagged():
    """When CI sets FPL_TEST_NETNS=1, assert the kernel view is loopback-only."""
    import os

    if os.environ.get("FPL_TEST_NETNS", "").strip() != "1":
        pytest.skip("FPL_TEST_NETNS not set (not running inside CI netns harness)")
    non_loop = []
    for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
        name = line.split(":", 1)[0].strip()
        if name and name != "lo":
            non_loop.append(name)
    assert non_loop == [], f"expected only loopback in netns, found {non_loop}"
