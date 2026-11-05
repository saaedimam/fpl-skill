"""Shared pytest fixtures for fpl-skill.

Installs a test-only network guard that:
- blocks non-loopback TCP connects at the socket layer
- blocks POST/PUT/PATCH/DELETE aimed at FPL hosts via urllib/http.client

This monkeypatch is not a security boundary. CI runs the suite inside a
network namespace with only loopback enabled; that kernel boundary is the
authoritative "no egress" control. See ``tests/README.md``.
"""
from __future__ import annotations

import pytest

from tests.network_isolation import install_network_guard, network_guard_enabled


@pytest.fixture(autouse=True)
def _fpl_test_network_guard(monkeypatch):
    if not network_guard_enabled():
        yield
        return
    install_network_guard(monkeypatch)
    yield
