"""Fail-closed approval gate for FPL account mutations.

A write is authorized only when all of the following hold:

* ``FPL_MODE`` is ``approval`` or ``autonomous`` (``advisory`` never writes)
* an explicit per-change approval token matches the payload digest
* account ownership state is ``VERIFIED_CURRENT``

``autonomous`` does not skip the per-change token. Invalid input raises
``ExecutionDenied`` and does not touch the network.
"""
from __future__ import annotations

import hmac
import os
from typing import Optional


class ExecutionDenied(Exception):
    """A write was refused before any request was sent."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class ApprovalGate:
    VALID_MODES = frozenset({"advisory", "approval", "autonomous"})
    WRITE_MODES = frozenset({"approval", "autonomous"})

    def __init__(self, mode: Optional[str] = None):
        if mode is None:
            mode = os.environ.get("FPL_MODE", "advisory")
        self.mode = str(mode).strip().lower()

    def check_confirmation(self, approval_token: Optional[str], expected_token: str) -> None:
        """Raise unless mode permits writes and the per-change token matches.

        This does not look up the account and does not send a request.
        """
        if self.mode not in self.VALID_MODES:
            raise ExecutionDenied(
                f"invalid FPL_MODE: {self.mode}. Must be advisory, approval, or autonomous."
            )
        if self.mode not in self.WRITE_MODES:
            raise ExecutionDenied(f"FPL_MODE={self.mode} does not permit writes")
        if not isinstance(approval_token, str) or not approval_token.strip():
            raise ExecutionDenied("missing per-change approval token")
        if not _tokens_match(approval_token.strip(), expected_token):
            raise ExecutionDenied("approval token does not match this change")

    def authorize(
        self,
        *,
        ownership_state: Optional[str],
        approval_token: Optional[str],
        expected_token: str,
    ) -> None:
        """Raise ``ExecutionDenied`` unless this exact change may be written."""
        self.check_confirmation(approval_token, expected_token)
        if ownership_state != "VERIFIED_CURRENT":
            raise ExecutionDenied(
                f"account state is not VERIFIED_CURRENT ({ownership_state})"
            )

    def verify(
        self,
        *,
        ownership_state: Optional[str] = None,
        approval_token: Optional[str] = None,
        expected_token: Optional[str] = None,
    ) -> bool:
        """Return whether a write would be authorized.

        Network account lookup runs only after the local mode and token checks
        pass. A missing token never contacts the account API.
        """
        token = approval_token if approval_token is not None else os.environ.get("FPL_APPROVAL_TOKEN")
        try:
            self.check_confirmation(token, expected_token or "")
            if ownership_state is None:
                ownership_state = _load_ownership_state()
            self.authorize(
                ownership_state=ownership_state,
                approval_token=token,
                expected_token=expected_token or "",
            )
        except ExecutionDenied as exc:
            print(f"GATE BLOCKED: {exc}")
            return False
        print(f"GATE PASSED: Mode {self.mode}, State {ownership_state}")
        return True


def _tokens_match(provided: str, expected: str) -> bool:
    if not isinstance(expected, str) or not expected:
        return False
    if len(provided) != len(expected):
        return False
    return hmac.compare_digest(provided, expected)


def _load_ownership_state() -> Optional[str]:
    from fpl_skill.account_adapter import FPLAccountAdapter

    team_id = os.environ.get("FPL_TEAM_ID")
    adapter = FPLAccountAdapter(team_id)
    state = adapter.get_state(adapter.get_active_event_id())
    return state.get("ownership_state")


if __name__ == "__main__":
    import sys

    gate = ApprovalGate()
    if not gate.verify():
        sys.exit(1)
