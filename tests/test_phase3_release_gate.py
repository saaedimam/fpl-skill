"""Fail-closed Phase 3 release evidence gate tests."""
import hashlib
import hmac

from fpl_skill.phase3_release_gate import (
    REQUIRED_PHASE3_GATES,
    _attestation_message,
    evaluate_phase3_release_gate,
)


TRUSTED_KEY = b"test-only-trusted-attestor-key-32-bytes-minimum"
TRUSTED_KEYS = {"release-reviewer": TRUSTED_KEY}


def _complete_evidence():
    evidence = {gate: True for gate in REQUIRED_PHASE3_GATES}
    evidence["evidence_refs"] = {
        gate: f"https://github.com/saaedimam/fpl-skill/blob/main/evidence/{gate}.json"
        for gate in REQUIRED_PHASE3_GATES
    }
    return evidence


def _sign_all(evidence, *, key=TRUSTED_KEY, attestor="release-reviewer"):
    evidence["verified_attestations"] = {
        gate: {
            "ref": evidence["evidence_refs"][gate],
            "attested_by": attestor,
            "signature": hmac.new(
                key,
                _attestation_message(gate, evidence["evidence_refs"][gate], attestor),
                hashlib.sha256,
            ).hexdigest(),
        }
        for gate in REQUIRED_PHASE3_GATES
    }
    return evidence


def test_empty_evidence_blocks_every_phase3_release_gate():
    result = evaluate_phase3_release_gate({})
    assert result["release_ready"] is False
    assert result["optimizer_integration_allowed"] is False
    assert result["accepted_gate_count"] == 0
    assert len(result["blockers"]) == len(REQUIRED_PHASE3_GATES)


def test_placeholder_urls_do_not_authorize_optimizer_integration():
    evidence = _complete_evidence()
    evidence["evidence_refs"] = {
        gate: f"https://example.invalid/evidence/{gate}"
        for gate in REQUIRED_PHASE3_GATES
    }
    _sign_all(evidence)
    result = evaluate_phase3_release_gate(
        evidence, trusted_attestor_keys=TRUSTED_KEYS
    )
    assert result["release_ready"] is False
    assert result["optimizer_integration_allowed"] is False
    assert all(
        item["reason"] == "UNVERIFIED_EVIDENCE_REFERENCE"
        for item in result["blockers"]
    )


def test_https_reference_without_attestation_stays_blocked():
    evidence = _complete_evidence()
    result = evaluate_phase3_release_gate(
        evidence, trusted_attestor_keys=TRUSTED_KEYS
    )
    assert result["release_ready"] is False
    assert all(
        item["reason"] == "UNVERIFIED_EVIDENCE_ATTESTATION"
        for item in result["blockers"]
    )


def test_self_asserted_verified_boolean_is_not_an_attestation():
    evidence = _complete_evidence()
    evidence["verified_attestations"] = {
        gate: {
            "verified": True,
            "ref": evidence["evidence_refs"][gate],
            "attested_by": "release-reviewer",
        }
        for gate in REQUIRED_PHASE3_GATES
    }
    result = evaluate_phase3_release_gate(
        evidence, trusted_attestor_keys=TRUSTED_KEYS
    )
    assert result["release_ready"] is False
    assert result["accepted_gate_count"] == 0


def test_attestation_must_name_the_same_reference():
    evidence = _complete_evidence()
    _sign_all(evidence)
    for gate in REQUIRED_PHASE3_GATES:
        evidence["verified_attestations"][gate]["ref"] = (
            "https://github.com/saaedimam/fpl-skill/blob/main/evidence/other.json"
        )
    result = evaluate_phase3_release_gate(
        evidence, trusted_attestor_keys=TRUSTED_KEYS
    )
    assert result["optimizer_integration_allowed"] is False


def test_untrusted_attestor_is_rejected():
    evidence = _complete_evidence()
    _sign_all(evidence, attestor="unknown-reviewer")
    result = evaluate_phase3_release_gate(
        evidence, trusted_attestor_keys=TRUSTED_KEYS
    )
    assert result["release_ready"] is False
    assert result["accepted_gate_count"] == 0


def test_tampered_signature_is_rejected():
    evidence = _complete_evidence()
    _sign_all(evidence)
    first_gate = REQUIRED_PHASE3_GATES[0]
    evidence["verified_attestations"][first_gate]["signature"] = "00" * 32
    result = evaluate_phase3_release_gate(
        evidence, trusted_attestor_keys=TRUSTED_KEYS
    )
    assert result["release_ready"] is False
    assert result["accepted_gate_count"] == len(REQUIRED_PHASE3_GATES) - 1
    assert result["blockers"][0]["gate"] == first_gate


def test_valid_trusted_signatures_allow_gate_evaluation_to_pass():
    evidence = _sign_all(_complete_evidence())
    result = evaluate_phase3_release_gate(
        evidence, trusted_attestor_keys=TRUSTED_KEYS
    )
    assert result["release_ready"] is True
    assert result["optimizer_integration_allowed"] is True
    assert result["decision"] == "PASS"
    assert result["accepted_gate_count"] == len(REQUIRED_PHASE3_GATES)


def test_true_without_evidence_reference_still_blocks():
    evidence = _complete_evidence()
    evidence["evidence_refs"] = {}
    _sign_all(evidence)
    result = evaluate_phase3_release_gate(
        evidence, trusted_attestor_keys=TRUSTED_KEYS
    )
    assert result["release_ready"] is False
    assert all(
        item["reason"] == "MISSING_EVIDENCE_REFERENCE"
        for item in result["blockers"]
    )


def test_missing_trust_store_fails_closed():
    evidence = _sign_all(_complete_evidence())
    result = evaluate_phase3_release_gate(evidence)
    assert result["release_ready"] is False
    assert result["accepted_gate_count"] == 0
