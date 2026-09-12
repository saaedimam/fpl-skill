"""Phase 2 feature normalization for FPL single-gameweek forecasting.

Cumulative bootstrap-static xG/xA/xGC are converted to per-90 rates before
any single-GW forecast. Expected minutes is kept separate from probability of
appearance so the same information is not multiplied twice.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import ceil, isfinite
from typing import Any, Mapping


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class PlayerRates:
    xg90: float
    xa90: float
    xgc90: float
    minutes: int
    expected_minutes: float
    p_start: float
    p_sub: float

    @property
    def gw_xg(self) -> float:
        return self.xg90 * self.expected_minutes / 90.0

    @property
    def gw_xa(self) -> float:
        return self.xa90 * self.expected_minutes / 90.0

    @property
    def gw_xgc(self) -> float:
        return self.xgc90 * self.expected_minutes / 90.0


def _history_rows(player: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("gameweek_history_parsed", "history"):
        value = player.get(key)
        if isinstance(value, list):
            return [row for row in value[-3:] if isinstance(row, Mapping)]
    return []


def estimate_expected_minutes(player: Mapping[str, Any]) -> tuple[float, float, float]:
    cop = player.get("chance_of_playing_next_round")
    chance = 1.0 if cop is None else _clamp(float(cop) / 100.0, 0.0, 1.0)
    recent = _history_rows(player)

    if recent:
        starts = sum(bool(r.get("starts")) or float(r.get("minutes", 0) or 0) >= 60 for r in recent)
        appearances = sum(float(r.get("minutes", 0) or 0) > 0 for r in recent)
        p_start_hist = starts / appearances if appearances else 0.0
        p_sub_hist = (appearances - starts) / appearances if appearances else 0.0
    else:
        minutes = max(0, int(float(player.get("minutes") or 0)))
        starts = max(0, int(float(player.get("starts") or 0)))
        if starts:
            appearances = max(starts, int(ceil(minutes / 90.0)))
            p_start_hist = starts / appearances
            p_sub_hist = (appearances - starts) / appearances
        elif minutes >= 135:
            p_start_hist, p_sub_hist = 0.85, 0.10
        elif minutes >= 90:
            p_start_hist, p_sub_hist = 0.65, 0.15
        elif minutes > 0:
            p_start_hist, p_sub_hist = 0.25, 0.25
        else:
            p_start_hist, p_sub_hist = 0.0, 0.0

    p_start = _clamp(p_start_hist * chance, 0.0, 1.0)
    p_sub = _clamp(p_sub_hist * chance, 0.0, 1.0 - p_start)
    expected_minutes = _clamp(p_start * 82.0 + p_sub * 22.0, 0.0, 90.0)
    if not all(isfinite(v) for v in (p_start, p_sub, expected_minutes)):
        raise ValueError("Non-finite expected-minute estimate")
    return p_start, p_sub, expected_minutes


def normalize_player_rates(player: Mapping[str, Any]) -> PlayerRates:
    minutes = max(0, int(float(player.get("minutes") or 0)))
    denominator = max(minutes, 90)
    xg = max(0.0, float(player.get("expected_goals") or 0.0))
    xa = max(0.0, float(player.get("expected_assists") or 0.0))
    xgc = max(0.0, float(player.get("expected_goals_conceded") or 0.0))
    p_start, p_sub, expected_minutes = estimate_expected_minutes(player)
    return PlayerRates(
        xg90=xg / denominator * 90.0,
        xa90=xa / denominator * 90.0,
        xgc90=xgc / denominator * 90.0,
        minutes=minutes,
        expected_minutes=expected_minutes,
        p_start=p_start,
        p_sub=p_sub,
    )


def gw_expected_contributions(player: Mapping[str, Any], expected_minutes_override: float | None = None) -> tuple[float, float, float]:
    rates = normalize_player_rates(player)
    minutes = rates.expected_minutes if expected_minutes_override is None else _clamp(float(expected_minutes_override), 0.0, 90.0)
    scale = minutes / 90.0
    return rates.xg90 * scale, rates.xa90 * scale, rates.xgc90 * scale
