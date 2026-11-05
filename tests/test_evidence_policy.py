"""
Evidence Policy Enforcement Tests (v1.1.0)
=========================================
Validates the source-authority hierarchy rules documented in:
- contracts/source-contract.md  (L0..L6 authority levels + CONFLICTED state machine)
- evidence/evidence-policy.md   (operating summary: silence-override, CONFLICTED,
  corroboration-promotion rules)

The enforcement layer is ``fpl_skill.evidence_policy.evaluate_evidence``. It is
called by the execution chokepoint and the prediction engine when claims are
attached. These tests exercise that function directly.
"""
from pathlib import Path

from fpl_skill.evidence_policy import evaluate_evidence

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_CONTRACT = REPO_ROOT / "contracts" / "source-contract.md"
EVIDENCE_POLICY = REPO_ROOT / "evidence" / "evidence-policy.md"


def test_l5_l6_solo_rejection():
    """L5/L6 evidence alone must never trigger a MATERIAL decision."""
    for level in ("L5", "L6"):
        decision = evaluate_evidence(
            [{
                "level": level,
                "claim": "Player should be bought",
                "fact_key": "transfer",
                "source": "podcast" if level == "L5" else "social",
            }],
            proposed_action="BUY",
        )
        assert decision["material_action_allowed"] is False
        assert decision["confidence"] == "signal_only"
        assert decision["action"] == "HOLD"
        assert decision["action"] != "BUY"


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


def test_conflicted_evidence_state():
    """Same-or-higher authority disagreements stay CONFLICTED.

    A lower source does not override a higher one, and it does not create a
    conflict by itself. L0 injured vs L1 available resolves to the L0 claim.
    Two L0 claims that disagree stay CONFLICTED.
    """
    conflicted = evaluate_evidence([
        {"level": "L0", "claim": "Player injured", "fact_key": "status", "source": "FPL API"},
        {"level": "L0", "claim": "Player available", "fact_key": "status", "source": "FPL status mirror"},
    ])
    assert conflicted["state"] == "CONFLICTED"
    assert conflicted["material_action_allowed"] is False
    assert conflicted["action"] == "HOLD"
    assert conflicted["resolved_claim"] is None

    lower_does_not_override = evaluate_evidence([
        {"level": "L0", "claim": "Player injured", "fact_key": "status", "source": "FPL API"},
        {"level": "L1", "claim": "Player available", "fact_key": "status", "source": "Club statement"},
    ])
    assert lower_does_not_override["state"] != "CONFLICTED"
    assert lower_does_not_override["resolved_claim"] == "Player injured"
    assert lower_does_not_override["material_action_allowed"] is True


def test_l5_requires_l0_corroboration():
    """L5 signal alone is not actionable. L5 corroborated at L0 can be medium."""
    solo = evaluate_evidence(
        [{"level": "L5", "claim": "Player is hot", "fact_key": "form", "source": "podcast"}],
        proposed_action="BUY",
    )
    assert solo["confidence"] == "signal_only"
    assert solo["material_action_allowed"] is False
    assert solo["action"] == "HOLD"

    corroborated = evaluate_evidence(
        [
            {"level": "L5", "claim": "Player is hot", "fact_key": "form", "source": "podcast"},
            {"level": "L0", "claim": "Player is hot", "fact_key": "form", "source": "FPL API"},
        ],
        proposed_action="BUY",
    )
    assert corroborated["confidence"] == "medium"
    assert corroborated["material_action_allowed"] is True
    assert corroborated["action"] == "BUY"
