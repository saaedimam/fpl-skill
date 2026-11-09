# Public source URLs

Checked on 2026-11-09 with unauthenticated requests and no cookies. Reachability is not a content capture, not a LiveFPL formula, and not a Phase 3 release attestation. Account writes stay disabled. `/api/my-team/` was not used as a source.

## LiveFPL app shell

`https://www.livefpl.net/` is a client-rendered page. The shell loaded for this check was `https://www.livefpl.net/assets/main-BgOy4Kip.js`. That asset name changes on deploy. `https://livefpl.net/` redirects to `http://www.livefpl.net/`; use the `https://www` form.

Pages that stayed on `www.livefpl.net` and returned the app shell:

- https://www.livefpl.net/
- https://www.livefpl.net/rank
- https://www.livefpl.net/planner
- https://www.livefpl.net/prices
- https://www.livefpl.net/games

The bundle also names `/plan`, `/planner2`, `/prices2`, `/rank2`, `/rank_fs`, and `/rank-preview`.

## Redirects to plan.livefpl.net

| Requested | Lands on | Result |
|---|---|---|
| https://www.livefpl.net/price_changes | https://plan.livefpl.net/price_changes | 200 HTML |
| https://www.livefpl.net/autosubs | https://plan.livefpl.net/autosubs | 200 HTML |
| https://www.livefpl.net/chips | https://plan.livefpl.net/chips | 200 HTML |
| https://www.livefpl.net/ticker | https://plan.livefpl.net/ticker | 200 HTML |
| https://www.livefpl.net/combos | https://plan.livefpl.net/combos | 200 HTML |
| https://www.livefpl.net/dgw | https://plan.livefpl.net/dgw | 200 HTML |
| https://www.livefpl.net/Overall | https://plan.livefpl.net/Overall | 200 HTML |
| https://www.livefpl.net/top10k | https://plan.livefpl.net/top10k | 200 HTML |
| https://www.livefpl.net/rank_tiers | https://plan.livefpl.net/rank_tiers | 200 HTML |
| https://www.livefpl.net/elite | https://plan.livefpl.net/elite | 200 HTML |
| https://www.livefpl.net/leagues | https://plan.livefpl.net/leagues/8449 | 200 HTML |
| https://www.livefpl.net/top10k_ownership | https://plan.livefpl.net/combos | 200 HTML |
| https://www.livefpl.net/plan | https://plan.livefpl.net/myteam/11 | 200 HTML |
| https://www.livefpl.net/whatif | no redirect | 500 |
| https://www.livefpl.net/Overall_ownership | https://plan.livefpl.net/Overall_ownership | 404 |
| https://www.livefpl.net/robots.txt | https://plan.livefpl.net/robots.txt | 404 |
| https://www.livefpl.net/sitemap.xml | https://plan.livefpl.net/sitemap.xml | 404 |

`8449` and `11` are the site's own redirect targets, not this repository's league or team. `https://plan.livefpl.net/rank` redirects back to `https://www.livefpl.net/rank`.

## Public JSON on livefpl.us

Each returned HTTP 200 and `application/json`.

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

`version.json` reported generation `259` and version `6`. Store links in that file: https://apps.apple.com/us/app/livefpl/id6753036580 and https://play.google.com/store/apps/details?id=com.pocketgamerguides.livefpl.

Seen in the bundle and not requested, because they take an id or gameweek:

- `https://livefpl.us/predictedEOs/{id}.json`
- `https://livefpl.us/locals_{id}.json`
- `https://livefpl.us/{gw}/counter_{gw}.json`
- `https://www.livefpl.net/livefplapi/{path}`
- `https://livefpl-api-489391001748.europe-west4.run.app/LH_api2/planner/snapshot?id=`

## Official FPL

Base `https://fantasy.premierleague.com/api/`. Sample ids `1` and `314` only prove the route answers. They are not this account.

| URL | Checked |
|---|---|
| https://fantasy.premierleague.com/api/bootstrap-static/ | 200 JSON |
| https://fantasy.premierleague.com/api/fixtures/ | 200 JSON |
| https://fantasy.premierleague.com/api/fixtures/?event=1 | 200 JSON |
| https://fantasy.premierleague.com/api/event-status/ | 200 JSON |
| https://fantasy.premierleague.com/api/event/1/live/ | 200 JSON |
| https://fantasy.premierleague.com/api/element-summary/1/ | 200 JSON |
| https://fantasy.premierleague.com/api/dream-team/1/ | 200 JSON |
| https://fantasy.premierleague.com/api/dream-team/ | 200 JSON |
| https://fantasy.premierleague.com/api/regions/ | 200 JSON |
| https://fantasy.premierleague.com/api/team/set-piece-notes/ | 200 JSON |
| https://fantasy.premierleague.com/api/stats/most-valuable-teams/ | 200 JSON |
| https://fantasy.premierleague.com/api/entry/1/ | 200 JSON |
| https://fantasy.premierleague.com/api/entry/1/history/ | 200 JSON |
| https://fantasy.premierleague.com/api/entry/1/transfers/ | 200 JSON |
| https://fantasy.premierleague.com/api/entry/1/event/1/picks/ | 200 JSON |
| https://fantasy.premierleague.com/api/leagues-classic/314/standings/ | 200 JSON |

`https://fantasy.premierleague.com/api/settings/` returned 404. Official HTML pages that returned 200: https://fantasy.premierleague.com/ , https://fantasy.premierleague.com/statistics , https://fantasy.premierleague.com/fixtures , and https://fantasy.premierleague.com/transfers .

`https://fantasy.premierleague.com/api/my-team/{id}/` needs a session and was not called. A URL in this list still does not satisfy `verified_attestations`.
