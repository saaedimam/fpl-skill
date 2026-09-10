import subprocess, json, hashlib, urllib.request, datetime, os
from typing import Dict, Any, List, Optional
from urllib.error import HTTPError

class FPLAccountAdapter:
    def __init__(self, team_id: str):
        self.team_id = str(team_id) if team_id is not None else ""
        self.base_url = "https://fantasy.premierleague.com/api"

    def _get_session_cookie(self) -> str:
        cookie = os.environ.get("FPL_SESSION_COOKIE", "")
        if cookie:
            return cookie.strip()
        try:
            res = subprocess.run(
                ['security', 'find-generic-password', '-s', 'fpl-agent', '-a', 'auth/session', '-w'],
                capture_output=True, text=True
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass
        return ""

    def _fetch_authenticated(self, endpoint: str) -> Optional[Dict[str, Any]]:
        cookie = self._get_session_cookie()
        try:
            req = urllib.request.Request(f"{self.base_url}{endpoint}")
            if cookie:
                req.add_header('Cookie', cookie)
            req.add_header('User-Agent', 'Mozilla/5.0')
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception:
            return None

    def get_bootstrap(self) -> Dict[str, Any]:
        with urllib.request.urlopen(f"{self.base_url}/bootstrap-static/", timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def get_fixtures(self) -> List[Dict[str, Any]]:
        with urllib.request.urlopen(f"{self.base_url}/fixtures/", timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def get_profile(self) -> Dict[str, Any]:
        """Fetch manager profile including bank, rank, and squad value."""
        if not self.team_id:
            return {
                "id": None,
                "name": "Unknown",
                "last_deadline_bank": 0,
                "overall_rank": 0,
                "total_points": 0,
                "source": "DEFAULT"
            }

        profile = {
            "id": self.team_id,
            "name": f"Team {self.team_id}",
            "last_deadline_bank": 0,
            "overall_rank": 0,
            "total_points": 0,
            "source": "PUBLIC_ENTRY"
        }

    def _fetch_entry(self) -> Optional[Dict[str, Any]]:
        try:
            req = urllib.request.Request(f"{self.base_url}/entry/{self.team_id}/", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception:
            return None

    def get_profile(self) -> Dict[str, Any]:
        """Fetch manager profile including bank, overall rank, and team name."""
        profile = {
            "id": int(self.team_id) if str(self.team_id).isdigit() else self.team_id,
            "name": "Unknown",
            "last_deadline_bank": 0,
            "overall_rank": 0,
            "total_points": 0,
            "last_deadline_value": 1000,
            "free_transfers": 1,
            "source": "PUBLIC_PROFILE"
        }

        # 1. Try public entry endpoint
        entry_data = self._fetch_entry()
        if entry_data and isinstance(entry_data, dict):
            profile.update({
                "name": entry_data.get("name", profile["name"]),
                "last_deadline_bank": entry_data.get("last_deadline_bank", 0),
                "overall_rank": entry_data.get("summary_overall_rank", 0),
                "total_points": entry_data.get("summary_overall_points", 0),
                "last_deadline_value": entry_data.get("last_deadline_value", 1000)
            })

        # 2. Try authenticated my-team endpoint for latest editable bank
        try:
            my_team = self._fetch_authenticated(f"/my-team/{self.team_id}/")
            if my_team and isinstance(my_team, dict) and "transfers" in my_team:
                t_info = my_team["transfers"]
                if "bank" in t_info:
                    profile["last_deadline_bank"] = t_info["bank"]
                    profile["free_transfers"] = t_info.get("limit", 1) - t_info.get("made", 0)
                    profile["source"] = "AUTHENTICATED_MY_TEAM"
        except Exception:
            pass

        return profile

    def get_active_event_id(self) -> int:
        bootstrap = self.get_bootstrap()
        now = datetime.datetime.now(datetime.timezone.utc)
        events = sorted(bootstrap['events'], key=lambda e: e['deadline_time'])
        for e in events:
            if now < datetime.datetime.fromisoformat(e['deadline_time'].replace('Z', '+00:00')):
                return e['id']
        return events[-1]['id']

    def get_state(self, target_gw: int) -> Dict[str, Any]:
        bootstrap = self.get_bootstrap()
        api_current = next((e['id'] for e in bootstrap['events'] if e.get('is_current')), 1)

        # 1. Check live authenticated editable squad
        my_team = self._fetch_authenticated(f"/my-team/{self.team_id}/")
        picks_data = None
        if my_team and isinstance(my_team, dict) and "picks" in my_team:
            picks_data = my_team
            ownership_event = target_gw
            ownership_state = "VERIFIED_CURRENT"
        else:
            # 2. Fallback to published picks for target_gw
            target_picks = self._fetch_authenticated(f"/entry/{self.team_id}/event/{target_gw}/picks/")
            if target_picks and isinstance(target_picks, dict) and "picks" in target_picks:
                picks_data = target_picks
                ownership_event = target_gw
                ownership_state = "PUBLISHED_EVENT_PICKS"
            else:
                # 3. Fallback to published picks for api_current
                fallback_picks = self._fetch_authenticated(f"/entry/{self.team_id}/event/{api_current}/picks/")
                if fallback_picks and isinstance(fallback_picks, dict) and "picks" in fallback_picks:
                    picks_data = fallback_picks
                    ownership_event = api_current
                    ownership_state = "HISTORICAL_FALLBACK"
                else:
                    ownership_event = api_current
                    ownership_state = "UNAVAILABLE"

        optimization_state = "OPTIMIZATION_READY" if ownership_state == "VERIFIED_CURRENT" else "OPTIMIZATION_BLOCKED"

        squad_ids = []
        if picks_data and isinstance(picks_data, dict) and "picks" in picks_data:
            squad_ids = [p["element"] for p in picks_data["picks"]]
            if len(squad_ids) != 15:
                optimization_state = "STATE_CONFLICT"
                squad_ids = []
        else:
            optimization_state = "OPTIMIZATION_BLOCKED"
            squad_ids = []

        return {
            "api_current_event": api_current,
            "target_gameweek": target_gw,
            "ownership_event": ownership_event,
            "ownership_state": ownership_state,
            "optimization_state": optimization_state,
            "squad_ids": squad_ids,
            "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
