# Research Contract v1.0 — Elite Cohort Public-Data Intelligence

**Status:** DRAFT — evidence-first, public-only. No optimizer integration until gate passes.
**Version:** `research-v1.0` (semver for cohort/observation schema)
**Authority:** L0 public FPL API only (`fantasy.premierleague.com/api`). Extends `contracts/source-contract.md` (L0→L6), does not weaken it.
**Applies to:** All cohort selection, observation capture, dataset assembly, and backtest evaluation claiming elite predictive value.

---

## 1. Purpose

Turn legitimate public data advantages into **reproducible v2 signals** without look-ahead, survivor bias, or private-data leakage. The only elite tell that survives scrutiny is a **timestamped, picks-delta-verified BUY** observed strictly before a GW deadline.

## 2. Public-Only Allowlist

```
GET /api/bootstrap-static/
GET /api/fixtures/
GET /api/element-summary/{element_id}/
GET /api/event/{gw}/live/
GET /api/leagues-classic/{league_id}/standings/?page_standings=N&page_new_entries=N
GET /api/entry/{manager_id}/
GET /api/entry/{manager_id}/history/
GET /api/entry/{manager_id}/transfers/
GET /api/entry/{manager_id}/event/{gw}/picks/
```

Forbidden: `GET /api/my-team/{id}/`, any `Cookie: sessionid`, `Authorization`, brute-force ID enumeration beyond the paginated standings, private leagues without public standings. `transfers_in_event` / `selected_by_percent` from `bootstrap-static` are **aggregate crowd** — never used as elite BUY.

## 3. Cohort Definition (versioned, reproducible)

```
cohort_definition: {
  version: "research-v1.0",
  league_id: 314,                 // public classic league used for pagination (e.g. overall-adjacent; configurable)
  snapshot_event: <int>,          // event whose standings were paginated
  rank_snapshot_at: <ISO8601 UTC>, // when standings were fetched (truth time for rank)
  rank_range: [1, N],             // elite = top-N in that snapshot
  pagination: { page_size: 50, pages_fetched: <int>, has_next: bool },
  dedup_key: "entry_id",          // duplicate manager entries removed
  cross_checks: ["entry/{id}/", "entry/{id}/history/"], // identity + rank/history consistency
  entry_ids: [<int>],             // ordered, deduplicated
  entry_ids_hash: "sha256:<hex>",  // hash of sorted entry_ids list
  content_hash: "sha256:<hex>"     // hash of raw standings pages concatenated
}
```

- Cohort membership is **frozen at `rank_snapshot_at`**. Any manager who later enters/leaves does not retroactively join.
- Multiple snapshots required before gate: at least **3 distinct `rank_snapshot_at` × pre-deadline captures** (e.g. 48h, 24h, 2h before deadline) to prove stability, not cherry-picked timing.

## 4. Observation Record (one row per manager × GW × player BUY)

Every row must contain all 13 required fields; missing field → row rejected (not imputed).

| # | Field | Type | Semantics |
|---|-------|------|-----------|
| 1 | `cohort_definition` | object | Pointer to §3 record (by `entry_ids_hash`) |
| 2 | `manager_id` | int | `entry/{id}` |
| 3 | `rank_snapshot` | int | Overall rank from standings at `rank_snapshot_at` (int, not string) |
| 4 | `player_id` | int | FPL element id (BUY target) |
| 5 | `buy_detected` | bool | `true` iff `player_id` ∈ picks(GW) ∖ picks(GW-1) (picks delta, §5) |
| 6 | `transfer_timestamp` | ISO8601 UTC | `transfers[]` entry `time` for that element_in; `null` if free-hit/wildcard bulk not individually timestamped → `confidence` downgraded |
| 7 | `deadline_timestamp` | ISO8601 UTC | `bootstrap-static.events[gw].deadline_time` (UTC, ends with `Z`) |
| 8 | `minutes_to_deadline` | float | `(deadline - transfer_time).total_seconds()/60` — negative = leaked look-ahead, rejected |
| 9 | `source_endpoint` | string | Exact endpoint that yielded the observation, e.g. `GET /api/entry/42/event/4/picks/` |
| 10 | `observed_at` | ISO8601 UTC | Wall-clock UTC when adapter fetched the response |
| 11 | `response_hash` | string | `sha256:<hex>` of raw response bytes for `source_endpoint` |
| 12 | `provenance` | enum | `picks_delta_verified` \| `transfers_endpoint_only` \| `conflicted` — only first is gate-eligible |
| 13 | `confidence` | enum | `high` \| `medium` \| `low` \| `provisional` — see §7 |

