"""Single chokepoint for FPL account mutations.

Nothing is sent unless every gate passes. The default is to refuse rather
than open a connection: callers must pass an explicit transport or session,
and that callable is invoked only after approval, mode, sandbox, evidence,
temporal-firewall, and account-state checks succeed.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
from typing import Any, Callable, Mapping, Optional, Sequence

from fpl_skill.approval_gate import ApprovalGate, ExecutionDenied
from fpl_skill.evidence_policy import evaluate_evidence
from fpl_skill.execution_sandbox import validate_picks
from fpl_skill.historical.exceptions import SnapshotIntegrityError, TemporalLeakageError
from fpl_skill.historical.firewall import admit_snapshots

# Set only for the duration of a transport call that has already passed every gate.
TRANSPORT_ARMED = contextvars.ContextVar("fpl_write_transport_armed", default=False)


def change_digest(team_id: str, endpoint: str, payload: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical team, endpoint, and payload."""
    body = {
        "team_id": str(team_id),
        "endpoint": endpoint,
        "payload": payload,
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def expected_approval_token(team_id: str, endpoint: str, payload: Mapping[str, Any]) -> str:
    """Explicit per-change confirmation bound to ``change_digest``."""
    return "APPROVE:" + change_digest(team_id, endpoint, payload)


def execute_account_mutation(
    *,
    team_id: str,
    endpoint: str,
    payload: Mapping[str, Any],
    approval_token: Optional[str],
    ownership_state: Optional[str] = None,
    picks: Optional[Sequence[Mapping[str, Any]]] = None,
    budget: float = 100.0,
    mode: Optional[str] = None,
    session: Any = None,
    transport: Optional[Callable[..., Any]] = None,
    state_provider: Optional[Callable[[], Optional[str]]] = None,
    evidence_claims: Optional[Sequence[Mapping[str, Any]]] = None,
    proposed_action: Optional[str] = None,
    decision_cutoff_utc: Optional[str] = None,
    historical_snapshots: Optional[Sequence[Any]] = None,
) -> Any:
    """Authorize one account write and only then call ``transport`` or ``session``.

    ``picks`` is the squad view used for sandbox checks. When omitted, the
    ``picks`` list inside ``payload`` is validated. The approval token is
    computed from ``payload``, so a token minted for a different body does
    not authorize this call.
    """
    if mode is None:
        mode = os.environ.get("FPL_MODE", "advisory")
    gate = ApprovalGate(mode)
    expected = expected_approval_token(team_id, endpoint, payload)
    # Mode and token first, so a missing approval cannot fall through to the
    # account lookup. The full authorize() call repeats these checks with the
    # resolved ownership state immediately before the transport runs.
    gate.check_confirmation(approval_token, expected)

    squad = list(picks) if picks is not None else list(payload.get("picks") or [])
    checked = validate_picks(squad, budget=budget)
    if not checked["valid"]:
        detail = "; ".join(checked["violations"])
        raise ExecutionDenied(f"sandbox rejected the squad: {detail}")

    if evidence_claims is not None:
        decision = evaluate_evidence(evidence_claims, proposed_action=proposed_action)
        if not decision["material_action_allowed"]:
            raise ExecutionDenied(
                f"evidence policy blocked the change ({decision['state']}: {decision['reason']})"
            )

    if historical_snapshots is not None or decision_cutoff_utc is not None:
        if not decision_cutoff_utc or historical_snapshots is None:
            raise ExecutionDenied("historical inputs require a decision cutoff and snapshots")
        try:
            admit_snapshots(decision_cutoff_utc, historical_snapshots)
        except (TemporalLeakageError, SnapshotIntegrityError) as exc:
            raise ExecutionDenied(f"temporal firewall refused the change: {exc}") from exc

    resolved_state = ownership_state
    if resolved_state is None and state_provider is not None:
        resolved_state = state_provider()
    gate.authorize(
        ownership_state=resolved_state,
        approval_token=approval_token,
        expected_token=expected,
    )

    if transport is None and session is None:
        raise ExecutionDenied("refusing to open a network connection without an explicit transport")

    armed = TRANSPORT_ARMED.set(True)
    try:
        if transport is not None:
            return transport(endpoint, payload)
        url = "https://fantasy.premierleague.com/api" + endpoint
        body = json.dumps(payload).encode("utf-8")
        return session.post(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
    finally:
        TRANSPORT_ARMED.reset(armed)
