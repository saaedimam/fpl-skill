# LiveFPL Public-Surface Reverse-Engineering Notes

**Captured:** 2026-11-08  
**Target:** https://www.livefpl.net/  
**Purpose:** Evidence-led feature decomposition for Phase 3 FPLSKILL integration.  
**Status:** PARTIAL — public rendered-page inspection only; dynamic runtime, network calls, JavaScript bundles, and authenticated flows were not inspected.

## 1. Method and limits

This is a black-box inspection of public pages and their rendered content. It is not a source-code clone. No authentication, access-control bypass, private API, account mutation, or copying of proprietary assets/code was used.

The connected Context.dev web extraction service was unavailable because its API key was disabled. The connected Browser Use service could not start because the project had insufficient credits. Public page inspection through the available web reader was used as a limited fallback.

Important freshness warning: the reader returned cached pages with crawl ages ranging from approximately 2 months to over a year. Some pages contained 2025/26 or older sample data. All observed numeric values are stale examples, not current FPL state and not valid implementation fixtures. Route visibility and page structure are useful leads, but must be re-verified against a fresh browser session before implementation sign-off.

## 2. Observed page contracts

| Route | Observed public behavior / fields | Evidence status | FPLSKILL integration implication |
|---|---|---|---|
| `/rank` | Navigation identifies Live Rank; page body was not readable in the current inspection. | Route/title only; dynamic body unavailable. | Keep observed rank separate from simulated rank. Need fresh capture of inputs, update cadence, rank formula and error states before parity claims. |
| `/planner` | Navigation identifies Transfer Planner; page body was not readable. | Route/title only; dynamic body unavailable. | Map against existing `transfer_intelligence.py`; do not claim planner parity until horizon, FT/hit/chip, selling-price and scenario behavior are captured. |
| `/prices` | Navigation identifies Prices; direct page body unavailable. | Route/title only; dynamic body unavailable. | Inspect fresh page and official FPL fields before implementing a price UI or model. |
| `/price_changes` | Actual price-change history page. Visible filters: direction, team, range, player/team/price search. Table columns: date, player, team, old price, new price, direction. Page text says it updates after price changes, usually around 01:30 GMT. A link leads to the predictor. | Rendered content available, cached about 2 months. | Keep observed confirmed changes distinct from predicted risk. Use official `now_cost` and timestamped snapshots; calibrate probabilities rather than hardcoding thresholds. |
| `/autosubs` | Top-10K and Overall sections. Shows average before/after autosubs, net increase, players subbed in/out, old/new/increased EO, live points, and vice-captain changes. | Rendered content available, cached about 3 months. | Implement active-season substitution rules and compare to official `automatic_subs`; expose EO/captain changes as derived cohort estimates with coverage. |
| `/chips` | Top-10K vs Overall sample comparison; chip use in current GW and total season; number of chips used; captain, chip, ownership and wildcard/free-hit template views. | Rendered content available, cached about 3 months. | Use official entry history and frozen cohort denominators. Popularity is descriptive, not a chip recommendation. |
| `/ticker` | Fixture matrix by team across GW1–GW38, with opponent and home/away notation; link back to planner. | Rendered content available, cached about 3 months. | Reuse normalized official fixtures; implement GW+1…GW+8 decision view first, preserving blanks/doubles and kickoff times. |
| `/combos` | Sample selector includes Elite, Top 100/1K/10K/100K, rank bands and Overall. Team filters and player table show ownership and EO. User can add/remove players and request the percentage of the selected sample owning the complete combination. | Rendered content available, cached about a year. | Build cohort-aware joint ownership from frozen public snapshots. Do not multiply individual ownership percentages; combination ownership is a joint count over the same entries. |
| `/dgw` | Sample selector, DGW/BGW/SGW filter, option to exclude injured/rotation players, average number of players in next GW, player ownership and average team counts. | Rendered content available, cached about 8 months. | Derive fixture counts from official fixtures; injury/rotation exclusions must be explicit user filters, never silently applied. |
| `/Overall` | Live overall statistics: live average, average players played, captain participation, EO table with ownership/live points/status, captaincy table. | Rendered content available, cached about 3 months. | Model the same metric families with timestamp, sample coverage, provisional/final state and exact denominators. |
| `/top10k` | Top-10K live statistics: live average, average players played, captain participation, EO/ownership/live points, captaincy, chip usage and chip-associated points. | Rendered content available, cached about 1.5 years. | Cohort analytics require frozen membership and snapshot-time denominator; stale rendered values are not reusable. |
| `/whatif` | Public page states a valid FPL ID must be entered on the rank page and the feature may take 1–2 hours to become ready. | Rendered text available, but very old cache. | Treat as a hypothesis for scenario simulation; exact scenario controls and calculations remain unverified. |
| `/games` | Navigation identifies Live Games & Bonus; page body was not readable. | Route/title only; dynamic body unavailable. | Need current official live-event schema and provisional-vs-final BPS/bonus behavior; no undocumented fields assumed. |
| `/leagues` | Direct route produced a redirect loop in the reader. Navigation exposes live leagues, league stats, league combinations, favorite managers and elite managers. | Partial navigation only. | Do not infer private league data access. Public league/entry endpoints only, subject to access and privacy constraints. |
| `/rank_tiers`, `/top10k_ownership`, `/Overall_ownership` | Links/routes were discoverable, but bodies were not readable in this pass. | Not verified. | Capture separately before implementing page-specific parity. |

