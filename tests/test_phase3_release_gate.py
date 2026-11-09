"""Fail-closed Phase 3 release evidence gate tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fpl_skill.phase3_release_gate import (
    REQUIRED_PHASE3_GATES, evaluate_phase3_release_gate,
)


def test_empty_evidence_blocks_every_phase3_release_gate():
    result = evaluate_phase3_release_gate({})
    assert result["release_ready"] is False
    assert result["optimizer_integration_allowed"] is False
    assert result["accepted_gate_count"] == 0
    assert len(result["blockers"]) == len(REQUIRED_PHASE3_GATES)


def test_placeholder_urls_do_not_authorize_optimizer_integration():
    evidence = {gate: True for gate in REQUIRED_PHASE3_GATES}
    evidence["evidence_refs"] = {gate: f"https://example.invalid/evidence/{gate}" for gate in REQUIRED_PHASE3_GATES}
    evidence["verified_attestations"] = {
        gate: {"verified": True, "ref": evidence["evidence_refs"][gate], "attested_by": "reviewer"}
        for gate in REQUIRED_PHASE3_GATES
    }
    result = evaluate_phase3_release_gate(evidence)
    assert result["release_ready"] is False
    assert result["optimizer_integration_allowed"] is False
    assert all(item["reason"] == "UNVERIFIED_EVIDENCE_REFERENCE" for item in result["blockers"])


def test_https_reference_without_attestation_stays_blocked():
    evidence = {gate: True for gate in REQUIRED_PHASE3_GATES}
    evidence["evidence_refs"] = {
        gate: f"https://github.com/saaedimam/fpl-skill/blob/main/evidence/{gate}.json"
        for gate in REQUIRED_PHASE3_GATES
    }
    result = evaluate_phase3_release_gate(evidence)
    assert result["release_ready"] is False
    assert all(item["reason"] == "UNVERIFIED_EVIDENCE_ATTESTATION" for item in result["blockers"])


def test_attestation_must_name_the_same_reference():
    evidence = {gate: True for gate in REQUIRED_PHASE3_GATES}
    evidence["evidence_refs"] = {
        gate: f"https://github.com/saaedimam/fpl-skill/blob/main/evidence/{gate}.json"
        for gate in REQUIRED_PHASE3_GATES
    }
    evidence["verified_attestations"] = {
        gate: {
            "verified": True,
            "ref": "https://github.com/saaedimam/fpl-skill/blob/main/evidence/other.json",
            "attested_by": "reviewer",
        }
        for gate in REQUIRED_PHASE3_GATES
    }
    result = evaluate_phase3_release_gate(evidence)
    assert result["optimizer_integration_allowed"] is False


def test_matching_attestation_allows_integration():
    evidence = {gate: True for gate in REQUIRED_PHASE3_GATES}
    evidence["evidence_refs"] = {
        gate: f"https://github.com/saaedimam/fpl-skill/blob/main/evidence/{gate}.json"
        for gate in REQUIRED_PHASE3_GATES
    }
    evidence["verified_attestations"] = {
        gate: {"verified": True, "ref": evidence["evidence_refs"][gate], "attested_by": "reviewer"}
        for gate in REQUIRED_PHASE3_GATES
    }
    result = evaluate_phase3_release_gate(evidence)
    assert result["release_ready"] is True
    assert result["optimizer_integration_allowed"] is True
    assert result["decision"] == "PASS"


def test_true_without_evidence_reference_still_blocks():
    evidence = {gate: True for gate in REQUIRED_PHASE3_GATES}
    evidence["evidence_refs"] = {}
    result = evaluate_phase3_release_gate(evidence)
    assert result["release_ready"] is False
    assert all(x["reason"] == "MISSING_EVIDENCE_REFERENCE" for x in result["blockers"])
