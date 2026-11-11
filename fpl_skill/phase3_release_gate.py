"""Explicit evidence gate for Phase 3 optimizer integration and certification.

Attestations are authenticated with HMAC-SHA256. Trusted keys must be supplied
by the caller from a trusted configuration/secret store; keys embedded in the
evidence payload are never trusted. A URL scheme or self-asserted boolean is
not verification.
"""
from __future__ import annotations

import hashlib
import hmac
import json
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

ATTESTATION_SCHEMA_VERSION = "phase3.release-attestation.v1"
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


def _attestation_message(gate: str, ref: str, attested_by: str) -> bytes:
    """Return the canonical bytes signed by an evidence attestor."""
    payload = {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "gate": gate,
        "ref": ref,
        "attested_by": attested_by,
    }
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _attested(
    gate: str,
    ref: str,
    attestations: Any,
    trusted_attestor_keys: Any,
) -> bool:
    if not isinstance(attestations, Mapping):
        return False
    if not isinstance(trusted_attestor_keys, Mapping):
        return False

    record = attestations.get(gate)
    if not isinstance(record, Mapping) or record.get("ref") != ref:
        return False

    attestor = record.get("attested_by")
    signature_hex = record.get("signature")
    if not isinstance(attestor, str) or not attestor.strip():
        return False
    if not isinstance(signature_hex, str):
        return False

    key = trusted_attestor_keys.get(attestor)
    if not isinstance(key, bytes) or len(key) < 32:
        return False

    try:
        supplied_signature = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    if len(supplied_signature) != hashlib.sha256().digest_size:
        return False

    expected_signature = hmac.new(
        key, _attestation_message(gate, ref, attestor), hashlib.sha256
    ).digest()
    return hmac.compare_digest(expected_signature, supplied_signature)


def evaluate_phase3_release_gate(
    evidence: Mapping[str, Any],
    *,
    trusted_attestor_keys: Mapping[str, bytes] | None = None,
) -> Dict[str, Any]:
    """Return a fail-closed release decision with authenticated attestations.

    trusted_attestor_keys is a trust root and must come from trusted caller
    configuration (for example, a secret manager), never from evidence.
    Each attestation signs the exact gate, evidence reference, and attestor ID.
    Omitting the trust store leaves all otherwise-passing gates blocked.
    """
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
        if not _attested(gate, ref, attestations, trusted_attestor_keys):
            blockers.append({"gate": gate, "reason": "UNVERIFIED_EVIDENCE_ATTESTATION"})
            continue
        accepted.append(gate)

    ready = not blockers
    return {
        "schema_version": "phase3.release-gate.0.2.0",
        "release_ready": ready,
        "optimizer_integration_allowed": ready,
        "required_gate_count": len(REQUIRED_PHASE3_GATES),
        "accepted_gate_count": len(accepted),
        "accepted_gates": accepted,
        "blockers": blockers,
        "decision": "PASS" if ready else "BLOCKED",
        "policy": (
            "all gates require explicit true, a non-placeholder https evidence "
            "reference, and a valid HMAC-SHA256 attestation signed by a trusted "
            "attestor key over that exact gate and reference"
        ),
    }