## 3. Cross-feature data model inferred from visible outputs

These are implementation hypotheses from page structure, not verified LiveFPL internals:

- **Cohort:** `cohort_id`, definition (e.g. Top-10K), captured_at, member entry IDs, rank bounds, coverage and frozen membership hash.
- **Entry snapshot:** entry ID, event/GW, retrieved_at, picks, captain, vice-captain, bench order, chip, transfers, bank/value when publicly available.
- **Player cohort metrics:** player ID, picked count, starter count, captain count, vice-captain count, ownership %, captaincy %, EO, live points, minutes/status state.
- **Fixture matrix:** team ID, event, opponent, home/away, fixture count, kickoff, blank/double/single state.
- **Price observation:** player ID, observed price, transfer in/out counters, timestamp, source hash, confirmed change event.
- **Autosub result:** entry ID, event, pre-sub picks, official autosubs, simulated autosubs, captain fallback, mismatch reason.
- **Combination query:** cohort snapshot ID + sorted player IDs; result = entries containing every selected player / valid cohort entries.

Every record in FPLSKILL must additionally carry source, retrieval time, schema version, freshness, content hash and provenance as required by the Phase 3 contract.

## 4. Mapping to the existing FPLSKILL architecture

| LiveFPL capability | Existing FPLSKILL foundation | Required Phase 3 work |
|---|---|---|
| Cohort ownership / EO | `elite_adapter.py`, `observation/`, probabilistic EP | Frozen public cohort snapshots; separate picked/starter/captain/vice-captain rates; explicit EO denominator and confidence. |
| Rank and what-if | `rank_aware_objective1.py`, probabilistic distributions | Observed-vs-forecast rank separation; scenario distribution and calibration. |
| Price predictor/history | `observation/`, current FPL bootstrap snapshots | Confirmed price-change event store plus calibrated rise/fall model. |
| Transfer planner | `transfer_intelligence.py`, `optimizer.py`, `current_data.py` | Extend to GW+1…GW+8 with legality, FT roll, hits, bank, selling price, chips, bench and captaincy scenarios. |
| Games/bonus | `observation/`, official live event ingestion | Current-schema validation, polling, BPS/bonus finality, fail-closed freshness. |
| Autosubs | picks snapshots and current-season rules | Versioned substitution simulator and official differential tests. |
| Chips | public entry history/cohort snapshots | Usage denominator, event timing, counterfactual value, chip availability. |
| Ticker/DGW/BGW | `current_data.py` fixture normalizer | 8-GW fixture grid and player/team fixture counts. |
| Combinations | cohort snapshot store | Exact joint ownership count from the same frozen cohort. |

## 5. Required reverse-engineering follow-up before feature parity

1. Obtain a fresh browser capture for every dynamic route: Rank, Planner, Prices, Games, Leagues, What-if, and rank-tier/ownership pages.
2. Record each page's controls, defaults, validation, sorting, pagination, loading state, update cadence, empty state and error state.
3. With public, non-authenticated traffic only, inspect request/response shapes and identify whether each metric comes from official FPL endpoints or third-party calculations. Respect robots, terms and rate limits; do not replay private/session requests.
4. Reproduce formulas independently from public fixtures and compare against visible outputs. Where the formula cannot be established, label the FPLSKILL result as an estimate and do not claim parity.
5. Build deterministic tests for denominators, missing players, chips, DGW/BGW, captain/vice-captain fallback, bench order, provisional points and stale data.
6. Run walk-forward tests through the immutable Phase 2 temporal firewall. No post-deadline or post-event information may enter a pre-deadline replay.
7. Update the implementation plan with per-feature status and evidence. No workstream is complete until tests, differential checks, calibration and human release review pass.

## 6. Explicit non-goals

- Do not copy LiveFPL source code, proprietary assets, branding, or private API behavior.
- Do not treat the cached page data as current-season truth.
- Do not treat displayed cohort EO as exact global ownership.
- Do not hardcode price thresholds inferred from transfer counts.
- Do not infer live BPS/DEFCON rules when the active official schema does not publish them.
- Do not change the frozen v2.0.0 baseline, P1–P15, or Phase 2 historical firewall/certification.
- Do not merge the Phase 3 branch or certify release without test evidence and explicit human sign-off.

## 7. Public references inspected

- https://www.livefpl.net/rank
- https://www.livefpl.net/planner
- https://www.livefpl.net/prices
- https://www.livefpl.net/price_changes
- https://www.livefpl.net/autosubs
- https://www.livefpl.net/chips
- https://www.livefpl.net/ticker
- https://www.livefpl.net/combos
- https://www.livefpl.net/dgw
- https://www.livefpl.net/Overall
- https://www.livefpl.net/top10k
- https://www.livefpl.net/whatif
- https://www.livefpl.net/games
- https://www.livefpl.net/leagues
- https://www.livefpl.net/rank_tiers
- https://www.livefpl.net/top10k_ownership
- https://www.livefpl.net/Overall_ownership
