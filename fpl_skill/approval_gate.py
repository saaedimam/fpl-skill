"""Fail-closed mode gate for FPL account mutations.

``FPL_MODE=autonomous`` does not bypass the out-of-band signed approval.
That approval is checked at the write boundary with a public key this
process does not use for signing.
"""
from __future__ import annotations

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

    def check_mode(self) -> None:
        """Raise unless this mode is allowed to attempt a write.

        Passing the mode check does not approve a change. ``autonomous``
        still needs a signed approval and a fresh verified account state.
        """
        if self.mode not in self.VALID_MODES:
            raise ExecutionDenied(
                f"invalid FPL_MODE: {self.mode}. Must be advisory, approval, or autonomous."
            )
        if self.mode not in self.WRITE_MODES:
            raise ExecutionDenied(f"FPL_MODE={self.mode} does not permit writes")


if __name__ == "__main__":
    import sys

    try:
        ApprovalGate().check_mode()
    except ExecutionDenied as exc:
        print(f"GATE BLOCKED: {exc}")
        sys.exit(1)
    print("GATE BLOCKED: a signed out-of-band approval and a fresh account check are still required.")
    sys.exit(1)
