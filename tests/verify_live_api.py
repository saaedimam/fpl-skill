#!/usr/bin/env python3
"""
Live API Verification Harness
=============================
Validates the official FPL API endpoints are reachable and their documented
fields/responses are present. Used to freeze the Data Adapter (GATE 2).

Checks:
  1. GET /bootstrap-static/ -> records field name of `events[]` (gameweeks[] alias)
  2. GET /entry/{team_id}/event/{gw}/picks/ -> without auth, records HTTP status
Outputs evidence JSON to: evidence/api-verification-{date}.json

Network-restricted environments are handled gracefully: returns
NETWORK_RESTRICTED status and exits with code 1 (no evidence file written).
"""
import json
import os
import sys
import datetime
import urllib.request
import urllib.error

BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
PICKS_URL = "https://fantasy.premierleague.com/api/entry/{team_id}/event/{gw}/picks/"


def _http_status(path):
    """Return (status_code, body_bytes) for a GET, or (None, None) on network error."""
    try:
        with urllib.request.urlopen(path, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"NETWORK_RESTRICTED: unable to reach {path}: {e}", file=sys.stderr)
        return None, None


def run(bootstrap_url=BOOTSTRAP_URL, pics_url_template=PICKS_URL,
        team_id=None, gw=None):
    """Execute verification. Returns (status, evidence_dict)."""
    now = datetime.date.today()

    # 1. bootstrap-static
    status, body = _http_status(bootstrap_url)
    ev = {"date": str(now), "bootstrap": {"url": bootstrap_url, "http_status": status}}
    if body is not None:
        try:
            data = json.loads(body)
            # Field name check: events[] == gameweeks[] alias
            field = "events" if "events" in data else "gameweeks" if "gameweeks" in data else None
            ev["bootstrap"]["field_name"] = field
            ev["bootstrap"]["event_count"] = len(data.get(field or "", []))
        except (ValueError, TypeError):
            ev["bootstrap"]["field_name"] = None

    # 2. entry picks (team_id + gw required)
    ev["picks"] = {"team_id": team_id, "gameweek": gw}
    if team_id and gw:
        url = pics_url_template.format(team_id=team_id, gw=gw)
        pstatus, pbody = _http_status(url)
        ev["picks"]["url"] = url
        ev["picks"]["http_status"] = pstatus
        if pbody is not None:
            try:
                picks = json.loads(pbody)
                ev["picks"]["picks_count"] = len(picks.get("picks", []))
            except (ValueError, TypeError):
                ev["picks"]["picks_count"] = None
    else:
        ev["picks"]["error"] = "FPL_TEAM_ID and GW required for picks check"

    # 3. Network-restricted?
    if status is None:
        return "NETWORK_RESTRICTED", ev
    return "OK", ev


def main():
    team_id = os.environ.get("FPL_TEAM_ID")
    gw = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FPL_GW")
    status, ev = run(team_id=team_id, gw=gw)

    if status == "NETWORK_RESTRICTED":
        print(json.dumps({"status": status, **ev}, indent=2))
        print("Network restricted; no evidence file written.", file=sys.stderr)
        sys.exit(1)

    fname = f"evidence/api-verification-{datetime.date.today().isoformat()}.json"
    with open(fname, "w") as f:
        json.dump({"status": status, **ev}, f, indent=2)
    print(f"Verification OK -> {fname}")
    sys.exit(0)


if __name__ == "__main__":
    main()
