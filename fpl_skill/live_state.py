"""Fail-closed live-state provenance, freshness, chips, and lineup contracts.

This module is pure logic: it performs no I/O and never contacts FPL.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from hashlib import sha256
from typing import Any, Mapping, Optional, Sequence


from fpl_skill.approval_gate import ExecutionDenied  # canonical refusal contract


class FixtureStatus(str, Enum):
    FIXTURE_NOT_PUBLISHED = "FIXTURE_NOT_PUBLISHED"
    BLANK = "BLANK"
    FIXTURE_MISSING = "FIXTURE_MISSING"
    POSTPONED = "POSTPONED"
    UNKNOWN = "UNKNOWN"
    CONFLICTED = "CONFLICTED"


@dataclass(frozen=True)
class RetrievalRecord:
    event_id: int
    team_id: int
    endpoint: str
    retrieved_at: Optional[datetime]
    observed_at: Optional[datetime]
    payload: bytes
    source: str
    upstream: str = "fpl-api"

    @property
    def payload_hash(self) -> str:
        return sha256(self.payload).hexdigest()

    def provenance(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "team_id": self.team_id,
            "endpoint": self.endpoint,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "payload_hash": self.payload_hash,
            "source": self.source,
            "upstream": self.upstream,
        }


@dataclass(frozen=True)
class FixtureSchedule:
    event_id: int
    team_id: int
    fixtures: Sequence[Mapping[str, Any]]
    published: bool
    complete: bool
    retrieval: RetrievalRecord
    postponed: bool = False
    conflicted: bool = False
    source: Optional[str] = None


def classify_fixture_schedule(schedule: FixtureSchedule) -> FixtureStatus:
    """Classify a schedule; zero rows alone can never establish a blank."""
    record = schedule.retrieval
    if schedule.source is not None and schedule.source != "official-fpl":
        return FixtureStatus.UNKNOWN
    if schedule.conflicted:
        return FixtureStatus.CONFLICTED
    if (
        schedule.event_id != record.event_id
        or schedule.team_id != record.team_id
        or not schedule.event_id
        or not schedule.team_id
    ):
        return FixtureStatus.CONFLICTED
    if (
        record.source != "official-fpl"
        or not record.endpoint
        or record.retrieved_at is None
        or record.observed_at is None
        or not record.payload
    ):
        return FixtureStatus.UNKNOWN
    if not schedule.published:
        return FixtureStatus.FIXTURE_NOT_PUBLISHED
    if not schedule.complete:
        return FixtureStatus.FIXTURE_MISSING

    ids = [fixture.get("id") for fixture in schedule.fixtures]
    if any(fixture_id is None for fixture_id in ids):
        return FixtureStatus.FIXTURE_MISSING
    if len(ids) != len(set(ids)):
        return FixtureStatus.CONFLICTED
    if schedule.postponed or any(f.get("postponed") is True for f in schedule.fixtures):
        return FixtureStatus.POSTPONED
    if len(schedule.fixtures) == 0:
        return FixtureStatus.BLANK
    return FixtureStatus.UNKNOWN


def retrieval_state(
    record: RetrievalRecord,
    *,
    now: datetime,
    live_gameweek: bool,
) -> str:
    """Return VERIFIED_CURRENT only inside the retrieval-age TTL."""
    if record.retrieved_at is None:
        raise ValueError("retrieved_at is required; it must never be inferred from now")
    ttl_seconds = 5 * 60 if live_gameweek else 60 * 60
    age_seconds = (now - record.retrieved_at).total_seconds()
    if age_seconds < 0 or age_seconds > ttl_seconds:
        return "STALE"
    return "VERIFIED_CURRENT"


def retrieval_context(record: RetrievalRecord, *, now: datetime, live_gameweek: bool) -> str:
    """Stale records can be retained as historical context, never current state."""
    return (
        "VERIFIED_CURRENT"
        if retrieval_state(record, now=now, live_gameweek=live_gameweek) == "VERIFIED_CURRENT"
        else "HISTORICAL_CONTEXT"
    )


def providers_are_independent(
    source_a: str,
    source_b: str,
    upstream_a: Optional[str] = None,
    upstream_b: Optional[str] = None,
) -> bool:
    """Prove independence only when distinct sources and upstreams are known.

    With just one upstream lineage supplied, independence is not established.
    """
    if not source_a or not source_b or source_a == source_b:
        return False
    if upstream_a is None and upstream_b is None:
        return True
    if upstream_a is None or upstream_b is None:
        return False
    return upstream_a != upstream_b


def resolve_provider_claims(claims: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Official FPL controls FPL state; lower-authority claims cannot override it."""
    canonical = [claim for claim in claims if claim.get("source") == "official-fpl"]
    if not canonical:
        return {"status": "UNAVAILABLE", "claim": None}
    values = {repr(claim.get("value")) for claim in canonical}
    if len(values) != 1:
        return {"status": "CONFLICTED", "claim": None}
    return {"status": "VERIFIED_CURRENT", "claim": dict(canonical[0])}


