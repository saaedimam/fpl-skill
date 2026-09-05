#!/usr/bin/env python3
"""
FPL Historical-Matchup Signal Layer — diagnostic only.

Does NOT feed into calculate_player_gw_ep() or the optimizer.
Attaches evidence to D0 for display alongside D3/D4.
"""

import json
import urllib.request
from typing import Dict, List, Any, Optional
from collections import defaultdict


BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"
ELEMENT_SUMMARY_URL = "https://fantasy.premierleague.com/api/element-summary/{}/"


def _fetch(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "FPL-Skill/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_bootstrap() -> Dict:
    return _fetch(BOOTSTRAP_URL)


def fetch_fixtures() -> List[Dict]:
    return _fetch(FIXTURES_URL)


def fetch_player_history(element_id: int) -> List[Dict]:
    try:
        data = _fetch(ELEMENT_SUMMARY_URL.format(element_id))
        return data.get("history", []) or []
    except Exception as e:
        print(f"fetch_player_history({element_id}) failed: {e}")
        return []


def attach_historical_signals(
    d0_squad: List[Dict[str, Any]],
    fixtures: Optional[List[Dict]] = None,
    fetch_per_player: bool = False,
    player_histories: Optional[Dict[int, List[Dict]]] = None
) -> List[Dict[str, Any]]:
    """
    Attach diagnostic h2h evidence to each player in the D0 squad.
    Only uses verified fields — never invents historical matchups.
    """
    team_id_to_name = {}
    try:
        bs = fetch_bootstrap()
        team_id_to_name = {t["id"]: t["name"] for t in bs.get("teams", [])}
    except Exception:
        pass

    fixtures = fixtures or fetch_fixtures()
    finished = [f for f in fixtures if f.get("finished")]

    # Build fixture-result lookup: team_id -> (result, score)
    team_recent_results: Dict[int, List[Dict]] = defaultdict(list)
    for f in sorted(finished, key=lambda x: x.get("kickoff_time") or "", reverse=True):
        h, a = f.get("team_h"), f.get("team_a")
        hs, as_ = f.get("team_h_score"), f.get("team_a_score")
        if None in (h, a, hs, as_):
            continue
        t = f.get("kickoff_time")
        if h is not None:
            if hs > as_:
                res = "W"
            elif hs < as_:
                res = "L"
            else:
                res = "D"
            team_recent_results[h].append({"result": res, "score": f"{hs}-{as_}", "opp_id": a, "kickoff": t})
        if a is not None:
            if hs > as_:
                res2 = "L"
            elif hs < as_:
                res2 = "W"
            else:
                res2 = "D"
            team_recent_results[a].append({"result": res2, "score": f"{as_}-{hs}", "opp_id": h, "kickoff": t})

    # Resolve per-player history (either supplied or fetched)
    if player_histories is None and fetch_per_player:
        player_histories = {}
        for p in d0_squad:
            eid = p.get("player_id")
            player_histories[eid] = fetch_player_history(eid)
    player_histories = player_histories or {}

    enriched = []
    for p in d0_squad:
        eid = p.get("player_id")
        hist = player_histories.get(eid, [])

        # Per-player vs recent opponents (season-to-date, verified only)
        h2h_by_opp: Dict[str, Dict] = {}
        for h in hist:
            opp_id = h.get("opponent_team")
            opp_name = team_id_to_name.get(opp_id, str(opp_id))
            key = opp_name
            if key not in h2h_by_opp:
                h2h_by_opp[key] = {"gws": [], "minutes": 0, "goals": 0, "assists": 0, "points": 0}
            h2h_by_opp[key]["gws"].append(h.get("round"))
            h2h_by_opp[key]["minutes"] += int(h.get("minutes") or 0)
            h2h_by_opp[key]["goals"] += int(h.get("goals_scored") or 0)
            h2h_by_opp[key]["assists"] += int(h.get("assists") or 0)
            h2h_by_opp[key]["points"] += int(h.get("total_points") or 0)

        # Team recent result snippet (team-level, from fixtures)
        tid = p.get("team")
        team_name = p.get("name") or p.get("web_name")
        recent_team_form = team_recent_results.get(tid, [])

        enriched.append({
            **p,
            "h2h_by_opp": h2h_by_opp,
            "team_recent_results": recent_team_form[:5],
        })

    return enriched


def render_counterfactual(
    xi_player: Dict[str, Any],
    candidate: Dict[str, Any],
    gw: int,
    fixture_map: Dict,
) -> Dict[str, Any]:
    """
    Render a single XI-swap counterfactual using ONLY verified EP/xG/xA.
    Form is NOT a signal — shown alongside as diagnostic curiosity only.
    """
    cur_ep = xi_player.get("gw_ep") if xi_player.get("gw_ep") is not None else xi_player.get("ep_gw", [0])[0] if isinstance(xi_player.get("ep_gw"), list) else 0
    cand_ep = candidate.get("gw_ep") if candidate.get("gw_ep") is not None else candidate.get("ep_gw", [0])[0] if isinstance(candidate.get("ep_gw"), list) else 0

    cur_xg = xi_player.get("expected_goals") if xi_player.get("expected_goals") is not None else xi_player.get("supporting_data", {}).get("expected_goals", 0)
    cur_xa = xi_player.get("expected_assists") if xi_player.get("expected_assists") is not None else xi_player.get("supporting_data", {}).get("expected_assists", 0)
    cand_xg = candidate.get("expected_goals") if candidate.get("expected_goals") is not None else candidate.get("supporting_data", {}).get("expected_goals", 0)
    cand_xa = candidate.get("expected_assists") if candidate.get("expected_assists") is not None else candidate.get("supporting_data", {}).get("expected_assists", 0)

    return {
        "out": xi_player.get("web_name"),
        "in": candidate.get("web_name"),
        "delta_ep": round(cand_ep - cur_ep, 2),
        "diagnostic_form": {"out_form": xi_player.get("form"), "in_form": candidate.get("form")},
        "verified": {"cur_xG": cur_xg, "cur_xA": cur_xa, "cand_xG": cand_xg, "cand_xA": cand_xa},
        "note": "Diagnostic only — form does not drive the decision. Selection bound to verified gw_ep/EP.",
    }