Additional carried fields (optional): `gw`, `element_in_cost`, `chip_active`, `is_wildcard_gw`.

## 5. BUY Detection — Picks Delta (authoritative)

```
BUY(GW, player) := player ∈ { p.element for p in picks(GW) if p.position ≤ 15 }
                   and player ∉ { p.element for p in picks(GW-1) }
```

- `transfers/` endpoint is **corroboration only**, never primary. Aggregate `transfers_in_event` is not elite.
- Wildcard/Free Hit GWs produce bulk deltas — still valid BUYs but flagged `chip_active != null` and evaluated separately (wildcard signal ≠ single-transfer signal).
- `automatic_subs` ignored (not a BUY).

## 6. Decision-Time Cutoff & Zero Look-Ahead (hard invariant)

```
eligible(observation) := observed_at < deadline_timestamp
                      and transfer_timestamp < deadline_timestamp   // if present
                      and minutes_to_deadline > 0
                      and source_gw == target_gw                  // GW-specific snapshot
```

- Datasets are **GW-specific snapshots**: `bootstrap-static`, `fixtures`, and all `entry/*` fetched with `observed_at` strictly before the GW deadline.
- Post-deadline `picks/` become public (verified: GW1-3 200, GW4 404 pre-deadline) — but a BUY is only counted if its supporting fetches satisfy the cutoff.
- `minutes_to_deadline` is computed with timezone-aware `datetime.fromisoformat(...replace(Z,+00:00))`; naive datetimes rejected.
- Historical `entry/history/` (`past` seasons) is aggregate only, never per-GW — cannot supply out-of-sample labels.

## 7. Provenance → Confidence

| Provenance | Condition | Confidence |
|---|---|---|
| `picks_delta_verified` | BUY appears in picks delta AND transfers corroborates (or chip GW with no single transfer row) | `high` |
| `transfers_endpoint_only` | BUY in transfers but picks unavailable (404 / missing GW-1) | `provisional` (excluded from gate) |
| `conflicted` | picks delta and transfers disagree, or same player both in/out | `low` → `conflicted` (excluded) |

Only `picks_delta_verified` + `high`/`medium` rows enter primary backtest.

## 8. Raw Evidence Archive

For every fetch: `{ url, status, observed_at_utc, response_bytes_sha256, content_hash, raw_path }` stored under `evidence/research/<YYYY-MM-DD>/`. Raw bytes retained verbatim; hashes recomputed on read for reproducibility check. Truncated/missing bodies → fetch marked failed (see §9).

## 9. Resilience, Rate Limits, Caching, Partial Failure

- Rate limit: ≥300ms between requests, exponential backoff on 429/5xx (1s, 2s, 4s, max 3 retries), `Retry-After` honored.
- Retries are idempotent; partial cohort is **usable but flagged**: `cohort.completeness = fetched_ids / target` and `failed_ids: [int]`.
- Stale snapshot: if `bootstrap-static` `events[].deadline_time` differs from cached deadline by >60s → cache invalidated, refetch.
- 404 on `picks/` for future GW = expected (pre-deadline); not an error — observation is `null` BUY for that GW.
- Schema drift: unknown fields preserved, required fields missing → `FieldNotFoundError`, fetch marked failed, row excluded (tested in adversarial suite).

## 10. Dataset Assembly & Leakage Guards

