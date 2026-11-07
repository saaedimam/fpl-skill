"""Explicit evidence gate for Phase 3 optimizer integration and certification.

A green CI run is necessary but insufficient. Every gate needs an explicit
true value and a supporting evidence reference; absent evidence fails closed.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence


REQUIRED_PHASE3_GATES = (
    "ci_matrix_passed",
    "release_manifest_verified",
    "phase2_temporal_firewall_passed",
    "livefpl_dynamic_capture_verified",
    "official_eo_differential_passed",
    "rank_walkforward_calibration_passed",
    "price_walkforward_calibration_passed",
    "transfer_flow_chip_filter_validated",
    "autosub_official_differential_passed",
    "live_event_schema_verified",
    "multi_gw_backtest_passed",
    "human_signoff",
)


def evaluate_phase3_release_gate(evidence: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a fail-closed release decision with named blockers."""
    if not isinstance(evidence, Mapping):
        raise TypeError("evidence must be a mapping")
    refs = evidence.get("evidence_refs", {})
    if not isinstance(refs, Mapping):
        refs = {}
    blockers = []
    accepted = []
    for gate in REQUIRED_PHASE3_GATES:
        value = evidence.get(gate)
        ref = refs.get(gate)
        if value is not True:
            blockers.append({"gate": gate, "reason": "NOT_PASSED"})
            continue
        if not isinstance(ref, str) or not ref.startswith("https://"):
            blockers.append({"gate": gate, "reason": "MISSING_EVIDENCE_REFERENCE"})
            continue
        accepted.append(gate)
    ready = not blockers
    return {
        "schema_version": "phase3.release-gate.0.1.0",
        "release_ready": ready,
        "optimizer_integration_allowed": ready,
        "required_gate_count": len(REQUIRED_PHASE3_GATES),
        "accepted_gate_count": len(accepted),
        "accepted_gates": accepted,
        "blockers": blockers,
        "decision": "PASS" if ready else "BLOCKED",
        "policy": "all gates require explicit true plus a non-empty evidence reference",
    }
