"""Authenticated account reads are GET-only and do not leak the session cookie."""
import json
from urllib.error import URLError

import fpl_skill.account_adapter as adapter_module
from fpl_skill.account_adapter import FPLAccountAdapter

SECRET = "session-secret-do-not-log"


class _Response:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _install(monkeypatch, responses):
    calls = []

    def urlopen(req, timeout=10):
        if isinstance(req, str):
            url = req
            method = "GET"
            data = None
            headers = {}
        else:
            url = req.full_url
            method = req.get_method()
            data = req.data
            headers = {key.lower(): value for key, value in req.header_items()}
        calls.append({"url": url, "method": method, "data": data, "headers": headers})
        if url not in responses:
            raise URLError("unexpected url")
        return _Response(responses[url])

    monkeypatch.setenv("FPL_SESSION_COOKIE", SECRET)
    monkeypatch.setattr(adapter_module.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(
        adapter_module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("keychain must not run")),
    )
    return calls


def _assert_cookie_not_exposed(document, capsys):
    text = json.dumps(document)
    captured = capsys.readouterr()
    assert SECRET not in text
    assert SECRET not in captured.out
    assert SECRET not in captured.err


def test_authenticated_profile_get_keeps_cookie_off_the_result(monkeypatch, capsys):
    calls = _install(
        monkeypatch,
        {
            "https://fantasy.premierleague.com/api/entry/7/": {"name": "Shown"},
            "https://fantasy.premierleague.com/api/my-team/7/": {
                "transfers": {"bank": 5, "limit": 1, "made": 0},
            },
        },
    )
    profile = FPLAccountAdapter("7").get_profile()
    authenticated = [call for call in calls if call["url"].endswith("/my-team/7/")]
    public = [call for call in calls if "/entry/7/" in call["url"]]
    assert len(authenticated) == 1
    assert authenticated[0]["method"] == "GET"
    assert authenticated[0]["data"] is None
    assert authenticated[0]["headers"]["cookie"] == SECRET
    assert public and "cookie" not in public[0]["headers"]
    assert profile["source"] == "AUTHENTICATED_MY_TEAM"
    _assert_cookie_not_exposed(profile, capsys)


def test_authenticated_state_get_is_not_a_write(monkeypatch, capsys):
    picks = [{"element": index, "position": index} for index in range(1, 16)]
    calls = _install(
        monkeypatch,
        {
            "https://fantasy.premierleague.com/api/bootstrap-static/": {
                "events": [{
                    "id": 1,
                    "deadline_time": "2099-01-01T00:00:00Z",
                    "is_current": True,
                }],
            },
            "https://fantasy.premierleague.com/api/my-team/7/": {"picks": picks, "transfers": {}},
        },
    )
    state = FPLAccountAdapter("7").get_state(1)
    assert state["ownership_state"] == "VERIFIED_CURRENT"
    assert all(call["method"] == "GET" and call["data"] is None for call in calls)
    my_team = [call for call in calls if call["url"].endswith("/my-team/7/")]
    assert my_team and my_team[0]["headers"]["cookie"] == SECRET
    bootstrap = [call for call in calls if call["url"].endswith("/bootstrap-static/")]
    assert bootstrap and "cookie" not in bootstrap[0]["headers"]
    _assert_cookie_not_exposed(state, capsys)


def test_authenticated_get_failure_does_not_raise_the_cookie(monkeypatch, capsys):
    def urlopen(req, timeout=10):
        raise URLError("upstream failed " + SECRET)

    monkeypatch.setenv("FPL_SESSION_COOKIE", SECRET)
    monkeypatch.setattr(adapter_module.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(
        adapter_module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("keychain must not run")),
    )
    profile = FPLAccountAdapter("7").get_profile()
    assert profile["source"] == "PUBLIC_PROFILE"
    _assert_cookie_not_exposed(profile, capsys)