- One dataset per **(cohort_snapshot_at, target GW)** pair. Never mix pre- and post-deadline observations.
- Elite crowd comparison: every elite BUY rate compared to **bootstrap crowd baseline** (`selected_by_percent` / `transfers_in_event` distribution) at the same `observed_at` cutoff.
- Out-of-sample: evaluation GWs must be **strictly after** all cohort-selection GWs. No OOS GW may share a deadline with its cohort selection snapshot.
- Cohort membership reproducibility: re-paginating the same `(league_id, snapshot_event, rank_snapshot_at)` must reproduce `entry_ids_hash`; otherwise dataset invalid.

## 11. Gate Before Optimizer Integration (all must pass)

| # | Criterion | Threshold |
|---|-----------|-----------|
| G1 | Cohort size | ≥200 deduplicated managers (target 500) |
| G2 | Snapshot multiplicity | ≥3 pre-deadline snapshots at distinct lead times (e.g. 48h/24h/2h) with `observed_at < deadline` proven |
| G3 | Picks-delta verification | 100% of BUY rows in primary set are `picks_delta_verified` |
| G4 | Reproducibility | Raw responses archived with `response_hash`; cohort `entry_ids_hash` and `content_hash` recomputed and matched |
| G5 | OOS protocol | Pre-registered OOS GWs, strictly post-cohort; no shared deadlines |
| G6 | Incremental value | Elite BUY signal beats strong baseline (bootstrap crowd / price-momentum / form) with **95% CI not crossing zero** on OOS |
| G7 | Costed | Leakage corrected: `PROVEN` (incremental, costed, CI>0) / `PROMISING` (incremental but CI straddles 0 or <200) / `REJECTED` (no incremental value or leakage) |
| G8 | Bias audit | Survivor/look-ahead leakage tests green (see adversarial suite) |

## 12. Versioning

`research-v1.0` pinned in code (`RESEARCH_CONTRACT_VERSION = "research-v1.0"`). Any change to cohort definition, observation fields, or cutoff rule → minor/major version bump and datasets re-stamped. Mixed-version datasets never evaluated together.

## 13. References

- Source authority:`contracts/source-contract.md`
- Prediction chain:`contracts/prediction-contract.md`(L0 inputs only elite signal; elite picks derived observations, not L0 facts own squad)
- Runtime pipeline:`contracts/runtime-contract.md`(RESEARCH stage where contract executes)
- File package truth:`SKILL.md``MANIFEST.json`

## 14. MONITOR — Continuous Observation Operation

MONITOR is the pre-deadline daemon that turns the public allowlist (§2) into timestamped ObservationRecords (§4) without look-ahead (§6).

- **Poller** (`fpl_skill/observation/poller.py`): adaptive poll loop (base 60s, burst 15s within 60 min of deadline), bounded retries, 429/5xx backoff, preserves last-known-good on transient failure, emits `MISSING_MANAGER` exactly once per previously-seen entry that 404s.
- **Watcher** (`fpl_skill/observation/watcher.py`): per-manager realtime loop, ETag conditional requests, `Alert_latency_ms` stamping, intent-event suppression after `finished=true`.
- **Ingest** (`fpl_skill/observation/ingest.py`): typed `Transport`/`HttpResponse`, `fetch_json` with `Retry-After` honor, `SchemaError` on required-field loss, `MissingManagerError` on 404.
- **Tape** (`fpl_skill/observation/tape.py`): deterministic replay harness (`TapeTransport` + `Clock`) proving the 7 acceptance properties without live network; optional live smoke run measures real latency.

MONITOR never writes optimizer inputs and never touches `fpl_skill/api.py` frozen paths; it is purely additive under `fpl_skill/observation/`.

## 15. ARCHITECTURE — Normalized Snapshot → Diff → Event Store

ARCHITECTURE is the single correctness spine. Every poll produces exactly one canonical Snapshot, diffs it, and appends closed-schema events.

```
Transport (public GET) → Snapshot (snapshot.py:build_snapshot)
                      → Diff (diff.py: diff / diff_picks / diff_history / diff_transfers)
                      → Event (model.py:new_event, 13 keys, content_hash)
                      → EventStore (store.py: append-only JSONL, dedup by Event_id)
                      → LatencyLog / Alert sink
```

