"""Source-authority evaluator for material FPL decisions.

Implements the rules in ``contracts/source-contract.md`` and
``evidence/evidence-policy.md``. Lower authority never silently overrides
higher authority. L5/L6 evidence alone cannot authorize a material action.
Disagreement at the highest tier is ``CONFLICTED`` and is not collapsed.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional


AUTHORITY_RANK = {f"L{rank}": rank for rank in range(7)}
# L0 is highest authority. "L3 or above" means rank <= 3.
CORROBORATION_RANK_MAX = 3


def evaluate_evidence(
    claims: Iterable[Mapping[str, Any]],
    *,
    proposed_action: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve a set of claims into a decision the execution path can enforce.

    Each claim mapping needs ``level`` (``L0``..``L6``) and ``claim``.
    ``fact_key`` groups statements about the same fact. Claims about different
    keys do not conflict with each other.
    """
    normalized = [_normalize_claim(claim) for claim in claims]
    if not normalized:
        return _decision(
            state="UNKNOWN",
            confidence="low",
            allowed=False,
            reason="no evidence",
            resolved_claim=None,
        )

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for claim in normalized:
        grouped.setdefault(claim["fact_key"], []).append(claim)

    conflicts: List[Dict[str, Any]] = []
    resolved: List[Dict[str, Any]] = []
    for fact_key, group in grouped.items():
        best_rank = min(item["rank"] for item in group)
        top = [item for item in group if item["rank"] == best_rank]
        distinct = {item["claim"] for item in top}
        if len(distinct) > 1:
            conflicts.append({
                "fact_key": fact_key,
                "level": top[0]["level"],
                "claims": sorted(distinct),
            })
            continue
        winner = top[0]
        resolved.append({
            "fact_key": fact_key,
            "level": winner["level"],
            "rank": winner["rank"],
            "claim": winner["claim"],
            "overridden": [
                {"level": item["level"], "claim": item["claim"]}
                for item in group
                if item["rank"] > best_rank and item["claim"] != winner["claim"]
            ],
        })

    if conflicts:
        return _decision(
            state="CONFLICTED",
            confidence="low",
            allowed=False,
            reason="same-or-higher authority claims disagree",
            resolved_claim=None,
            conflicts=conflicts,
            resolved=resolved,
        )

    ranks = [item["rank"] for item in normalized]
    best_rank = min(ranks)
    signal_only = all(rank >= 5 for rank in ranks)
    if signal_only:
        return _decision(
            state="SIGNAL_ONLY",
            confidence="signal_only",
            allowed=False,
            reason="L5/L6 evidence cannot justify a material decision",
            resolved_claim=resolved[0]["claim"] if len(resolved) == 1 else None,
            resolved=resolved,
        )

    corroborated = best_rank <= CORROBORATION_RANK_MAX
    if not corroborated:
        return _decision(
            state="INSUFFICIENT_CORROBORATION",
            confidence="low",
            allowed=False,
            reason="material claims need corroboration at L3 or above",
            resolved_claim=resolved[0]["claim"] if len(resolved) == 1 else None,
            resolved=resolved,
        )

    mixed_with_signal = any(rank >= 5 for rank in ranks)
    if mixed_with_signal or best_rank > 0:
        confidence = "medium"
    else:
        confidence = "high"
    return _decision(
        state="CORROBORATED" if mixed_with_signal else "RESOLVED",
        confidence=confidence,
        allowed=True,
        reason="supported at L3 or above",
        resolved_claim=resolved[0]["claim"] if len(resolved) == 1 else None,
        resolved=resolved,
        proposed_action=proposed_action,
    )


def _normalize_claim(claim: Mapping[str, Any]) -> Dict[str, Any]:
    level = str(claim.get("level") or claim.get("source_level") or "").upper()
    if level not in AUTHORITY_RANK:
        raise ValueError(f"evidence level must be L0..L6, got {level!r}")
    text = claim.get("claim")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("evidence claim text is required")
    fact_key = claim.get("fact_key") or text
    return {
        "level": level,
        "rank": AUTHORITY_RANK[level],
        "claim": text.strip(),
        "fact_key": str(fact_key),
        "source": claim.get("source") or claim.get("source_type") or "",
    }


def _decision(
    *,
    state: str,
    confidence: str,
    allowed: bool,
    reason: str,
    resolved_claim: Optional[str],
    conflicts: Optional[List[Dict[str, Any]]] = None,
    resolved: Optional[List[Dict[str, Any]]] = None,
    proposed_action: Optional[str] = None,
) -> Dict[str, Any]:
    action = proposed_action if allowed and proposed_action else "HOLD"
    return {
        "state": state,
        "confidence": confidence,
        "material_action_allowed": allowed,
        "action": action,
        "reason": reason,
        "resolved_claim": resolved_claim,
        "conflicts": conflicts or [],
        "resolved": resolved or [],
    }
