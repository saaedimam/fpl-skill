"""Single chokepoint for FPL account mutations.

Every mutation is refused before any outbound write. A signed approval is
evidence about a proposed change. It does not authorize transmission, and
there is no mode, transport, or session that turns the refusal off. The
executor cannot mint an approval. Account state is read inside this function.
Caller-supplied state strings are not accepted.
"""
from __future__ import annotations

import contextvars
import os
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Sequence

from fpl_skill.approval_gate import ApprovalGate, ExecutionDenied
from fpl_skill.approval_verify import (
    NonceStore,
    default_nonce_store,
    load_public_key_pem,
    verify_approval_record,
)
from fpl_skill.evidence_policy import evaluate_evidence
from fpl_skill.execution_sandbox import validate_picks
from fpl_skill.historical.exceptions import SnapshotIntegrityError, TemporalLeakageError
from fpl_skill.historical.firewall import admit_snapshots

# Set only for the duration of a transport call that has already passed every gate.
TRANSPORT_ARMED = contextvars.ContextVar("fpl_write_transport_armed", default=False)

__all__ = ["TRANSPORT_ARMED", "execute_account_mutation", "load_bootstrap_elements", "load_fresh_ownership"]


def load_fresh_ownership(team_id: str) -> str:
    """Return ownership from a new account-adapter read. No cached flag."""
    from fpl_skill.account_adapter import FPLAccountAdapter

    adapter = FPLAccountAdapter(str(team_id))
    state = adapter.get_state(adapter.get_active_event_id())
    return str(state.get("ownership_state") or "")


def load_bootstrap_elements() -> dict:
    """Return the current bootstrap element index. No squad-price cache."""
    from fpl_skill.direct_api import DirectFPLClient

    master = DirectFPLClient().fetch_master()
    return {int(player["id"]): player for player in master.get("players", [])}


def execute_account_mutation(
    *,
    team_id: str,
    endpoint: str,
    payload: Mapping[str, Any],
    approval: Any = None,
    public_key_pem: Optional[str] = None,
    picks: Optional[Sequence[Mapping[str, Any]]] = None,
    budget: float = 100.0,
    mode: Optional[str] = None,
    session: Any = None,
    transport: Optional[Callable[..., Any]] = None,
    account_state_reader: Optional[Callable[[], str]] = None,
    bootstrap_reader: Optional[Callable[[], Any]] = None,
    nonce_store: Optional[NonceStore] = None,
    clock: Optional[Callable[[], datetime]] = None,
    evidence_claims: Optional[Sequence[Mapping[str, Any]]] = None,
    proposed_action: Optional[str] = None,
    decision_cutoff_utc: Optional[str] = None,
    historical_snapshots: Optional[Sequence[Any]] = None,
) -> Any:
    """Validate one proposed account write, then refuse to send it.

    ``approval`` is a signed record produced by ``fpl_skill.approval_issuer``.
    A valid record does not permit ``transport`` or ``session`` to be called.
    ``FPL_MODE=autonomous`` does not skip the signature, the fresh account
    read, the sandbox, or the transmission refusal.
    """
    if mode is None:
        mode = os.environ.get("FPL_MODE", "advisory")
    ApprovalGate(mode).check_mode()
    if approval is None:
        raise ExecutionDenied("missing out-of-band approval record")

    now = clock() if clock is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    public_key = load_public_key_pem(public_key_pem)
    nonce = verify_approval_record(
        approval,
        team_id=team_id,
        endpoint=endpoint,
        payload=payload,
        public_key_pem=public_key,
        now=now,
    )

    squad = list(picks) if picks is not None else list(payload.get("picks") or [])
    elements = bootstrap_reader() if bootstrap_reader is not None else load_bootstrap_elements()
    if isinstance(elements, list):
        elements = {int(player["id"]): player for player in elements}
    checked = validate_picks(squad, budget=budget, bootstrap=elements)
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

    ownership_state = (
        account_state_reader() if account_state_reader is not None else load_fresh_ownership(team_id)
    )
    if ownership_state != "VERIFIED_CURRENT":
        raise ExecutionDenied(f"account state is not VERIFIED_CURRENT ({ownership_state})")

    store = nonce_store if nonce_store is not None else default_nonce_store()
    if not store.consume(nonce):
        raise ExecutionDenied("approval nonce was already used")

    # Checked last so a bad approval, squad, or account state still fails
    # closed for its own reason. No approval, mode, or injected transport
    # is allowed to proceed past this line into the network.
    del transport, session
    raise ExecutionDenied(
        "live writes are disabled; a signed approval does not authorize transmission"
    )
