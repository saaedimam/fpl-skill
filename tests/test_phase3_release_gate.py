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


def test_all_gates_need_explicit_evidence_references():
    evidence = {gate: True for gate in REQUIRED_PHASE3_GATES}
    evidence["evidence_refs"] = {gate: f"https://example.invalid/evidence/{gate}" for gate in REQUIRED_PHASE3_GATES}
    result = evaluate_phase3_release_gate(evidence)
    assert result["release_ready"] is True
    assert result["optimizer_integration_allowed"] is True


def test_true_without_evidence_reference_still_blocks():
    evidence = {gate: True for gate in REQUIRED_PHASE3_GATES}
    evidence["evidence_refs"] = {}
    result = evaluate_phase3_release_gate(evidence)
    assert result["release_ready"] is False
    assert all(x["reason"] == "MISSING_EVIDENCE_REFERENCE" for x in result["blockers"])
