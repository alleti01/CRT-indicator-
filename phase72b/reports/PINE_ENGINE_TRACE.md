# Phase72B — Pine Engine Trace

Documents **actual** behavior of `phase72a_autonomous_trader.pine` Layer A.
Do not infer intended behavior — mirror this trace in Python.

## Execution model

| Aspect | Behavior |
|--------|----------|
| Bar gating | Layer A runs only when `barstate.isconfirmed and not TZ_WARN and bar_index >= WARMUP` |
| Feature cache | Lines 832–844: context, location, reaction, evidence, confidence computed **every bar** (including warmup) |
| State updates | `var` persistence; reset conditions per section below |
| Intrabar | Layer A uses **closed bar** OHLC; management uses bar `high`/`low` for stop/target hits |
| `[1]` usage | Completed HTF via `request.security` with `[1]` — prior completed HTF bar only |

## Data flow (OHLC → exit)

```
1M OHLC
  → atrRaw = SMA(high-low, 14) → f_atrUse → atrUse
  → Developing 5M/15M buckets (var reset on new bucket ms)
  → Completed HTF via security [1]
  → 1M pivots + 5M pivots (completed) → swing refs
  → Hoisted rolling (rh1m20, imp15m8, …)
  → f_ctx15, f_ctx5, f_computeContext
  → f_locationScore, f_allReactions, f_computeEvidence
  → f_computeConfidence → f_p4Abstain, f_h1Abstain
  → Layer A state machine (below)
  → Phase71 pendingTake → entry T+1 open
  → Phase71 management (STOP_FIRST, T5, max hold)
```

## Layer A bar loop order (lines ~986–1271)

Order is **load-bearing** — Python must match exactly:

1. **Reset display labels** (`decisionLabel`, `p58dDecision`, `p4Status`, `h1Status`)
2. **Coerce p58State** if `p58InTrade` and state is ARMED (1/-1) → IN (2/-2)
3. **Finalize p58 internal entry** on `bar_index == p58EntryBar`: entry=close, stop/target from signal ATR
4. **Phase71 entry** if `pendingTake and bar_index == pendingSignalBar + 1 and posState == FLAT` → open entry, set stops
5. **Phase71 management** if active: STOP_FIRST same-bar, T5 @ t5Bars, maxHoldBars
6. **p58 internal management** if `p58InTrade and bar_index > p58EntryBar`
7. **Cooldown** if `p58State == 3`: skip decrement on exit bar via `p58SkipCooldownDec`
8. **Signal generation** if gates open (not in trade, not cooldown, not block)
9. **Clear** `p58BlockSignals` flag (one-bar block after cooldown ends)

## State variables

### Phase58 FSM (`p58State`)

| Value | Meaning |
|-------|---------|
| 0 | WATCH |
| 1 | ARMED LONG |
| -1 | ARMED SHORT |
| 2 | IN LONG (internal) |
| -2 | IN SHORT (internal) |
| 3 | COOLDOWN |

### Phase71 (`posState`)

| Value | Meaning |
|-------|---------|
| FLAT | No canonical position |
| LONG_ACTIVE / SHORT_ACTIVE | One-position management active |
| PENDING_* | Debug manual only |

### Key `var` flags

| Variable | Known when | Reset |
|----------|------------|-------|
| `p58SkipCooldownDec` | Set true on p58 exit bar | Cleared after cooldown tick |
| `p58BlockSignals` | Set true when cooldown → WATCH | Cleared end of same bar |
| `pendingTake` | Set on canonical SIGNAL | Cleared on entry bar |
| `p58InTrade` | Set on TAKE | Cleared on p58 exit |

## Signal path (raw TAKE → canonical SIGNAL)

1. WATCH → ARMED: `ctxDir` BULLISH/BEARISH + `armedMinScore`
2. ARMED: timeout, context contra, anti-chase, or `total >= takeThreshold`
3. On raw threshold: opportunity `isNew` gate (`structGap`)
4. `f_decideE(evTotal, evReact, evContra, 0)` — variant E, waitUsed=0 at first bar
5. P4/H1 abstain checks
6. `f_posActive()` skip (one-position)
7. Set `pendingTake`, `lastAction=SIGNAL_*`, start p58 internal trade

## Entry / price semantics

| Event | Bar | Price |
|-------|-----|-------|
| SIGNAL | T (close confirmed) | — |
| Phase71 ENTER | T+1 | **open** |
| p58 internal entry finalize | T+1 | **close** (stop uses signal bar ATR) |
| Stop/target init (Phase71) | T+1 | risk = m1StopAtr × **atrUse at entry bar** |

## Exit semantics

| Type | Condition | Priority |
|------|-----------|----------|
| STOP+TARGET same bar | STOP_FIRST | stop wins |
| T5 | bars since entry ≥ t5Bars, MFE < t5MfeR | once |
| MAX_HOLD | bars since entry ≥ maxHoldBars | — |

## ATR (audit item G)

- **Not** `ta.atr` RMA
- `atrRaw = ta.sma(high - low, 14)`
- `f_atrUse`: fallback to [1], scan [2..5], default 1.0

## HTF (audit items A, B)

- Developing buckets: floor(time/ms) boundary, incremental H/L
- Completed: security with `lookahead_off` and index `[1]`
- Python mirror: `phase60/python/developing_htf.py` + native m5/m15 for completed refs

## Cooldown (audit item C)

- Exit bar: `p58SkipCooldownDec=true` → **no** decrement
- Following bars: decrement until 0 → WATCH + `p58BlockSignals=true`

## Known Python mirror gaps (Phase72B v1)

Full `f_computeConfidence` / reversal-support path is **simplified** in `pine_features.py`.
First TV divergence may trace here — fix on first-divergence only.

## Phase72B TV export

Enable `exportParity` → Data Window plots `P72B_*` series for CSV export.
Save as `phase72b/diagnostics/tv_event_log.csv` after normalization.
