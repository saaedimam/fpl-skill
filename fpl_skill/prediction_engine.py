import json, os
from typing import Optional, List, Dict, Any, Sequence
from fpl_skill.account_adapter import FPLAccountAdapter
from fpl_skill.api import calculate_player_gw_ep, build_fixture_map, select_best_legal_xi
from fpl_skill.current_data import (
    CurrentDataError, assert_future_gameweeks, assert_gameweeks_have_fixtures,
    assert_projections_valid, blank_teams,
)
from fpl_skill.evidence_policy import evaluate_evidence
from fpl_skill.historical.exceptions import SnapshotIntegrityError, TemporalLeakageError
from fpl_skill.historical.firewall import admit_snapshots

class PredictionEngine:
    def __init__(self, team_id: str):
        self.adapter = FPLAccountAdapter(team_id)
        self.bootstrap = self.adapter.get_bootstrap()
        self.fixtures = self.adapter.get_fixtures()
        self.events = self.bootstrap.get("events")
        # Current-data gate: live /api/fixtures/ schema, keyed by team id, name and short_name.
        self.fixture_map = build_fixture_map(self.fixtures, teams=self.bootstrap.get("teams"))
        self.elements = {p['id']: p for p in self.bootstrap['elements']}

    def run(
        self,
        target_gw: int,
        squad: Optional[List[Dict[str, Any]]] = None,
        *,
        evidence_claims: Optional[Sequence[Dict[str, Any]]] = None,
        proposed_action: Optional[str] = None,
        decision_cutoff_utc: Optional[str] = None,
        historical_snapshots: Optional[Sequence[Any]] = None,
    ):
        guard = _guard_prediction_inputs(
            evidence_claims=evidence_claims,
            proposed_action=proposed_action,
            decision_cutoff_utc=decision_cutoff_utc,
            historical_snapshots=historical_snapshots,
        )
        if guard.get("status") == "BLOCKED":
            return guard

        if squad is None:
            state = self.adapter.get_state(target_gw)
            if state['optimization_state'] != "OPTIMIZATION_READY":
                return {"status": "BLOCKED", "reason": state['optimization_state']}
            squad_ids = state['squad_ids']
            raw_squad = [self.elements[pid] for pid in squad_ids if pid in self.elements]
        else:
            raw_squad = squad

        pos_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
        normalized_squad = []
        for p_raw in raw_squad:
            p = dict(p_raw)
            if "position" not in p and "element_type" in p:
                p["position"] = pos_map.get(p["element_type"], "UNKNOWN")
            if "player_id" not in p:
                p["player_id"] = p.get("id", 0)
            normalized_squad.append(p)

        # Current-data gate (fail loudly, never silently plan on zeros).
        events = getattr(self, "events", None) or (getattr(self, "bootstrap", None) or {}).get("events")
        if not events:
            raise CurrentDataError("Bootstrap events missing; cannot confirm target gameweek is upcoming.")
        assert_future_gameweeks([target_gw], events)
        assert_gameweeks_have_fixtures(self.fixture_map, [target_gw])
        blank = set(blank_teams(self.fixture_map, target_gw, {p.get("team") for p in normalized_squad}))
        blank_players = [p["player_id"] for p in normalized_squad if p.get("team") in blank]

        assert_projections_valid(
            {p["player_id"]: calculate_player_gw_ep(p, target_gw, self.fixture_map) for p in normalized_squad},
            context=f"GW{target_gw} prediction",
        )
        xi_res = select_best_legal_xi(normalized_squad, target_gw, self.fixture_map)
        xi_players = [
            {"id": p.get("player_id", p.get("id")), "name": p.get("web_name"), "ep": p.get("gw_ep", 0.0), "position": p.get("position")}
            for p in xi_res["starting_xi"]
        ]
        captain = {
            "id": xi_res["captain"].get("player_id", xi_res["captain"].get("id")),
            "name": xi_res["captain"].get("web_name"),
            "ep": xi_res["captain"].get("gw_ep", 0.0),
            "position": xi_res["captain"].get("position")
        } if xi_res.get("captain") else None

        result = {
            "xi": xi_players,
            "captain": captain,
            "formation": xi_res.get("formation"),
            "bench": [
                {"id": p.get("player_id", p.get("id")), "name": p.get("web_name"), "ep": p.get("gw_ep", 0.0), "position": p.get("position")}
                for p in xi_res.get("bench", [])
            ],
            "total_ep": xi_res.get("total_ep", 0.0),
            "target_gw": target_gw,
            "blank_gameweek_players": blank_players,
        }
        if "evidence" in guard:
            result["evidence"] = guard["evidence"]
            result["action"] = guard["evidence"]["action"]
            result["executable"] = bool(guard["evidence"]["material_action_allowed"])
        if "historical_snapshots_admitted" in guard:
            result["historical_snapshots_admitted"] = guard["historical_snapshots_admitted"]
        return result

def _guard_prediction_inputs(
    *,
    evidence_claims,
    proposed_action,
    decision_cutoff_utc,
    historical_snapshots,
) -> Dict[str, Any]:
    """Apply the evidence policy and temporal firewall before a prediction is used."""
    guard: Dict[str, Any] = {}
    if historical_snapshots is not None or decision_cutoff_utc is not None:
        if not decision_cutoff_utc or historical_snapshots is None:
            return {"status": "BLOCKED", "reason": "TEMPORAL_CUTOFF_REQUIRED"}
        try:
            admitted = admit_snapshots(decision_cutoff_utc, list(historical_snapshots))
        except (TemporalLeakageError, SnapshotIntegrityError) as exc:
            return {"status": "BLOCKED", "reason": "TEMPORAL_LEAKAGE", "detail": str(exc)}
        guard["historical_snapshots_admitted"] = len(admitted)
    if evidence_claims is not None:
        guard["evidence"] = evaluate_evidence(evidence_claims, proposed_action=proposed_action)
    return guard

if __name__ == "__main__":
    engine = PredictionEngine(os.environ.get("FPL_TEAM_ID"))
    from fpl_skill.current_data import next_gameweek
    print(json.dumps(engine.run(next_gameweek(engine.events)), indent=2))
