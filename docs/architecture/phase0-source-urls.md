# Public source URLs

Checked on 2026-11-09 with unauthenticated GET requests. No cookies, no account writes, and none of these URLs are release-gate evidence. A page or JSON file existing does not prove a LiveFPL formula.

The current LiveFPL app shell is `https://www.livefpl.net/assets/main-BgOy4Kip.js` (the hash changes when the site deploys). Routes and data URLs below were read from that shell and then requested.

## Pages that stayed on www.livefpl.net

These returned HTTP 200 and the app shell. The data is not in the HTML.

- https://www.livefpl.net/
- https://www.livefpl.net/rank
- https://www.livefpl.net/planner
- https://www.livefpl.net/prices
- https://www.livefpl.net/games

The same bundle also declares `/plan`, `/planner2`, `/prices2`, `/rank2`, `/rank_fs`, and `/rank-preview`.

## Pages that redirect to plan.livefpl.net

| From | First response | Lands on |
|---|---|---|
| https://www.livefpl.net/price_changes | 302 | https://plan.livefpl.net/price_changes |
| https://www.livefpl.net/autosubs | 302 | https://plan.livefpl.net/autosubs |
| https://www.livefpl.net/chips | 302 | https://plan.livefpl.net/chips |
| https://www.livefpl.net/ticker | 302 | https://plan.livefpl.net/ticker |
| https://www.livefpl.net/combos | 302 | https://plan.livefpl.net/combos |
| https://www.livefpl.net/dgw | 302 | https://plan.livefpl.net/dgw |
| https://www.livefpl.net/Overall | 302 | https://plan.livefpl.net/Overall |
| https://www.livefpl.net/top10k | 302 | https://plan.livefpl.net/top10k |
| https://www.livefpl.net/leagues | 302 | https://plan.livefpl.net/leagues/8449 |
| https://www.livefpl.net/plan | 302, then again | https://plan.livefpl.net/myteam/11 |

`8449` and `11` are the site's own redirect targets, not this repository's team or league. https://www.livefpl.net/whatif returned HTTP 500. https://plan.livefpl.net/rank redirects back to https://www.livefpl.net/rank.

## Public JSON the app loads

All of these returned HTTP 200 and `application/json` from `https://livefpl.us` with no session cookie.

- https://livefpl.us/version.json
- https://livefpl.us/teams.json
- https://livefpl.us/players.json
- https://livefpl.us/types.json
- https://livefpl.us/elite.json
- https://livefpl.us/top10k.json
- https://livefpl.us/prediction.json
- https://livefpl.us/fdr2.json
- https://livefpl.us/fixture-kickoffs.json
- https://livefpl.us/top_transfers.json
- https://livefpl.us/api/prices.json
- https://livefpl.us/api/games.json
- https://livefpl.us/planner/fdr.json
- https://livefpl.us/planner/fdr_ratings.json
- https://livefpl.us/planner/fixtures_names.json
- https://livefpl.us/planner/all_player_info.json
- https://livefpl.us/planner/extended_api.json

`version.json` on that date reported generation `259` and version `6`. It also links the store pages https://apps.apple.com/us/app/livefpl/id6753036580 and https://play.google.com/store/apps/details?id=com.pocketgamerguides.livefpl.

Templates seen in the bundle and not requested, because they take an id or gameweek:

- `https://livefpl.us/predictedEOs/{id}.json`
- `https://livefpl.us/locals_{id}.json`
- `https://livefpl.us/{gw}/counter_{gw}.json`
- `https://www.livefpl.net/livefplapi/{path}`
- `https://livefpl-api-489391001748.europe-west4.run.app/LH_api2/planner/snapshot?id=`

## Official FPL documents

These are the public GET documents this repository already uses or can use without a session. Each returned HTTP 200 JSON when checked with an unauthenticated request. `element-summary` and `event/{id}/live` were checked only for id `1`.

- https://fantasy.premierleague.com/api/bootstrap-static/
- https://fantasy.premierleague.com/api/fixtures/
- https://fantasy.premierleague.com/api/event-status/
- https://fantasy.premierleague.com/api/element-summary/{element_id}/
- https://fantasy.premierleague.com/api/event/{event_id}/live/

`https://fantasy.premierleague.com/api/settings/` returned HTTP 404. Authenticated paths such as `/api/my-team/{team_id}/` are not source URLs for this catalog.
