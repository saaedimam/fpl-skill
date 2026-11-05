"""Dry-run sandbox and hard squad validation for account mutations.

``validate_picks`` is the enforcement check used by the execution chokepoint.
An invalid squad raises no network traffic; the caller refuses the write.
``simulate`` keeps the previous id-swap preview and blocks when a full pick
list is attached and fails validation.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from fpl_skill.account_adapter import FPLAccountAdapter


_ROLE_BY_TYPE = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
_SQUAD_QUOTA = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}


def _formations() -> set:
    from fpl_skill.api import VALID_FORMATIONS

    return set(VALID_FORMATIONS)


def _element_id(pick: Mapping[str, Any]) -> Optional[int]:
    for key in ("element", "player_id", "id"):
        value = pick.get(key)
        if isinstance(value, int):
            return value
    return None


def _role(pick: Mapping[str, Any]) -> Optional[str]:
    for key in ("role", "squad_position", "position"):
        value = pick.get(key)
        if isinstance(value, str):
            label = value.strip().upper()
            if label == "GK":
                return "GKP"
            if label in _SQUAD_QUOTA:
                return label
    element_type = pick.get("element_type")
    if isinstance(element_type, int):
        return _ROLE_BY_TYPE.get(element_type)
    return None


def _lineup_slot(pick: Mapping[str, Any]) -> Optional[int]:
    if isinstance(pick.get("lineup_position"), int):
        return pick["lineup_position"]
    position = pick.get("position")
    if isinstance(position, int):
        return position
    return None


def _cost_tenths(pick: Mapping[str, Any]) -> Optional[int]:
    if isinstance(pick.get("now_cost"), int):
        return pick["now_cost"]
    if isinstance(pick.get("cost_int"), int):
        return pick["cost_int"]
    cost_m = pick.get("cost_m")
    if isinstance(cost_m, (int, float)):
        return int(round(float(cost_m) * 10))
    return None


def _club(pick: Mapping[str, Any]) -> Optional[str]:
    for key in ("team", "club"):
        value = pick.get(key)
        if value is not None and value != "":
            return str(value)
    return None


def validate_squad_players(
    players: Sequence[Mapping[str, Any]],
    *,
    budget: float = 100.0,
) -> List[str]:
    """Check 15-man shape, 2/5/5/3, budget, and max 3 per club."""
    violations: List[str] = []
    if len(players) != 15:
        violations.append(f"squad: size {len(players)} != 15")

    ids = [_element_id(player) for player in players]
    if any(element_id is None for element_id in ids):
        violations.append("squad: missing element id")
    elif len(set(ids)) != len(ids):
        violations.append("squad: duplicate element")

    roles = []
    for player in players:
        role = _role(player)
        if role is None:
            violations.append("role: missing squad position")
        roles.append(role)
    counts = {role: roles.count(role) for role in _SQUAD_QUOTA}
    for role, required in _SQUAD_QUOTA.items():
        if counts[role] != required:
            violations.append(f"positions: {role} {counts[role]} != {required}")

    clubs: Dict[str, int] = {}
    costs = []
    for player in players:
        club = _club(player)
        if club is None:
            violations.append("club: missing club")
        else:
            clubs[club] = clubs.get(club, 0) + 1
        cost = _cost_tenths(player)
        if cost is None:
            violations.append("budget: missing now_cost")
        else:
            costs.append(cost)
    for club, count in sorted(clubs.items()):
        if count > 3:
            violations.append(f"club: {club} has {count} players")

    budget_tenths = int(round(float(budget) * 10))
    if costs and len(costs) == len(players) and sum(costs) > budget_tenths:
        violations.append(
            f"budget: {sum(costs) / 10:.1f}m exceeds {budget_tenths / 10:.1f}m"
        )
    return violations


def validate_lineup(
    players: Sequence[Mapping[str, Any]],
    xi_ids: Iterable[int],
    captain_id: Optional[int],
    vice_id: Optional[int] = None,
    *,
    require_captain: bool = True,
    require_vice: bool = True,
    attacking_captain: bool = False,
) -> List[str]:
    """Check a starting XI, formation, and captain/vice membership."""
    violations: List[str] = []
    by_id = {}
    for player in players:
        element_id = _element_id(player)
        if element_id is not None:
            by_id[element_id] = player
    xi = list(xi_ids)
    if len(xi) != 11 or len(set(xi)) != 11:
        violations.append(f"lineup: starting XI size {len(xi)} != 11")
    missing = [element_id for element_id in xi if element_id not in by_id]
    if missing:
        violations.append("lineup: starting XI contains players outside the squad")

    role_counts = {"GKP": 0, "DEF": 0, "MID": 0, "FWD": 0}
    for element_id in xi:
        player = by_id.get(element_id)
        if player is None:
            continue
        role = _role(player)
        if role in role_counts:
            role_counts[role] += 1
    if role_counts["GKP"] != 1:
        violations.append(f"lineup: GKP {role_counts['GKP']} != 1")
    formation = (role_counts["DEF"], role_counts["MID"], role_counts["FWD"])
    if formation not in _formations():
        violations.append(f"lineup: formation {formation[0]}-{formation[1]}-{formation[2]} is not legal")

    if require_captain:
        violations.extend(
            _check_armband(
                "captain",
                captain_id,
                xi,
                by_id,
                attacking=attacking_captain,
            )
        )
    if require_vice:
        violations.extend(_check_armband("vice", vice_id, xi, by_id, attacking=False))
    if (
        require_captain
        and require_vice
        and captain_id is not None
        and captain_id == vice_id
    ):
        violations.append("captain: captain and vice-captain must be different players")
    return violations


def _check_armband(
    label: str,
    element_id: Optional[int],
    xi: Sequence[int],
    by_id: Mapping[int, Mapping[str, Any]],
    *,
    attacking: bool,
) -> List[str]:
    prefix = "captain" if label == "captain" else "vice"
    if element_id is None:
        return [f"{prefix}: missing"]
    if element_id not in xi:
        return [f"{prefix}: not in the starting XI"]
    if attacking:
        role = _role(by_id.get(element_id, {}))
        if role not in {"MID", "FWD"}:
            return [f"{prefix}: {role or 'unknown'} is not an attacking position"]
    return []


def validate_picks(
    picks: Sequence[Mapping[str, Any]],
    *,
    budget: float = 100.0,
    require_vice: bool = True,
    require_captain: bool = True,
    bootstrap: Optional[Mapping[Any, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Validate a proposed 15-pick write against authoritative bootstrap data.

    FPL's wire ``position`` field is the lineup slot (1-15). Playing position,
    club, and price are taken from ``bootstrap`` and must match any values
    the caller supplied. Aggregate squad rules run on that authoritative
    data. Without bootstrap data the write is rejected.
    """
    if bootstrap is None:
        return {"valid": False, "violations": ["bootstrap: authoritative player data is required"]}
    identity = _bootstrap_identity_violations(picks, bootstrap)
    if identity:
        return {"valid": False, "violations": identity}
    picks = _picks_from_bootstrap(picks, bootstrap)
    violations = validate_squad_players(picks, budget=budget)
    slots = []
    for pick in picks:
        slot = _lineup_slot(pick)
        if slot is None:
            violations.append("lineup: missing lineup position")
        else:
            slots.append(slot)
    if slots and (len(slots) != len(picks) or sorted(slots) != list(range(1, len(picks) + 1))):
        violations.append("lineup: positions must be 1..15 exactly once")

    xi_ids = []
    captains = []
    vices = []
    for pick in picks:
        element_id = _element_id(pick)
        slot = _lineup_slot(pick)
        if element_id is None or slot is None:
            continue
        if slot <= 11:
            xi_ids.append(element_id)
        if pick.get("is_captain") is True:
            captains.append(element_id)
        if pick.get("is_vice_captain") is True:
            vices.append(element_id)

    if require_captain and len(captains) != 1:
        violations.append(f"captain: expected exactly one, found {len(captains)}")
    if require_vice and len(vices) != 1:
        violations.append(f"vice: expected exactly one, found {len(vices)}")
    captain_id = captains[0] if len(captains) == 1 else None
    vice_id = vices[0] if len(vices) == 1 else None
    if len(slots) == len(picks) and slots:
        violations.extend(
            validate_lineup(
                picks,
                xi_ids,
                captain_id,
                vice_id,
                require_captain=require_captain and len(captains) == 1,
                require_vice=require_vice and len(vices) == 1,
            )
        )
    # Preserve order while dropping duplicates from the two passes.
    deduped = list(dict.fromkeys(violations))
    return {"valid": not deduped, "violations": deduped}


