import subprocess, json, hashlib, urllib.request, datetime
from typing import Dict, Any, List, Optional
from urllib.error import HTTPError

class FPLAccountAdapter:
    def __init__(self, team_id: str):
        self.team_id, self.base_url = team_id, "https://fantasy.premierleague.com/api"

    def _get_session_cookie(self) -> str:
        return subprocess.run(['security', 'find-generic-password', '-s', 'fpl-agent', '-a', 'auth/session', '-w'], capture_output=True, text=True, check=True).stdout.strip()

    def _fetch_authenticated(self, endpoint: str) -> Optional[Dict[str, Any]]:
        try:
            req = urllib.request.Request(f"{self.base_url}{endpoint}")
            req.add_header('Cookie', self._get_session_cookie())
            req.add_header('User-Agent', 'Mozilla/5.0')
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except (HTTPError, ValueError):
            return None

    def get_bootstrap(self) -> Dict[str, Any]:
        with urllib.request.urlopen(f"{self.base_url}/bootstrap-static/") as resp:
            return json.loads(resp.read().decode('utf-8'))

    def get_fixtures(self) -> List[Dict[str, Any]]:
        with urllib.request.urlopen(f"{self.base_url}/fixtures/") as resp:
            return json.loads(resp.read().decode('utf-8'))

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
        api_current = next(e['id'] for e in bootstrap['events'] if e['is_current'])
        picks_data = self._fetch_authenticated(f"/entry/{self.team_id}/event/{target_gw}/picks/")
        
        if picks_data and picks_data.get("picks"):
            ownership_event, ownership_state = target_gw, "VERIFIED_CURRENT"
        else:
            picks_data = self._fetch_authenticated(f"/entry/{self.team_id}/event/{api_current}/picks/")
            ownership_event, ownership_state = api_current, "HISTORICAL_FALLBACK"

        optimization_state = "OPTIMIZATION_READY" if ownership_state == "VERIFIED_CURRENT" else "OPTIMIZATION_BLOCKED"
        
        squad_ids = []
        if picks_data and picks_data.get("picks"):
            squad_ids = [p["element"] for p in picks_data["picks"]]
            if len(squad_ids) != 15: optimization_state = "STATE_CONFLICT"; squad_ids = []
        else:
            optimization_state = "STATE_CONFLICT"; squad_ids = []
            
        return {
            "api_current_event": api_current,
            "target_gameweek": target_gw,
            "ownership_event": ownership_event,
            "ownership_state": ownership_state,
            "optimization_state": optimization_state,
            "squad_ids": squad_ids,
            "retrieved_at": datetime.datetime.now().isoformat()
        }
