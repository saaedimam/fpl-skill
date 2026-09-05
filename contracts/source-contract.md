# Source Authority Contract — v1.1.0

## Hierarchy
```
L0 Official FPL / Premier League data & rules
L1 Official Premier League / Opta-derived data (BPS, defensive contributions)
L2 Official club/player communications
L3 Reputable sports news / established journalists
L4 FPL expert analysis (written or video)
L5 Podcasts / YouTube / fan analyst channels
L6 Social posts / community signals
```

## Rules
1. A lower-authority source never silently overrides a higher-authority source. To override, the lower source must be corroborated by a source at or above the level of the claim it contradicts, or must itself be promoted to `OFFICIAL`/`VERIFIED_CURRENT_STATE` via the state machines below.
2. L5–L6 are signal-only. They may open an evidence record and raise an alert; they can never alone justify a material transfer/captain/chip decision.
3. A podcast or video is evidence that the speaker made a claim — never evidence that the claim is true.
4. Material claims (anything that would change a transfer, captain, or chip recommendation) require corroboration from at least one independent source at L3 or above, or promotion through the relevant state machine to its terminal state.

## State Machines

### Transfer evidence
```
RUMOUR → REPORTED → ADVANCED → AGREED → OFFICIAL
```
Only `OFFICIAL` (club/league-confirmed) is treated as a completed transfer for squad-value, role, or fixture purposes. Everything before that is tracked as an open evidence record, not acted on as fact.

### Injury evidence
```
REPORTED → CLUB_CONFIRMED → VERIFIED_CURRENT_STATE
```
A journalist or podcast report can create `REPORTED`. Only club/official-source confirmation reaches `CLUB_CONFIRMED`. `VERIFIED_CURRENT_STATE` requires the official FPL status field or equivalent official current-state confirmation.

## Freshness
```
<24h   high-priority / current
24-72h current
3-7d   contextual
>7d    background unless re-confirmed
```
Freshness affects **confidence**, never **authority**. A fresh L5 signal is still L5; a stale L0 fact is still L0, just flagged for re-verification before being used in a material decision.

## Evidence Record (canonical, superset of both consolidated drafts)
```
source_type    : official | club | sports-news | podcast | youtube | expert | social
publisher      :
source_title   :
claim          :
published_at   :
retrieved_at   :
confidence     : high | medium | low
corroboration  : [list of independent supporting sources, if any]
contradictions : [list of conflicting claims/sources, if any]
FPL_impact     : free-text description of what this changes if true
```

## Conflict Handling
When two same-or-higher-authority sources materially disagree and neither state machine resolves it, the claim is recorded as `CONFLICTED`. A `CONFLICTED` claim is never silently resolved by picking the more convenient or more recent side; it is carried into the output as an explicit unresolved item until a higher-authority source resolves it.
