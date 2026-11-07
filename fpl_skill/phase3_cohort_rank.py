"""Phase 3 cohort ownership/EO and Monte Carlo rank simulation.

This module is additive. It consumes frozen, public cohort snapshots and
caller-supplied player distributions; it performs no network I/O and does not
mutate the Phase 2 historical firewall.

EO is a cohort estimate, not global FPL EO. The initial implementation models
starting-XI exposure and captain/vice-captain fallback. Bench autosub exposure
is deliberately excluded until the season-versioned autosub engine is released.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import random
from statistics import NormalDist
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


SCHEMA_VERSION = "phase3.cohort-rank.0.1.0"


@dataclass(frozen=True)
class CohortSnapshot:
    cohort_id: str
    event: int
    captured_at: str
    entries: Tuple[Mapping[str, Any], ...]
    coverage: Optional[float] = None
    content_hash: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.cohort_id.strip():
            raise ValueError("cohort_id is required")
        if self.event < 1:
            raise ValueError("event must be >= 1")
        if not self.captured_at.strip():
            raise ValueError("captured_at is required")
        if not self.entries:
            raise ValueError("cohort snapshot must contain entries")
        if self.coverage is not None and not 0.0 <= self.coverage <= 1.0:
            raise ValueError("coverage must be in [0, 1]")
        ids = [int(e["entry_id"]) for e in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate entry_id in frozen cohort")


def _p_start(probabilities: Mapping[int, float], player_id: int) -> float:
    value = float(probabilities.get(player_id, 1.0))
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"start probability for {player_id} must be in [0, 1]")
    return value


def cohort_ownership(
    snapshot: CohortSnapshot,
    start_probabilities: Optional[Mapping[int, float]] = None,
) -> Dict[str, Any]:
    """Return picked/starter/captain/vice ownership and expected cohort EO.

    Input pick rows follow the public FPL picks shape: element, position,
    multiplier, is_captain, is_vice_captain. Only positions 1..11 contribute
    starting-XI exposure. Bench/autosub exposure is not silently imputed.
    """
    probs = start_probabilities or {}
    n = len(snapshot.entries)
    picked: Dict[int, int] = {}
    starters: Dict[int, int] = {}
    captains: Dict[int, int] = {}
    vice_captains: Dict[int, int] = {}
    eo_weight: Dict[int, float] = {}
    captain_fallback: Dict[int, float] = {}

    for entry in snapshot.entries:
        rows = entry.get("picks")
        if not isinstance(rows, list):
            raise ValueError(f"entry {entry.get('entry_id')} has no picks list")
        captain_id = None
        vice_id = None
        seen_positions = set()
        for row in rows:
            if not isinstance(row, Mapping) or "element" not in row:
                raise ValueError("malformed pick row")
            pid = int(row["element"])
            pos = int(row.get("position", 99))
            if pos in seen_positions:
                raise ValueError(f"duplicate pick position {pos}")
            seen_positions.add(pos)
            picked[pid] = picked.get(pid, 0) + 1
            if bool(row.get("is_captain")):
                if captain_id is not None:
                    raise ValueError("multiple captains in entry")
                captain_id = pid
            if bool(row.get("is_vice_captain")):
                if vice_id is not None:
                    raise ValueError("multiple vice-captains in entry")
                vice_id = pid
            if 1 <= pos <= 11:
                starters[pid] = starters.get(pid, 0) + 1
        if captain_id is None:
            raise ValueError(f"entry {entry.get('entry_id')} missing captain")
        if vice_id is None:
            raise ValueError(f"entry {entry.get('entry_id')} missing vice-captain")

        # Expected multiplier exposure: starter baseline + captain extra.
        for pid in {int(r["element"]) for r in rows if 1 <= int(r.get("position", 99)) <= 11}:
            p = _p_start(probs, pid)
            eo_weight[pid] = eo_weight.get(pid, 0.0) + p
        p_cap = _p_start(probs, captain_id)
        p_vice = _p_start(probs, vice_id)
        eo_weight[captain_id] = eo_weight.get(captain_id, 0.0) + p_cap
        fallback = (1.0 - p_cap) * p_vice
        eo_weight[vice_id] = eo_weight.get(vice_id, 0.0) + fallback
        captain_fallback[vice_id] = captain_fallback.get(vice_id, 0.0) + fallback
        captains[captain_id] = captains.get(captain_id, 0) + 1
        vice_captains[vice_id] = vice_captains.get(vice_id, 0) + 1

    player_ids = sorted(set(picked) | set(eo_weight))
    rows_out = {}
    for pid in player_ids:
        rows_out[pid] = {
            "picked_count": picked.get(pid, 0),
            "starter_count": starters.get(pid, 0),
            "captain_count": captains.get(pid, 0),
            "vice_captain_count": vice_captains.get(pid, 0),
            "ownership_pct": 100.0 * picked.get(pid, 0) / n,
            "starter_pct": 100.0 * starters.get(pid, 0) / n,
            "captain_pct": 100.0 * captains.get(pid, 0) / n,
            "vice_captain_pct": 100.0 * vice_captains.get(pid, 0) / n,
            "expected_effective_ownership_pct": 100.0 * eo_weight.get(pid, 0.0) / n,
            "expected_vice_captain_fallback_pct": 100.0 * captain_fallback.get(pid, 0.0) / n,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "cohort_id": snapshot.cohort_id,
        "event": snapshot.event,
        "captured_at": snapshot.captured_at,
        "sample_size": n,
        "coverage": snapshot.coverage,
        "content_hash": snapshot.content_hash,
        "eo_method": "expected starting-XI exposure + captain extra + vice fallback; bench autosubs excluded",
        "players": rows_out,
    }


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("cannot calculate quantile of empty values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * q
    lo = math.floor(index)
    hi = math.ceil(index)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)


def _sample_points(rng: random.Random, distribution: Mapping[str, float]) -> float:
    mean = float(distribution["mean"])
    variance = float(distribution["variance"])
    if not math.isfinite(mean) or not math.isfinite(variance) or variance < 0:
        raise ValueError("player distribution mean/variance must be finite; variance >= 0")
    if mean < 0:
        raise ValueError("player distribution mean must be non-negative")
    if variance == 0:
        return mean
    # A non-negative normal approximation. It preserves the supplied first
    # two moments only approximately after truncation; outputs are a simulation
    # proxy, not an official rank forecast.
    return max(0.0, rng.gauss(mean, math.sqrt(variance)))


def simulate_rank(
    own: Mapping[str, Any],
    cohort: CohortSnapshot,
    distributions: Mapping[int, Mapping[str, float]],
    *,
    simulations: int = 5000,
    seed: int = 0,
) -> Dict[str, Any]:
    """Estimate rank distribution relative to a frozen comparison cohort.

    own: {entry_id, current_points, current_rank, picks:[...]}
    cohort entries: {entry_id, current_points, current_rank, picks:[...]}
    distributions: player_id -> {mean, variance}

    Uses the same simulated player score for every entry in a simulation,
    preserving shared-player outcome correlation. It does not yet model
    autosubs, chips, captain fallback, or rank-field members outside the
    supplied cohort; these are explicit limitations, not hidden assumptions.
    """
    if simulations < 100:
        raise ValueError("simulations must be >= 100")
    own_id = int(own["entry_id"])
    if not own.get("picks"):
        raise ValueError("own entry requires picks")
    if int(own["current_points"]) < 0 or int(own["current_rank"]) < 1:
        raise ValueError("own current_points/current_rank invalid")

    entries = []
    seen = set()
    for e in cohort.entries:
        eid = int(e["entry_id"])
        if eid == own_id:
            continue
        if eid in seen:
            raise ValueError("duplicate cohort entry")
        seen.add(eid)
        if "current_points" not in e or "current_rank" not in e or "picks" not in e:
            raise ValueError(f"cohort entry {eid} missing rank/points/picks")
        entries.append(e)
    if not entries:
        raise ValueError("comparison cohort has no entries besides own entry")

    all_picks = [own["picks"]] + [e["picks"] for e in entries]
    required_ids = set()
    for picks in all_picks:
        for row in picks:
            required_ids.add(int(row["element"]))
    missing = required_ids - set(int(k) for k in distributions)
    if missing:
        raise ValueError(f"missing player distributions: {sorted(missing)}")

    def multipliers(picks: Sequence[Mapping[str, Any]]) -> Dict[int, float]:
        out: Dict[int, float] = {}
        for p in picks:
            pid = int(p["element"])
            mult = float(p.get("multiplier", 1 if int(p.get("position", 99)) <= 11 else 0))
            if mult < 0:
                raise ValueError("negative pick multiplier")
            out[pid] = out.get(pid, 0.0) + mult
        return out

    own_mult = multipliers(own["picks"])
    field_mult = [(e, multipliers(e["picks"])) for e in entries]
    rng = random.Random(seed)
    rank_samples = []
    ahead_counts = []
    own_deltas = []

    for _ in range(simulations):
        sampled = {pid: _sample_points(rng, distributions[pid]) for pid in required_ids}
        own_gain = sum(sampled[pid] * mult for pid, mult in own_mult.items())
        own_future = float(own["current_points"]) + own_gain
        future_scores = []
        ahead = 0
        for entry, mults in field_mult:
            score = float(entry["current_points"]) + sum(sampled[pid] * mult for pid, mult in mults.items())
            future_scores.append(score)
            if score > own_future or (score == own_future and int(entry["current_rank"]) < int(own["current_rank"])):
                ahead += 1
        rank_samples.append(ahead + 1)
        ahead_counts.append(ahead)
        own_deltas.append(own_gain)

    return {
        "schema_version": SCHEMA_VERSION,
        "cohort_id": cohort.cohort_id,
        "event": cohort.event,
        "captured_at": cohort.captured_at,
        "simulations": simulations,
        "seed": seed,
        "comparison_sample_size": len(entries),
        "cohort_coverage": cohort.coverage,
        "observed_rank": int(own["current_rank"]),
        "forecast_rank": {
            "p10": _quantile(rank_samples, 0.10),
            "p50": _quantile(rank_samples, 0.50),
            "p90": _quantile(rank_samples, 0.90),
            "mean": sum(rank_samples) / len(rank_samples),
        },
        "probability_ahead_of_sample": sum(x == 0 for x in ahead_counts) / simulations,
        "own_projected_points": {
            "p10": _quantile(own_deltas, 0.10),
            "p50": _quantile(own_deltas, 0.50),
            "p90": _quantile(own_deltas, 0.90),
            "mean": sum(own_deltas) / len(own_deltas),
        },
        "limitations": [
            "rank is relative only to the supplied frozen cohort; it is not a global-rank estimate",
            "bench autosubs, vice-captain fallback, chips and future transfers are not simulated",
            "player points use a non-negative normal approximation and require calibration",
            "shared player outcomes are correlated across entries; other dependencies are not modelled",
        ],
    }
