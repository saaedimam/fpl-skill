"""Test-only network isolation helpers.

This module is imported by ``tests/conftest.py``. It is NOT production code and
is never installed as part of the ``fpl_skill`` package.

Two layers exist:

1. **Process network namespace (CI / local unshare)** — the real boundary.
   With ``unshare --user --map-root-user --net`` and only loopback up, the
   kernel denies non-loopback egress regardless of Python monkeypatches.
2. **Autouse pytest monkeypatches** — defense in depth for developer laptops
   that are not running inside a namespace. They are incomplete: C extensions,
   subprocesses, ``ctypes``, and already-bound method references can bypass
   them. Prefer the namespace when proving "no outbound write".

The pytest monkeypatch is not a security boundary. It is an incomplete
laptop backstop. The authoritative control is the kernel network
namespace used by CI (``unshare --net``). C extensions, subprocesses,
``ctypes``, and already-bound methods can bypass the monkeypatch.

The monkeypatch stays on unless a developer sets both
``FPL_ALLOW_TEST_NETWORK=1`` and
``FPL_CONFIRM_LIVE_NETWORK=I-understand-this-is-not-a-security-boundary``
outside CI. Either variable alone does nothing. Under ``CI`` or
``GITHUB_ACTIONS`` both are ignored. Neither variable disables the
namespace or production write refusal.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any
from urllib.parse import urlparse

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

FPL_HOST_SUFFIXES = (
    "fantasy.premierleague.com",
    "premierleague.com",
)


class NetworkGuardError(RuntimeError):
    """Raised when a test attempts forbidden network activity."""


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


LIVE_NETWORK_CONFIRMATION = "I-understand-this-is-not-a-security-boundary"


def network_guard_enabled() -> bool:
    """Return True when the pytest monkeypatch guard should be installed.

    The monkeypatch is not a security boundary. Disabling it locally
    requires ``FPL_ALLOW_TEST_NETWORK=1`` and the exact second confirmation
    ``FPL_CONFIRM_LIVE_NETWORK=I-understand-this-is-not-a-security-boundary``.
    Under CI / GitHub Actions the opt-out is ignored.
    """
    import warnings

    allow = os.environ.get("FPL_ALLOW_TEST_NETWORK", "").strip() == "1"
    confirmed = os.environ.get("FPL_CONFIRM_LIVE_NETWORK", "").strip() == LIVE_NETWORK_CONFIRMATION
    if not allow and not confirmed:
        return True
    if _env_truthy("CI") or _env_truthy("GITHUB_ACTIONS"):
        warnings.warn(
            "FPL_ALLOW_TEST_NETWORK ignored because CI/GITHUB_ACTIONS is set; "
            "pytest network guard stays enabled. The monkeypatch is not a security boundary.",
            RuntimeWarning,
            stacklevel=2,
        )
        return True
    if not (allow and confirmed):
        warnings.warn(
            "pytest network guard stays enabled. Set both FPL_ALLOW_TEST_NETWORK=1 "
            "and FPL_CONFIRM_LIVE_NETWORK="
            f"{LIVE_NETWORK_CONFIRMATION}. The monkeypatch is not a security boundary.",
            RuntimeWarning,
            stacklevel=2,
        )
        return True
    warnings.warn(
        "Local pytest monkeypatch disabled after explicit confirmation. "
        "This is not a security boundary. Production writes stay refused "
        "and the CI network namespace is unaffected.",
        RuntimeWarning,
        stacklevel=2,
    )
    return False


def _hostname(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    text = str(value).strip().lower()
    if text.startswith("[") and "]" in text:
        text = text[1 : text.index("]")]
    if "%" in text:
        text = text.split("%", 1)[0]
    return text


def is_loopback_host(host: Any) -> bool:
    name = _hostname(host)
    if not name or name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def is_fpl_host(host: Any) -> bool:
    name = _hostname(host)
    if not name:
        return False
    for suffix in FPL_HOST_SUFFIXES:
        if name == suffix or name.endswith("." + suffix):
            return True
    return False


def _peer_host(address: Any) -> str:
    if isinstance(address, tuple) and address:
        return _hostname(address[0])
    if isinstance(address, str):
        # AF_UNIX path or similar — treat non-absolute IP-ish as non-loopback TCP.
        return _hostname(address)
    return ""


def assert_connect_allowed(address: Any) -> None:
    host = _peer_host(address)
    if is_loopback_host(host):
        return
    raise NetworkGuardError(
        f"test network guard blocked non-loopback connect to {address!r}"
    )


def assert_http_allowed(method: Any, host: Any, url: Any = None) -> None:
    verb = str(method or "GET").upper()
    target_host = _hostname(host)
    if url:
        parsed = urlparse(str(url))
        if parsed.hostname:
            target_host = _hostname(parsed.hostname)
        if not verb or verb == "GET":
            # urlopen(Request) may carry method on the Request object instead.
            pass
    if verb in WRITE_METHODS and is_fpl_host(target_host):
        raise NetworkGuardError(
            f"test network guard blocked {verb} to FPL host {target_host!r}"
        )


def install_network_guard(monkeypatch) -> None:
    """Patch socket / urllib / http.client so tests cannot open FPL writes."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_create_connection = socket.create_connection

    def guarded_connect(self, address):
        assert_connect_allowed(address)
        return real_connect(self, address)

    def guarded_connect_ex(self, address):
        try:
            assert_connect_allowed(address)
        except NetworkGuardError:
            return errno_host_unreachable()
        return real_connect_ex(self, address)

    def guarded_create_connection(address, *args, **kwargs):
        assert_connect_allowed(address)
        return real_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)

    import http.client as http_client
    import urllib.request as urllib_request

    real_request = http_client.HTTPConnection.request
    real_putrequest = http_client.HTTPConnection.putrequest
    real_urlopen = urllib_request.urlopen
    real_opener_open = urllib_request.OpenerDirector.open

    def guarded_putrequest(self, method, url, *args, **kwargs):
        assert_http_allowed(method, getattr(self, "host", None), url)
        return real_putrequest(self, method, url, *args, **kwargs)

    def guarded_request(self, method, url, body=None, headers={}, *args, **kwargs):  # noqa: B006
        host = getattr(self, "host", None)
        header_host = None
        if headers:
            for key, value in headers.items():
                if str(key).lower() == "host":
                    header_host = value
                    break
        assert_http_allowed(method, header_host or host, url)
        return real_request(self, method, url, body=body, headers=headers, *args, **kwargs)

    def _request_method_and_host(req_or_url, data=None):
        method = "GET"
        host = None
        url = req_or_url
        if isinstance(req_or_url, urllib_request.Request):
            method = req_or_url.get_method()
            host = urlparse(req_or_url.full_url).hostname
            url = req_or_url.full_url
            if data is not None and method == "GET":
                method = "POST"
        else:
            parsed = urlparse(str(req_or_url))
            host = parsed.hostname
            if data is not None:
                method = "POST"
        return method, host, url

    def guarded_urlopen(url, data=None, *args, **kwargs):
        method, host, full = _request_method_and_host(url, data)
        assert_http_allowed(method, host, full)
        # Non-loopback destinations are also blocked at socket connect.
        return real_urlopen(url, data=data, *args, **kwargs)

    def guarded_opener_open(self, fullurl, data=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT):
        method, host, full = _request_method_and_host(fullurl, data)
        assert_http_allowed(method, host, full)
        return real_opener_open(self, fullurl, data=data, timeout=timeout)

    monkeypatch.setattr(http_client.HTTPConnection, "putrequest", guarded_putrequest)
    monkeypatch.setattr(http_client.HTTPConnection, "request", guarded_request)
    monkeypatch.setattr(urllib_request, "urlopen", guarded_urlopen)
    monkeypatch.setattr(urllib_request.OpenerDirector, "open", guarded_opener_open)


def errno_host_unreachable() -> int:
    return getattr(__import__("errno"), "ENETUNREACH", 101)