def _bootstrap_index(bootstrap: Mapping[Any, Mapping[str, Any]]) -> Dict[int, Mapping[str, Any]]:
    indexed: Dict[int, Mapping[str, Any]] = {}
    for key, record in bootstrap.items():
        element_id = record.get("id", key)
        indexed[int(element_id)] = record
    return indexed


def _bootstrap_identity_violations(
    picks: Sequence[Mapping[str, Any]],
    bootstrap: Mapping[Any, Mapping[str, Any]],
) -> List[str]:
    violations: List[str] = []
    indexed = _bootstrap_index(bootstrap)
    seen = []
    for pick in picks:
        element_id = _element_id(pick)
        if element_id is None:
            violations.append("bootstrap: pick is missing an element id")
            continue
        seen.append(element_id)
        record = indexed.get(element_id)
        if record is None:
            violations.append(f"bootstrap: element {element_id} is not in the authoritative bootstrap")
            continue
        incomplete = False
        for field in ("element_type", "now_cost", "team"):
            if field not in record or record[field] in (None, ""):
                violations.append(f"bootstrap: element {element_id} is missing {field}")
                incomplete = True
        if incomplete:
            continue
        if "element_type" in pick and int(pick["element_type"]) != int(record["element_type"]):
            violations.append(
                f"bootstrap: element {element_id} element_type does not match authoritative data"
            )
        if "now_cost" in pick and int(pick["now_cost"]) != int(record["now_cost"]):
            violations.append(
                f"bootstrap: element {element_id} now_cost does not match authoritative data"
            )
        if ("team" in pick or "club" in pick) and _club(pick) != str(record.get("team")):
            violations.append(
                f"bootstrap: element {element_id} team does not match authoritative data"
            )
    if len(seen) != len(set(seen)):
        violations.append("squad: duplicate element")
    return list(dict.fromkeys(violations))


