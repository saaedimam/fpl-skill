# Public source URLs

Checked with unauthenticated HTTP HEAD on 2026-11-09. Status is reachability only. It is not a content capture, not a formula, and not evidence that a Phase 3 gate passed.

No cookies, no `/api/my-team/`, and no `/api/me/` were requested. Account writes stay disabled. A page URL still needs a separate verified attestation before the optimizer-integration gate can accept it.

## LiveFPL pages

`https://www.livefpl.net/` is a client-rendered page. Its HTML does not list these routes. Several paths redirect to `plan.livefpl.net`.

| Requested | Result | Final URL |
|---|---|---|
| `https://www.livefpl.net/` | 200 | same |
| `https://www.livefpl.net/rank` | 200 | same |
| `https://www.livefpl.net/planner` | 200 | same |
| `https://www.livefpl.net/prices` | 200 | same |
| `https://www.livefpl.net/games` | 200 | same |
| `https://www.livefpl.net/price_changes` | 200 | `https://plan.livefpl.net//price_changes` |
| `https://www.livefpl.net/autosubs` | 200 | `https://plan.livefpl.net//autosubs` |
| `https://www.livefpl.net/chips` | 200 | `https://plan.livefpl.net//chips` |
| `https://www.livefpl.net/ticker` | 200 | `https://plan.livefpl.net//ticker` |
| `https://www.livefpl.net/combos` | 200 | `https://plan.livefpl.net//combos` |
| `https://www.livefpl.net/dgw` | 200 | `https://plan.livefpl.net//dgw` |
| `https://www.livefpl.net/Overall` | 200 | `https://plan.livefpl.net//Overall` |
| `https://www.livefpl.net/top10k` | 200 | `https://plan.livefpl.net//top10k` |
| `https://www.livefpl.net/rank_tiers` | 200 | `https://plan.livefpl.net//rank_tiers` |
| `https://www.livefpl.net/elite` | 200 | `https://plan.livefpl.net//elite` |
| `https://www.livefpl.net/top10k_ownership` | 200 | `https://plan.livefpl.net/combos` |
| `https://www.livefpl.net/leagues` | 200 | `https://plan.livefpl.net/leagues/8449` |
| `https://plan.livefpl.net/` | 200 | same |
| `https://plan.livefpl.net/price_changes` | 200 | same |
| `https://plan.livefpl.net/chips` | 200 | same |
| `https://plan.livefpl.net/ticker` | 200 | same |
| `https://plan.livefpl.net/combos` | 200 | same |
| `https://plan.livefpl.net/Overall` | 200 | same |
| `https://plan.livefpl.net/top10k` | 200 | same |
| `https://plan.livefpl.net/games` | 200 | same |
| `https://plan.livefpl.net/rank_tiers` | 200 | same |
| `https://www.livefpl.net/whatif` | 500 | not usable |
| `https://plan.livefpl.net/autosubs` | 500 | the `www` redirect above did answer |
| `https://plan.livefpl.net/dgw` | 500 | the `www` redirect above did answer |
| `https://www.livefpl.net/Overall_ownership` | 404 | absent |
| `https://www.livefpl.net/robots.txt` | 404 | absent |
| `https://www.livefpl.net/sitemap.xml` | 404 | absent |

`https://livefpl.net/` redirects to `http://www.livefpl.net/`. Prefer the `https://www` form.

Manager-specific pages such as `https://plan.livefpl.net/{entry_id}` exist in public search results. They are one entry's live view, not a cohort source, and they were not fetched here.

## Official public FPL API

Base: `https://fantasy.premierleague.com/api/`. All of these returned HTTP 200 and `application/json` with no session cookie.

| URL | Use |
|---|---|
| `https://fantasy.premierleague.com/api/bootstrap-static/` | Players, clubs, gameweeks, settings |
| `https://fantasy.premierleague.com/api/fixtures/` | Season fixtures |
| `https://fantasy.premierleague.com/api/fixtures/?event=1` | One gameweek of fixtures |
| `https://fantasy.premierleague.com/api/event-status/` | Provisional or final bonus state |
| `https://fantasy.premierleague.com/api/event/1/live/` | Player stats for one gameweek |
| `https://fantasy.premierleague.com/api/element-summary/1/` | One player's history and upcoming fixtures |
| `https://fantasy.premierleague.com/api/dream-team/1/` | Dream team for one gameweek |
| `https://fantasy.premierleague.com/api/dream-team/` | Season dream team |
| `https://fantasy.premierleague.com/api/regions/` | Region list |
| `https://fantasy.premierleague.com/api/team/set-piece-notes/` | Set-piece notes |
| `https://fantasy.premierleague.com/api/stats/most-valuable-teams/` | Public value table |
| `https://fantasy.premierleague.com/api/entry/1/` | Public manager profile |
| `https://fantasy.premierleague.com/api/entry/1/history/` | Public manager history |
| `https://fantasy.premierleague.com/api/entry/1/transfers/` | Public transfer list |
| `https://fantasy.premierleague.com/api/entry/1/event/1/picks/` | Public gameweek picks |
| `https://fantasy.premierleague.com/api/leagues-classic/314/standings/` | Public classic-league page |

`1` and `314` are public sample ids used only to prove the route answers. Replace them with the id under study. These routes are not authenticated account writes.

Official site pages that returned HTML 200:

- `https://fantasy.premierleague.com/`
- `https://fantasy.premierleague.com/statistics`
- `https://fantasy.premierleague.com/fixtures`
- `https://fantasy.premierleague.com/transfers`

## Not sources

- `https://fantasy.premierleague.com/api/my-team/{id}/` requires a session and was not called.
- A LiveFPL or FPL URL does not by itself satisfy `verified_attestations`.
- Cached numbers on these pages are not fixtures for tests.