@dataclass(frozen=True)
class ChipState:
    available_h1: set[str]
    available_h2: set[str]
    used_h1: set[str]
    used_h2: set[str] = field(default_factory=set)
    h2_activated_gw: int = 20

    def inventory_at(self, gw: int) -> frozenset[str]:
        if not 1 <= gw <= 38:
            raise ValueError("Gameweek must be between 1 and 38")
        if gw < self.h2_activated_gw:
            return frozenset(self.available_h1 - self.used_h1)
        return frozenset(self.available_h2 - self.used_h2)


@dataclass(frozen=True)
class FreeHitRestoration:
    squad: tuple[int, ...]
    bank: int
    free_transfers: int


def reconcile_free_hit(
    *,
    pre_squad: Sequence[int],
    temporary_squad: Sequence[int],
    pre_bank: int,
    pre_sell_values: Mapping[int, int],
    post_sell_values: Mapping[int, int],
    saved_free_transfers: int,
) -> FreeHitRestoration:
    """Restore the original squad and bank, adjusted for official sale-value changes."""
    del temporary_squad  # Free Hit acquisitions are temporary and are never restored.
    price_delta = sum(
        int(post_sell_values.get(pid, pre_sell_values[pid])) - int(pre_sell_values[pid])
        for pid in pre_squad
        if pid in pre_sell_values
    )
    return FreeHitRestoration(
        squad=tuple(pre_squad),
        bank=int(pre_bank) + price_delta,
        free_transfers=int(saved_free_transfers),
    )


def reconcile_wildcard(pre_squad: Sequence[int], wildcard_squad: Sequence[int]) -> tuple[int, ...]:
    """Wildcard changes are permanent; unlike Free Hit, the prior squad is not restored."""
    del pre_squad
    return tuple(wildcard_squad)


def validate_chip_use(
    chip: str,
    *,
    gw: int,
    chips_already_used: int = 0,
    previous_chip: Optional[str] = None,
    previous_gw: Optional[int] = None,
    inventory: Optional[ChipState] = None,
) -> None:
    normalized = chip.lower()
    if normalized not in {"wildcard", "free_hit", "triple_captain", "bench_boost"}:
        raise ValueError("unknown chip")
    if chips_already_used >= 1:
        raise ValueError("one chip per Gameweek")
    if inventory is not None and normalized not in inventory.inventory_at(gw):
        raise ValueError("chip is not available in this half-season inventory")
    if (
        normalized == "free_hit"
        and previous_chip
        and previous_chip.lower() == "free_hit"
        and previous_gw is not None
        and gw == previous_gw + 1
    ):
        raise ValueError("Free Hit cannot be used in consecutive Gameweeks")


def _player_id(player: Mapping[str, Any]) -> int:
    value = player.get("id", player.get("element_id", player.get("player_id")))
    if value is None:
        raise ValueError("player is missing a canonical FPL element ID")
    return int(value)


def _position(player: Mapping[str, Any]) -> str:
    pos = player.get("position", player.get("pos"))
    if pos is None:
        pos = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}.get(player.get("element_type"))
    return {"GK": "GKP"}.get(str(pos), str(pos))


def validate_lineup(
    squad: Sequence[Mapping[str, Any]],
    xi: Sequence[int],
    bench: Sequence[int],
) -> bool:
    """Validate XI formation and exact disjoint XI/bench partition of 15 assets."""
    try:
        squad_ids = [_player_id(player) for player in squad]
        xi_ids = [int(player_id) for player_id in xi]
        bench_ids = [int(player_id) for player_id in bench]
        if len(squad_ids) != 15 or len(set(squad_ids)) != 15:
            return False
        if len(xi_ids) != 11 or len(bench_ids) != 4:
            return False
        if len(set(xi_ids)) != 11 or len(set(bench_ids)) != 4:
            return False
        if set(xi_ids).intersection(bench_ids):
            return False
        if set(xi_ids).union(bench_ids) != set(squad_ids):
            return False

        by_id = {_player_id(player): player for player in squad}
        starting = [by_id[player_id] for player_id in xi_ids]
        positions = [_position(player) for player in starting]
        if positions.count("GKP") != 1:
            return False
        if not 3 <= positions.count("DEF") <= 5:
            return False
        if not 2 <= positions.count("MID") <= 5:
            return False
        if not 1 <= positions.count("FWD") <= 3:
            return False
        # Zero chance is explicitly unavailable; do not default it to 100%.
        if any(player.get("chance_of_playing_next_round") == 0 for player in starting):
            return False
        return True
    except (KeyError, TypeError, ValueError):
        return False
