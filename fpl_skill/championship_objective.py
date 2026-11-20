"""Deterministic championship objective, FPL bonus, and horizon contracts."""
from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Mapping, Optional, Sequence


@dataclass(frozen=True)
class HorizonEvaluation:
    status: str
    horizon: tuple[int, ...]
    total_ep: Optional[float]
    missing: tuple[int, ...]


def bps_bonus_points(scores: Sequence[int]) -> list[int]:
    """Competition-rank bonus allocation, including ties: first tie -> [3, 3, 1]."""
    points: list[int] = []
    for score in scores:
        place = 1 + sum(1 for other in scores if other > score)
        points.append(3 if place == 1 else 2 if place == 2 else 1 if place == 3 else 0)
    return points


def _confidence_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return {"high": 1.0, "medium": 0.5, "low": 0.0}.get(str(value).lower(), -1.0)


def rank_candidates(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Lexicographic ordering on raw values; FPL element ID is the final key."""
    def key(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
        action = str(candidate.get("action", "")).upper()
        prefer_keep = 0 if action in {"KEEP", "NO_ACTION"} else 1
        return (
            -float(candidate["value"]),              # unrounded decision value
            -float(candidate["downside"]),           # higher downside protection
            -float(candidate["coverage"]),            # stronger evidence coverage
            -_confidence_value(candidate.get("confidence", "low")),
            float(candidate["cost"]),                 # lower cost
            prefer_keep,                              # no action when truly tied
            int(candidate["element_id"]),             # canonical final tie-break
        )
    return [dict(candidate) for candidate in sorted(candidates, key=key)]


def classic_league_transfer_count(history: Iterable[Mapping[str, Any]]) -> int:
    """Count transfers excluding the Wildcard and Free Hit transfer bursts."""
    return sum(
        int(item.get("transfers", 0) or 0)
        for item in history
        if str(item.get("chip") or "").lower() not in {"wildcard", "free_hit"}
    )


def evaluate_horizon(
    expected_points: Mapping[int, Any],
    horizon: Optional[Sequence[int]],
    *,
    incomplete: Iterable[int] = (),
) -> HorizonEvaluation:
    """Aggregate only a caller-specified complete horizon; never impute missing EP."""
    if horizon is None:
        raise ValueError("requested horizon must be explicit")
    required = tuple(int(gameweek) for gameweek in horizon)
    if not required or len(set(required)) != len(required):
        raise ValueError("requested horizon must contain unique Gameweeks")
    incomplete_set = set(int(gameweek) for gameweek in incomplete)
    missing = []
    values = []
    for gameweek in required:
        item = expected_points.get(gameweek)
        if gameweek in incomplete_set or item is None or (
            isinstance(item, Mapping)
            and (item.get("status") not in {"READY", "VERIFIED_CURRENT", "BLANK"}
                 or item.get("expected_points") is None)
        ):
            missing.append(gameweek)
            continue
        value = item.get("expected_points") if isinstance(item, Mapping) else item
        try:
            numeric_value = float(value)
        except (TypeError, ValueError, OverflowError):
            missing.append(gameweek)
            continue
        if not isfinite(numeric_value):
            missing.append(gameweek)
            continue
        values.append(numeric_value)
    if missing:
        return HorizonEvaluation("INSUFFICIENT_DATA", required, None, tuple(sorted(set(missing))))
    return HorizonEvaluation("READY", required, sum(values), ())


def compare_horizons(left: HorizonEvaluation, right: HorizonEvaluation) -> HorizonEvaluation:
    if left.status != "READY" or right.status != "READY" or left.horizon != right.horizon:
        missing = tuple(sorted(set(left.missing + right.missing)))
        return HorizonEvaluation("INSUFFICIENT_DATA", left.horizon, None, missing)
    assert left.total_ep is not None and right.total_ep is not None
    return HorizonEvaluation("READY", left.horizon, left.total_ep - right.total_ep, ())


def evaluate_transfer_horizon(
    expected_points: Mapping[int, Any],
    horizon: Sequence[int],
    *,
    incomplete: Iterable[int] = (),
) -> HorizonEvaluation:
    """Transfer decision entrypoint; required horizon must be explicitly supplied."""
    return evaluate_horizon(expected_points, horizon, incomplete=incomplete)
