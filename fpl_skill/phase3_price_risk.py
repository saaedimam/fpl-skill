"""Leakage-aware empirical price-risk calibration for Phase 3.

This module does not infer an FPL transfer threshold. It calibrates a caller's
pre-deadline risk score against matured, timestamped official price outcomes.
Insufficient evidence is returned as uncalibrated rather than promoted to a
rise/fall recommendation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import math
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .observation.ingest import Transport, bootstrap_url, fetch_json


class PriceCalibrationError(ValueError):
    """Invalid, stale, or temporally inconsistent price-risk evidence."""


def _dt(value: str, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PriceCalibrationError(f"{field} must be ISO-8601") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise PriceCalibrationError(f"{field} must be timezone-aware")
    return result


@dataclass(frozen=True)
class PriceRiskLabel:
    player_id: int
    event: int
    direction: str
    risk_score: float
    changed: bool
    observed_at: str
    resolved_at: str
    source_url: str
    content_hash: str

    def __post_init__(self) -> None:
        if self.player_id < 1 or self.event < 1:
            raise PriceCalibrationError("player_id and event must be positive")
        if self.direction not in {"rise", "fall"}:
            raise PriceCalibrationError("direction must be rise or fall")
        if not math.isfinite(float(self.risk_score)) or not 0.0 <= float(self.risk_score) <= 1.0:
            raise PriceCalibrationError("risk_score must be finite and in [0, 1]")
        if not self.source_url.startswith("https://") or not self.content_hash.strip():
            raise PriceCalibrationError("HTTPS source_url and content_hash are required")
        if _dt(self.resolved_at, "resolved_at") < _dt(self.observed_at, "observed_at"):
            raise PriceCalibrationError("resolved_at cannot precede observed_at")


@dataclass(frozen=True)
class CalibratedPriceRisk:
    direction: str
    as_of: str
    bin_count: int
    min_total_samples: int
    min_bin_samples: int
    counts: Tuple[int, ...]
    successes: Tuple[int, ...]
    global_count: int
    global_successes: int
    global_probability: float
    source_urls: Tuple[str, ...]
    source_hashes: Tuple[str, ...]

    def predict(self, risk_score: float, prediction_at: str) -> Dict[str, Any]:
        score = float(risk_score)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise PriceCalibrationError("risk_score must be finite and in [0, 1]")
        when = _dt(prediction_at, "prediction_at")
        cutoff = _dt(self.as_of, "as_of")
        if when <= cutoff:
            raise PriceCalibrationError("prediction_at must be strictly after calibration cutoff")
        index = min(self.bin_count - 1, int(score * self.bin_count))
        count = self.counts[index]
        successes = self.successes[index]
        calibrated = self.global_count >= self.min_total_samples and count >= self.min_bin_samples
        if calibrated:
            # Beta(1,1) smoothing avoids probabilities of exactly 0 or 1.
            probability = (successes + 1.0) / (count + 2.0)
            status = "CALIBRATED"
        else:
            probability = self.global_probability
            status = "INSUFFICIENT_HISTORY"
        return {
            "direction": self.direction,
            "risk_score": score,
            "probability": probability,
            "status": status,
            "action_label": "ESTIMATE_ONLY" if calibrated else "UNAVAILABLE",
            "bin_index": index,
            "bin_sample_size": count,
            "training_sample_size": self.global_count,
            "calibration_as_of": self.as_of,
            "prediction_at": prediction_at,
            "source_urls": list(self.source_urls),
            "source_hashes": list(self.source_hashes),
            "confidence": "medium" if calibrated and count >= 2 * self.min_bin_samples else (
                "low" if calibrated else "none"
            ),
        }


@dataclass(frozen=True)
class PriceSignal:
    player_id: int
    event: int
    direction: str
    risk_score: float
    net_transfer_flow: int
    now_cost: int
    cost_change_start: int
    cost_change_event: int
    captured_at: str
    source_url: str
    content_hash: str


def build_price_risk_scores(
    elements: Sequence[Mapping[str, Any]],
    *,
    event: int,
    captured_at: str,
    source_url: str,
    content_hash: str,
) -> Dict[str, Any]:
    """Convert official bootstrap transfer fields into cross-sectional risk scores.

    Scores are relative ranks, not probabilities or price thresholds. The
    separate calibrator maps these scores to matured rise/fall outcomes.
    Missing official fields fail closed rather than being imputed as zero.
    """
    if event < 1 or not source_url.startswith("https://") or not content_hash.strip():
        raise PriceCalibrationError("event, HTTPS source_url and content_hash are required")
    _dt(captured_at, "captured_at")
    parsed = []
    seen = set()
    for row in elements:
        try:
            pid = int(row["id"])
            now_cost = int(row["now_cost"])
            change_start = int(row["cost_change_start"])
            change_event = int(row["cost_change_event"])
            transfers_in = int(row["transfers_in_event"])
            transfers_out = int(row["transfers_out_event"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PriceCalibrationError("bootstrap player missing a required price/transfer field") from exc
        if pid < 1 or pid in seen or now_cost <= 0 or transfers_in < 0 or transfers_out < 0:
            raise PriceCalibrationError("invalid or duplicate bootstrap player price/transfer values")
        seen.add(pid)
        parsed.append({
            "player_id": pid, "now_cost": now_cost,
            "cost_change_start": change_start, "cost_change_event": change_event,
            "net_transfer_flow": transfers_in - transfers_out,
        })
    if not parsed:
        raise PriceCalibrationError("bootstrap element snapshot is empty")

    def percentiles(values: Sequence[int]) -> Dict[int, float]:
        ordered = sorted(values)
        out = {}
        for value in set(values):
            lower = sum(1 for x in ordered if x < value)
            equal = sum(1 for x in ordered if x == value)
            out[value] = 0.5 if len(ordered) == 1 else (
                lower + (equal - 1) / 2.0
            ) / (len(ordered) - 1)
        return out

    rise_ranks = percentiles([x["net_transfer_flow"] for x in parsed])
    fall_ranks = percentiles([-x["net_transfer_flow"] for x in parsed])
    signals = []
    for row in parsed:
        for direction, score in (
            ("rise", rise_ranks[row["net_transfer_flow"]]),
            ("fall", fall_ranks[-row["net_transfer_flow"]]),
        ):
            signals.append({
                **row,
                "event": event,
                "direction": direction,
                "risk_score": score,
                "captured_at": captured_at,
                "source_url": source_url,
                "content_hash": content_hash,
                "score_semantics": "cross-sectional percentile rank; not probability",
            })
    return {
        "schema_version": "phase3.price-risk-signal.0.1.0",
        "event": event,
        "captured_at": captured_at,
        "source_url": source_url,
        "content_hash": content_hash,
        "player_count": len(parsed),
        "signals": signals,
    }


def fit_price_risk_calibrator(
    labels: Sequence[PriceRiskLabel],
    *,
    direction: str,
    as_of: str,
    bin_count: int = 10,
    min_total_samples: int = 50,
    min_bin_samples: int = 10,
) -> CalibratedPriceRisk:
    if direction not in {"rise", "fall"}:
        raise PriceCalibrationError("direction must be rise or fall")
    if bin_count < 2 or min_total_samples < 1 or min_bin_samples < 1:
        raise PriceCalibrationError("invalid calibration sample/bin configuration")
    cutoff = _dt(as_of, "as_of")
    selected: List[PriceRiskLabel] = []
    seen_labels = set()
    for label in labels:
        if label.direction != direction:
            continue
        observed = _dt(label.observed_at, "observed_at")
        resolved = _dt(label.resolved_at, "resolved_at")
        if observed > cutoff or resolved > cutoff:
            raise PriceCalibrationError("training label contains post-cutoff observation or outcome")
        key = (label.player_id, label.event, label.direction)
        if key in seen_labels:
            raise PriceCalibrationError(f"duplicate training label: {key}")
        seen_labels.add(key)
        selected.append(label)
    counts = [0] * bin_count
    successes = [0] * bin_count
    for label in selected:
        index = min(bin_count - 1, int(float(label.risk_score) * bin_count))
        counts[index] += 1
        successes[index] += int(bool(label.changed))
    total = len(selected)
    positive = sum(successes)
    global_probability = (positive + 1.0) / (total + 2.0)
    return CalibratedPriceRisk(
        direction=direction,
        as_of=as_of,
        bin_count=bin_count,
        min_total_samples=min_total_samples,
        min_bin_samples=min_bin_samples,
        counts=tuple(counts),
        successes=tuple(successes),
        global_count=total,
        global_successes=positive,
        global_probability=global_probability,
        source_urls=tuple(sorted({x.source_url for x in selected})),
        source_hashes=tuple(sorted({x.content_hash for x in selected})),
    )


def brier_score(labels: Sequence[PriceRiskLabel], predictions: Mapping[Tuple[int, int], float]) -> float:
    """Brier score for matured outcomes keyed by (player_id, event)."""
    errors = []
    for label in labels:
        key = (label.player_id, label.event, label.direction)
        if key not in predictions:
            key = (label.player_id, label.event)
        if key not in predictions:
            continue
        probability = float(predictions[key])
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise PriceCalibrationError(f"invalid probability for {key}")
        errors.append((probability - float(label.changed)) ** 2)
    if not errors:
        raise PriceCalibrationError("no matching predictions/outcomes for Brier score")
    return sum(errors) / len(errors)


def calibration_report(
    labels: Sequence[PriceRiskLabel],
    predictions: Mapping[Tuple[int, int], float],
    *,
    bin_count: int = 10,
) -> Dict[str, Any]:
    if bin_count < 2:
        raise PriceCalibrationError("bin_count must be >= 2")
    groups: List[List[Tuple[float, int]]] = [[] for _ in range(bin_count)]
    for label in labels:
        key = (label.player_id, label.event, label.direction)
        if key not in predictions:
            key = (label.player_id, label.event)
        if key not in predictions:
            continue
        p = float(predictions[key])
        if not math.isfinite(p) or not 0.0 <= p <= 1.0:
            raise PriceCalibrationError(f"invalid probability for {key}")
        groups[min(bin_count - 1, int(p * bin_count))].append((p, int(label.changed)))
    total = sum(len(g) for g in groups)
    if not total:
        raise PriceCalibrationError("no matching predictions/outcomes for calibration report")
    bins = []
    for i, group in enumerate(groups):
        if not group:
            continue
        bins.append({
            "bin": i,
            "sample_size": len(group),
            "mean_predicted_probability": sum(p for p, _ in group) / len(group),
            "observed_frequency": sum(y for _, y in group) / len(group),
        })
    return {
        "sample_size": total,
        "brier_score": brier_score(labels, predictions),
        "bins": bins,
    }


def ingest_public_price_signals(
    transport: Transport,
    *,
    event: int,
    captured_at: str,
) -> Dict[str, Any]:
    """Fetch and hash the official public bootstrap before scoring price risk."""
    import hashlib

    url = bootstrap_url()
    payload, response = fetch_json(transport, url)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("elements"), list):
        raise PriceCalibrationError("official bootstrap payload missing elements")
    if not isinstance(payload.get("events"), list) or not any(int(x.get("id", -1)) == event for x in payload["events"] if isinstance(x, Mapping)):
        raise PriceCalibrationError("requested event is absent from official bootstrap")
    if response is None or response.body is None:
        raise PriceCalibrationError("official bootstrap response has no raw body")
    digest = "sha256:" + hashlib.sha256(response.body).hexdigest()
    result = build_price_risk_scores(
        payload["elements"], event=event, captured_at=captured_at,
        source_url=url, content_hash=digest,
    )
    result["source_observed_at"] = response.headers.get("last-modified") or response.headers.get("date")
    return result



def mature_price_labels(
    before_snapshot: Mapping[str, Any],
    after_snapshot: Mapping[str, Any],
) -> Dict[str, Any]:
    """Turn two timestamped official bootstrap snapshots into matured outcomes.

    The risk score is taken only from the earlier snapshot. The later snapshot
    supplies the resolved price outcome. Missing players are excluded and
    reported; no price threshold is inferred.
    """
    before_at = _dt(before_snapshot["captured_at"], "before_snapshot.captured_at")
    after_at = _dt(after_snapshot["captured_at"], "after_snapshot.captured_at")
    if after_at <= before_at:
        raise PriceCalibrationError("after snapshot must be later than before snapshot")
    if int(before_snapshot["event"]) != int(after_snapshot["event"]):
        raise PriceCalibrationError("price snapshots must refer to the same event")
    for snapshot in (before_snapshot, after_snapshot):
        if not str(snapshot.get("source_url", "")).startswith("https://") or not snapshot.get("content_hash"):
            raise PriceCalibrationError("both price snapshots require source provenance")
    def index_snapshot(snapshot: Mapping[str, Any]) -> Dict[int, Mapping[str, Any]]:
        result = {}
        for row in snapshot.get("signals", []):
            if not isinstance(row, Mapping):
                raise PriceCalibrationError("malformed price signal row")
            pid = int(row["player_id"])
            if pid in result:
                continue
            result[pid] = row
        return result
    before = index_snapshot(before_snapshot)
    after = index_snapshot(after_snapshot)
    common = set(before) & set(after)
    labels = []
    for pid in sorted(common):
        earlier = before[pid]
        later = after[pid]
        if "now_cost" not in earlier or "now_cost" not in later:
            raise PriceCalibrationError(f"player {pid} missing now_cost in snapshot")
        old_cost, new_cost = int(earlier["now_cost"]), int(later["now_cost"])
        for direction in ("rise", "fall"):
            score = earlier.get(f"{direction}_risk_score")
            if score is None:
                # The standard signal schema stores one row per direction.
                matches = [
                    x for x in before_snapshot.get("signals", [])
                    if int(x.get("player_id", -1)) == pid and x.get("direction") == direction
                ]
                if len(matches) != 1:
                    raise PriceCalibrationError(f"player {pid} missing unique {direction} score")
                score = matches[0]["risk_score"]
            labels.append(PriceRiskLabel(
                player_id=pid,
                event=int(before_snapshot["event"]),
                direction=direction,
                risk_score=float(score),
                changed=(new_cost > old_cost) if direction == "rise" else (new_cost < old_cost),
                observed_at=before_snapshot["captured_at"],
                resolved_at=after_snapshot["captured_at"],
                source_url=after_snapshot["source_url"],
                content_hash="sha256:" + hashlib.sha256(
                    (str(before_snapshot["content_hash"]) + "|" + str(after_snapshot["content_hash"])).encode()
                ).hexdigest(),
            ))
    return {
        "event": int(before_snapshot["event"]),
        "observed_at": before_snapshot["captured_at"],
        "resolved_at": after_snapshot["captured_at"],
        "before_content_hash": before_snapshot["content_hash"],
        "after_content_hash": after_snapshot["content_hash"],
        "matched_player_count": len(common),
        "before_player_count": len(before),
        "after_player_count": len(after),
        "missing_after_count": len(set(before) - set(after)),
        "missing_before_count": len(set(after) - set(before)),
        "labels": labels,
    }
