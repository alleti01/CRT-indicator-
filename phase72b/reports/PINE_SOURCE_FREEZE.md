# Phase72B — Pine Source Freeze

Frozen: **2026-09-02** (Phase72B kickoff)

## Source file

| Field | Value |
|-------|-------|
| Path | `TV_REVIEW/phase72a_autonomous_trader.pine` |
| SHA256 (16) | `ed1ab8e4fd020036` |
| Pine version | **6** (`//@version=6`) |
| Lines | ~1585 (includes Phase72B export layer) |
| Indicator type | `indicator()` overlay |

## Symbol / session assumptions

| Assumption | Value |
|------------|-------|
| Symbol | **NQ1!** (continuous Nasdaq futures) |
| Chart timeframe | **1 minute** (`timeframe.in_seconds() == 60`) |
| TZ_WARN | Non-1M charts show warning; Layer A gated when `TZ_WARN` |
| Session | **24h** (no RTH filter in autonomous trader) |
| Exchange time axis | TradingView **America/New_York** display common; bar `time` is exchange-aligned open ms |
| Python local data | LW NQ continuous 1M, index tz **America/Chicago** |

## Timeframe / HTF assumptions

| Component | Semantics |
|-----------|-----------|
| Developing 5M/15M | Incremental bucket OHLC on 1M chart — **no `lookahead_on`** |
| Completed HTF | `request.security(..., lookahead=barmerge.lookahead_off)` with `[1]` offset |
| Phase71 entry | Signal on closed bar **T** → entry at **open T+1** |
| Phase58 internal | 0.75 ATR stop blocks signals until exit/cooldown |
| Warmup | `WARMUP = 100` bars before Layer A runs |

## Frozen parameters (defaults)

### Core (`grpCore`)

| Input | Default |
|-------|---------|
| structGap | 30 |
| takeThreshold | 4 |
| armedMinScore | 2 |
| armedTimeoutBars | 15 |
| swingPeriod | 5 |
| m1StopAtr | 1.0 |
| p58StopAtr | 0.75 |
| targetR | 2.5 |
| maxHoldBars | 60 |
| bodyThreshATR | 0.3 |
| maxChaseATR | 1.5 |
| cooldownBars | 3 |
| maxWaitBars | 2 |
| decelLookback | 3 |
| microShiftBars | 2 |
| wickRejectionPct | 0.5 |
| ctPullback | 0.5 |
| ctReversal | 0.85 |
| progressLb1m | 8 |
| progressLb5m | 5 |
| progressLb15m | 4 |
| strongProgressAtr | 1.0 |
| weakProgressAtr | 0.3 |

### Phase71 (`grpP71`)

| Input | Default |
|-------|---------|
| t5Bars | 15 |
| t5MfeR | 1.0 |
| enableT5 | true |
| DEBUG_MANUAL_SIGNAL | **false** |

### Display defaults

All signal labels **on** (`showTake`, `showEntry`, `showExits` = true).  
Python review ghosts **on** by default (`showPyExpected` = true) — **display only**.

### Phase72B export (added Phase72B)

| Input | Default |
|-------|---------|
| exportParity | **false** (enable for TV CSV export) |

## Hashes referenced in header (informational — frozen Python stream)

| Name | Hash |
|------|------|
| Signal hash | `0da41f282174679f` |
| Trader hash | `b6adfc04e8885a3d` |

**Phase72B ground truth:** autonomous Pine behavior on TV, **not** the above Python stream.

## Rejected logic (must remain absent)

`PASS_LATE`, `PASS_CHASE`, `EXIT_AND_REVERSE`, `runner_frac`, `trail_atr`

## Phase72B Python mirror

| Path | Role |
|------|------|
| `phase72b/python/series_builder.py` | Pine-equivalent OHLC/HTF series |
| `phase72b/python/pine_features.py` | Feature cache (context/evidence/confidence) |
| `phase72b/python/autonomous_mirror_engine.py` | Sequential Layer A state machine |
| `phase72b/tools/run_phase72b_parity.py` | Parity runner |