def _picks_from_bootstrap(
    picks: Sequence[Mapping[str, Any]],
    bootstrap: Mapping[Any, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    indexed = _bootstrap_index(bootstrap)
    normalized = []
    for pick in picks:
        element_id = _element_id(pick)
        record = indexed[int(element_id)]
        normalized.append({
            "element": element_id,
            "element_type": int(record["element_type"]),
            "position": _lineup_slot(pick),
            "team": str(record["team"]),
            "now_cost": int(record["now_cost"]),
            "is_captain": pick.get("is_captain") is True,
            "is_vice_captain": pick.get("is_vice_captain") is True,
        })
    return normalized


class ExecutionSandbox:
    def __init__(self, team_id: str):
        self.team_id = team_id
        self.adapter = FPLAccountAdapter(team_id)

    def calculate_evidence_gap(self, pre_state: dict, post_state: dict, requested_actions: dict) -> list:
        gap = []
        if pre_state.get("squad_ids") != post_state.get("squad_ids"):
            gap.append("SQUAD_CHANGED")
        if requested_actions.get("captain"):
            gap.append("CAPTAIN_CHANGED")
        if requested_actions.get("vice_captain"):
            gap.append("VICE_CAPTAIN_CHANGED")
        if requested_actions.get("transfers"):
            gap.append("FREE_TRANSFER_CHANGED")
        return gap

    def simulate(self, current_state: dict, requested_actions: dict):
        if current_state["ownership_state"] != "VERIFIED_CURRENT":
            return {"status": "BLOCKED", "reason": "Requires VERIFIED_CURRENT ownership"}

        if "picks" in requested_actions:
            checked = validate_picks(
                requested_actions["picks"],
                budget=requested_actions.get("budget", 100.0),
                bootstrap=requested_actions.get("bootstrap"),
            )
            if not checked["valid"]:
                return {
                    "status": "BLOCKED",
                    "reason": "SANDBOX",
                    "violations": checked["violations"],
                }

        post_state = current_state.copy()
        post_squad = current_state["squad_ids"].copy()

        if "sell" in requested_actions and "buy" in requested_actions:
            if requested_actions["sell"] in post_squad:
                post_squad.remove(requested_actions["sell"])
                post_squad.append(requested_actions["buy"])

        post_state["squad_ids"] = post_squad

        return {
            "status": "SIMULATION_COMPLETE",
            "evidence_gap": self.calculate_evidence_gap(current_state, post_state, requested_actions),
        }


if __name__ == "__main__":
    import json

    sandbox = ExecutionSandbox(os.environ.get("FPL_TEAM_ID"))
    state = sandbox.adapter.get_state(sandbox.adapter.get_active_event_id())
    print(json.dumps(sandbox.simulate(state, {"sell": 496, "buy": 2, "captain": True}), indent=2))
