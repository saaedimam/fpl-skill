"""
fpl_skill/player_model.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Canonical internal player representation.

The FPL API returns bootstrap elements with:
  - 'id'           (int) as the player identifier
  - 'element_type' (int 1-4) as the position code

Downstream modules (optimizer, backtest, certification, select_best_legal_xi)
expect:
  - 'player_id'    (int)
  - 'position'     (str: "GKP"/"DEF"/"MID"/"FWD")

This module is the single adapter boundary.  All FPL API data should pass
through from_bootstrap_element() or from_bootstrap_list() before being
consumed by any production or test code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ELEMENT_TYPE_MAP: Dict[int, str] = {
    1: "GKP",
    2: "DEF",
    3: "MID",
    4: "FWD",
}

VALID_POSITIONS = frozenset(ELEMENT_TYPE_MAP.values())


# ---------------------------------------------------------------------------
# Canonical player dataclass
# ---------------------------------------------------------------------------

@dataclass
class FPLPlayer:
    """
    Canonical internal player representation.

    All downstream modules (optimizer, backtest, certification, XI selector)
    consume this type instead of raw bootstrap dicts.
    """

    # Canonical identifiers (always present)
    player_id: int          # normalised from bootstrap 'id'
    web_name: str
    team: str               # team short-name or code
    position: str           # "GKP" | "DEF" | "MID" | "FWD"
    now_cost: int           # integer tenths (e.g. 65 = 6.5m)

    # Expected points fields (populated after EP calculation)
    ep_next: float = 0.0
    ep_this: float = 0.0

    # Raw bootstrap field preserved for transparency
    element_type: int = 0

    # Additional bootstrap fields (optional)
    chance_of_playing_next_round: Optional[int] = None
    total_points: int = 0
    form: float = 0.0
    selected_by_percent: float = 0.0
    transfers_in_event: int = 0
    transfers_out_event: int = 0

    # Arbitrary extra bootstrap keys stored without blocking normalisation
    _extra: Dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict suitable for consumption by optimizer / certification."""
        d = {
            "player_id": self.player_id,
            "web_name": self.web_name,
            "team": self.team,
            "position": self.position,
            "now_cost": self.now_cost,
            "cost_int": self.now_cost,
            "ep_next": self.ep_next,
            "ep_this": self.ep_this,
            "element_type": self.element_type,
            "chance_of_playing_next_round": self.chance_of_playing_next_round,
            "total_points": self.total_points,
        }
        d.update(self._extra)
        return d


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def from_bootstrap_element(el: Dict[str, Any]) -> "FPLPlayer":
    """
    Construct an FPLPlayer from a raw FPL API bootstrap element dict.

    Raises:
        ValueError: if element_type is not in 1-4, or 'id' is missing.
    """
    raw_id = el.get("id")
    if raw_id is None:
        raise ValueError(f"Bootstrap element missing 'id' field: {el!r}")

    element_type = int(el.get("element_type", 0))
    position = ELEMENT_TYPE_MAP.get(element_type)
    if position is None:
        raise ValueError(
            f"Unknown element_type={element_type} for player id={raw_id}. "
            f"Expected one of {sorted(ELEMENT_TYPE_MAP.keys())}."
        )

    team = (
        el.get("team_short_name")
        or el.get("team_name")
        or str(el.get("team", "UNK"))
    )

    def _float(key: str, default: float = 0.0) -> float:
        try:
            return float(el.get(key) or default)
        except (TypeError, ValueError):
            return default

    def _int(key: str, default: int = 0) -> int:
        try:
            return int(el.get(key) or default)
        except (TypeError, ValueError):
            return default

    known_keys = {
        "id", "element_type", "web_name", "team", "team_short_name", "team_name",
        "now_cost", "ep_next", "ep_this", "chance_of_playing_next_round",
        "total_points", "form", "selected_by_percent",
        "transfers_in_event", "transfers_out_event",
    }
    extra = {k: v for k, v in el.items() if k not in known_keys}

    return FPLPlayer(
        player_id=int(raw_id),
        web_name=str(el.get("web_name", f"Player_{raw_id}")),
        team=team,
        position=position,
        now_cost=_int("now_cost", 50),
        ep_next=_float("ep_next"),
        ep_this=_float("ep_this"),
        element_type=element_type,
        chance_of_playing_next_round=el.get("chance_of_playing_next_round"),
        total_points=_int("total_points"),
        form=_float("form"),
        selected_by_percent=_float("selected_by_percent"),
        transfers_in_event=_int("transfers_in_event"),
        transfers_out_event=_int("transfers_out_event"),
        _extra=extra,
    )


def from_bootstrap_list(elements: List[Dict[str, Any]]) -> List["FPLPlayer"]:
    """
    Convert a list of bootstrap elements to FPLPlayer instances.
    Elements with unknown element_type are skipped with a warning.
    """
    import sys
    players: List[FPLPlayer] = []
    for el in elements:
        try:
            players.append(from_bootstrap_element(el))
        except ValueError as exc:
            print(f"[player_model] SKIP element id={el.get('id')}: {exc}", file=sys.stderr)
    return players
