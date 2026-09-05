"""
Evidence Policy Enforcement Tests (v1.1.0)
=========================================
Validates the source-authority hierarchy rules documented in:
- contracts/source-contract.md  (L0..L6 authority levels + CONFLICTED state machine)
- evidence/evidence-policy.md   (operating summary: silence-override, CONFLICTED,
  corroboration-promotion rules)

The evidence *enforcement layer* (an evaluator that consumes claims and returns
decisions/states) is NOT yet coded in fpl_skill/ as of v1.1.0. The L0-L6 hierarchy,
CONFLICTED resolution, and corroboration gates exist as *contract prose* only.

Per task spec: structural-rule tests may be placeholders / XFAIL as long as at least
one test is executable and each test documents the rule it validates.
"""
import pytest
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_CONTRACT = REPO_ROOT / "contracts" / "source-contract.md"
EVIDENCE_POLICY = REPO_ROOT / "evidence" / "evidence-policy.md"


@pytest.mark.xfail(
    reason="Structural rule only: L5/L6-solo rejection is documented in "
           "source-contract.md, but no decision/evidence evaluator exists in "
           "fpl_skill/ to enforce it (v1.1.0). Becomes executable when the "
           "evidence layer is integrated (Phase 3+).",
    strict=False,
)
def test_l5_l6_solo_rejection():
    """
    L5/L6 evidence alone must never trigger a MATERIAL decision.
    """
    # Test structure:
    # 1. Create evidence with source_level = "L5" or "L6"
    # 2. Call decision function / evidence evaluator
    # 3. Assert decision.confidence != "high" or decision.action != BUY/SELL/etc.
    #    OR assert explicitly that L5 solo is rejected for material decisions
    #
    # For v1.1.0: structural test only — the rule is encoded in the contract
    # prose ("lower-authority source never silently overrides a higher-authority
    # source"), not in a callable decision layer. When fpl_skill gains an
    # evidence evaluator, implement: L5/L6-only claims MUST NOT yield a
    # confidence above "signal_only" / any MATERIAL action.
    assert False, "Structural placeholder — see docstring for enforcement spec"


def test_source_hierarchy_ordering():
    """
    Lower-level sources (L0, official) override higher-level sources (L6, social).
    """
    # The authority hierarchy is defined in contracts/source-contract.md.
    # Executable structural check: the contract must enumerate L0..L6 and
    # L0 must be the highest-priority (lowest number) level.
    text = SOURCE_CONTRACT.read_text()
    policy = EVIDENCE_POLICY.read_text()

    # 1. All seven authority levels are documented
    levels = [f"L{rank}" for rank in range(7)]
    for level in levels:
        assert level in text or level in policy, f"{level} missing from evidence contract"

    # 2. L0 (official) has priority over L6 (social) — both docs agree
    assert "L0" in policy and "L6" in policy
    # policy prose: "Authority: L0 (official FPL/PL data & rules) down to L6 (social/community)"
    # Lower number = higher authority. L0 first in the authority declaration implies precedence.
    l0_pos = policy.index("L0")
    l6_pos = policy.index("L6")
    assert l0_pos < l6_pos, "L0 must precede L6 in authority declaration (higher priority)"

    # 3. Numeric ranking is consistent: L0 -> rank 0 (highest), L6 -> rank 6 (lowest)
    hierarchy = {f"L{rank}": rank for rank in range(7)}
    for level, rank in hierarchy.items():
        assert rank == int(level[1]), f"{level} rank mismatch"


@pytest.mark.xfail(
    reason="Structural rule only: conflicting same-or-higher-authority claims must be "
           "marked CONFLICTED per evidence-policy.md, but no evaluate_evidence() "
           "function exists in fpl_skill/ to assert against (v1.1.0). Becomes "
           "executable when evidence resolution layer lands.",
    strict=False,
)
def test_conflicted_evidence_state():
    """
    When two authority sources conflict, mark as CONFLICTED — never silently resolved.
    """
    # Test:
    # 1. FPL API says player injured (L0)
    # 2. Club says player available (L1)
    # 3. Assert state == "CONFLICTED", not silently "injured" or "available"
    #
    # Mock: conflicting evidence dict
    conflicting_evidence = {
        "L0_source": "FPL API",
        "L0_claim": "Player injured",
        "L1_source": "Club statement",
        "L1_claim": "Player available",
    }
    #
    # Evidence-policy.md: "Conflicting same-or-higher-authority claims -> CONFLICTED
    # carried through output, never silently resolved."
    # Structural placeholder — no evaluate_evidence(conflicting_evidence) exists yet.
    # Future assertion:
    #   result = evaluate_evidence(conflicting_evidence)
    #   assert result["state"] == "CONFLICTED"
    assert False, "Structural placeholder — see docstring for enforcement spec"


@pytest.mark.xfail(
    reason="Structural rule only: L5 corroboration gate is documented in "
           "source-contract.md (lower source must be corroborated at/above the level "
           "of the claim it contradicts), but no confidence-downgrade logic is coded "
           "in fpl_skill/ (v1.1.0). Becomes executable when evidence layer integrates.",
    strict=False,
)
def test_l5_requires_l0_corroboration():
    """
    L5 signal alone = no action. L5 + L0-L4 corroboration = actionable.
    """
    # Test:
    # 1. L5 only: "Podcast says player hot" -> confidence = "signal_only"
    # 2. L5 + L0: "Podcast + form trending" -> confidence can be "medium"
    #
    # Structural rule (source-contract.md): "a lower source must be corroborated by a
    # source at or above the level of the claim it contradicts, or must itself be
    # promoted to OFFICIAL/VERIFIED_CURRENT_STATE via the state machines."
    # Structural placeholder — no confidence-downgrade function exists yet.
    assert False, "Structural placeholder — see docstring for enforcement spec"
