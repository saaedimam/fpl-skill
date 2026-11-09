"""Explicit evidence gate for Phase 3 optimizer integration and certification.

A green CI run is necessary but insufficient. Every gate needs an explicit
true value, a non-placeholder evidence reference, and a separate attestation
that names that exact reference. A URL scheme is not verification.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping
from urllib.parse import urlsplit


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

_RESERVED_HOSTS = frozenset({"example.com", "example.org", "example.net", "localhost"})
_RESERVED_SUFFIXES = (".invalid", ".example", ".test", ".localhost")


def _evidence_host(ref: str):
    if any(character.isspace() for character in ref):
        return None
    parsed = urlsplit(ref)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    return parsed.hostname.lower().rstrip(".")


def _reference_status(ref: Any) -> str:
    if not isinstance(ref, str) or _evidence_host(ref) is None:
        return "MISSING_EVIDENCE_REFERENCE"
    host = _evidence_host(ref)
    if host in _RESERVED_HOSTS or host.endswith(_RESERVED_SUFFIXES):
        return "UNVERIFIED_EVIDENCE_REFERENCE"
    return "OK"


def _attested(gate: str, ref: str, attestations: Any) -> bool:
    if not isinstance(attestations, Mapping):
        return False
    record = attestations.get(gate)
    if not isinstance(record, Mapping) or record.get("verified") is not True:
        return False
    if record.get("ref") != ref:
        return False
    attestor = record.get("attested_by")
    return isinstance(attestor, str) and bool(attestor.strip())


def evaluate_phase3_release_gate(evidence: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a fail-closed release decision with named blockers."""
    if not isinstance(evidence, Mapping):
        raise TypeError("evidence must be a mapping")
    refs = evidence.get("evidence_refs", {})
    if not isinstance(refs, Mapping):
        refs = {}
    attestations = evidence.get("verified_attestations", {})
    blockers = []
    accepted = []
    for gate in REQUIRED_PHASE3_GATES:
        value = evidence.get(gate)
        ref = refs.get(gate)
        if value is not True:
            blockers.append({"gate": gate, "reason": "NOT_PASSED"})
            continue
        status = _reference_status(ref)
        if status != "OK":
            blockers.append({"gate": gate, "reason": status})
            continue
        if not _attested(gate, ref, attestations):
            blockers.append({"gate": gate, "reason": "UNVERIFIED_EVIDENCE_ATTESTATION"})
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
        "policy": (
            "all gates require explicit true, a non-placeholder https evidence "
            "reference, and a verified attestation of that exact reference"
        ),
    }