- **Snapshot** (`snapshot.py`): normalizes `picks` (position 1..11 = XI, 12..15 = bench — never `multiplier`), `history`, `transfers` into one `Snapshot` dict keyed by `manager_id`, `event`, `deadline_utc`, `finished`, `observed_at`.
- **Diff** (`diff.py`): `normalize_picks` / `diff_picks`, `normalize_history` / `diff_history`, `transfer_keys` / `diff_transfers`; identical snapshots emit zero events; post-GW `automatic_subs` never become intent events.
- **Event Store** (`store.py:EventStore` + `LatencyLog` + `SnapshotStore`): append-only JSONL keyed by `Event_id`; `exists()`/`append()` are restart-safe via `Content_hash` dedup; `LatencyLog.rows()` feeds the replay gate latency report.
- **Event Schema** (`schemas/event.schema.json`, canonical keys in `fpl_skill/observation/model.py:EVENT_KEYS`): closed 13-key contract — `Event_id`, `Manager_id`, `Event_type`, `Old_state`, `New_state`, `Event_time`, `Detected_at`, `Source_endpoint`, `Source_observed_at`, `Content_hash`, `Schema_version`, `Provenance`, `Confidence`. `Event_time` is `None`→`"UNKNOWN"` when the public API exposes no manager-action timestamp (captaincy/chip/squad/bench); only `transfers[].time` and chip-activation times populate it. `Content_hash = sha256({Manager_id, Event_type, Event_time||"UNKNOWN", New_state})`, `Event_id = Content_hash[:24]`.

## 16. Event Schema Artifact — `schemas/event.schema.json` (event.schema)

The file `schemas/event.schema.json` (`$id: fpl-skill/schemas/event.schema.json`, `title: ObservationEvent`) is the wire-formalization of `EVENT_KEYS`. Required: all 13 keys; `Event_type` enum `TRANSFER|CAPTAINCY|CHIP|SQUAD|BENCH|MANAGER_JOINED|FINANCIAL_CHANGE|MISSING_MANAGER|SCHEMA_CHANGE|STALE_RESPONSE|POLL_RECOVERY`; `Provenance` enum `picks_delta_verified|transfers_endpoint_only|conflicted|public_api`; `Confidence` enum `high|medium|low|provisional`; `Schema_version` must equal `model.SCHEMA_VERSION` (`obs.0.1.0`). No extra keys permitted (`additionalProperties: false`). Unknown fields in upstream payloads are preserved in `New_state` but never promoted to top-level keys.

## 17. Latency Budgets & Measurement (latency)

Three latencies are stamped on every event and asserted in `tests/test_replay_gate.py`:

- **Observation latency** (`Observation_latency_ms` / `Observation_latency_s`): `Source_observed_at − Event_time` when `Event_time` is known; `null` when `Event_time` is `UNKNOWN` (design, not a miss). Measures how long after the manager's action the public API made it observable.
- **Detection latency** (`Detection_latency_ms` / `Detection_latency_s`): `Detected_at − Source_observed_at`. Time between fetching the response and recognizing the transition. Poller stamps `Detected_at` at diff time; Watcher recomputes as `max(0, Detected_at − Source_observed_at)`.
- **Alert latency** (`Alert_latency_ms`): `Alert_time − Detected_at` (Watcher `on_alert` path via `alerts.SafeEmitter`).

Budgets (tape replay, zero-sleep injected clock): `Detection_latency_ms` p95 < 50 ms, `Alert_latency_ms` p95 < 100 ms. Live smoke (real network, 60s poll): `Observation_latency_s` median < poll interval + 5s, `Detection_latency_s` p95 < 1s. `LatencyLog` persists one row per event; `tape.summarize_latency(poller.latency.rows())` reports `observation_latency_min/max_s` and `detection_latency_avg_s`. Latency never influences eligibility (§6); it is a quality signal only.

