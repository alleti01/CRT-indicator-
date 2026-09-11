# Prop quality gates + 2.5R bank / trail — design

**Date:** 2026-09-10  
**Status:** Draft for review (approved in conversation; not implemented)  
**Mode:** Phase74 local paper only. Frozen Pine and Phase73 engine stay unchanged.

---

## 1. Problem

Chart A (`phase72a_autonomous_trader.pine`, hash `d75ff747…cc1f`) and Chart B (signal ledger) fire the **same** Layer A TAKEs. The ledger cannot filter quality.

Paper is taking every executable TAKE. That path is wrong for a prop drawdown:

- Sep 9: 6 trades, +4.50R, but losses were failed breakdowns / afternoon chop.
- Sep 10: 20 closed trades, 5W / 15L, **−2.5R**. Peak path ~**−6.5R**. Five losers before the first win.
- Overnight / pre-RTH Sep 10: 9 trades, **−5.5R**. RTH: 11 trades, **+3.0R**.
- Loser pattern: chop false-break (1–8 minute stop, MFE often &lt; 1R) and late TAKEs after the impulse is spent (e.g. 10:08 ET short, −21.5 pts slip).
- Winner cap: M0 flattens at **2.5R** while MFE on expansions reached **3.1–4.6R**.

Existing checks do not solve this:

- Pine `NO_CHASE`: vs **arm** price, 1.5 ATR, and only if reaction score ≥ 1.
- Python `pass_chase`: vs **signal** price at fill. A late TAKE has fill ≈ signal, so it passes.
- Webhook `context` is only `BULLISH` / `BEARISH`, never chop.
- Daily halt is a **dollar** cap (`safety.daily_loss_limit` = 500), not a quality skip and not an R-based day stop.

---

## 2. Goal

On paper, **skip** TAKEs that look like chop or end-of-move, **halt** new entries after a small loser budget, and **let expansions run** after banking ~2R via stop (1 contract, no scale-out).

Success for v1 (replay on Sep 9–10 bars + `paper_trades.csv`):

- Fewer losers from false breaks / late TAKEs than the unfiltered book.
- Every kept winner still reaches at least the locked-stop outcome (~+2R) if price later fails; expansions can finish above 2.5R.
- Skip / trail / halt reasons are logged and replayable.
- Frozen Pine hash and Phase73 engine files are not edited.

Out of scope for v1:

- Rewriting Pine TAKE / `takeThreshold`.
- Session-only ban (09:30–16:00). Chop + late-move are the first cut; add a session window later if replay still shows overnight leakage.
- Two-lot scale-out (half off at 2.5R).
- Live combine / funded account.
- Changing Chart B ledger (except it may keep logging the same TAKEs the bot skips).

---

## 3. Architecture

```text
TradingView Chart A  →  /webhook  →  Phase74 LiveStack
                                      │
                                      ├─ existing: hash, health, chase, late
                                      ├─ NEW: quality gates (20 NT bars)
                                      ├─ NEW: day halt (3 losers or −2R)
                                      ├─ fill (1 contract) if all pass
                                      └─ NEW: trail overlay on bars
                                           (no flatten at 2.5R; lock +2.0R; trail 1.0 ATR)
```

**Authorities (unchanged):**

| Layer | Authority |
|-------|-----------|
| Pine | Signal only (what fired) |
| Phase74 quality gates | Permission to fill |
| Phase74 trail overlay | Exit prices after fill |
| Phase73 `TraderEngine` | Frozen FSM / M0 math; overlay intercepts target-flat |

New modules live under `phase74/` only. Do not edit files listed in `phase73/config/PHASE73_ENGINE_FREEZE.json`.

---

## 4. Quality gates (pre-fill)

### 4.1 Inputs

- Last **20 fully closed** 1m bars from the NT provider cache (`recent_bars`). Do not use the in-progress bar.
- **ATR** = live NT ATR already used for paper risk (`_with_live_atr` / provider ATR), **not** the webhook `atr` field (often `1.0`).
- If fewer than 20 bars or ATR is missing / not healthy → **do not fill** (`SKIP_DATA`). Same fail-closed idea as `PASS_DATA_UNHEALTHY`.

Definitions on those 20 bars:

- `range_high` = max(high)
- `range_low` = min(low)
- `box` = `range_high - range_low`
- `close` = last closed bar close
- `progress` (with signal direction):
  - SHORT: `(first_close - last_close)` of the 20-bar window  
  - LONG: `(last_close - first_close)`
  - Use first and last **closes** so a single wick does not count as a finished impulse.

### 4.2 Skip rules (evaluate in this order, first match wins)

| Reason | Condition |
|--------|-----------|
| `SKIP_CHOP` | `box < 2.0 * ATR` |
| `SKIP_FALSE_BREAK` | SHORT and (`close` in bottom **15%** of `box` **or** `close <= range_low + 0.25 * ATR`). LONG and (top 15% **or** `close >= range_high - 0.25 * ATR`) |
| `SKIP_LATE_MOVE` | `progress > 1.0 * ATR` |

If `box == 0`, treat as `SKIP_CHOP`.

15% of box: SHORT if `(close - range_low) / box <= 0.15`. LONG if `(range_high - close) / box <= 0.15`.

### 4.3 Existing gates still apply

After quality gates pass: current `evaluate_entry` (data health, position conflict, stale, `pass_late`, `pass_chase` at **1.5 ATR** vs signal price). Do not loosen chase.

### 4.4 Logging

Append one JSONL row per webhook TAKE to `phase74/logs/quality_skips.jsonl` (and a CSV mirror) whether skipped or taken:

- `received_at_utc`, `signal_id`, `direction`, `decision` (`TAKE` or `SKIP`)
- `reason` (`TAKE`, `SKIP_CHOP`, `SKIP_FALSE_BREAK`, `SKIP_LATE_MOVE`, `SKIP_DATA`, plus existing PASS_* if those fire first)
- `atr`, `box`, `box_atr`, `progress_atr`, `range_low`, `range_high`, `close`
- `percentile_in_box` (0 = at low, 1 = at high)

Never send a skip back to TradingView. Chart A may still alert; the bot just does not fill.

---

## 5. Day halt (prop)

New entries halt when **either**:

- **3** realized losers on the session date (America/New_York), or
- realized session P&amp;L **≤ −2.0R** (sum of closed `net_R`)

Open trade continues to manage (stop / trail / max hold). Halt clears on the next NY session date.

Log `HALT_DAY_LOSERS` or `HALT_DAY_R`. Existing dollar `daily_loss_limit` remains as a backstop; do not remove it.

---

## 6. Winner management (1 contract)

`max_contracts` stays **1**. There is no half-size scale-out.

### 6.1 Until 2.5R is touched

- Initial stop = **−1.0R** (unchanged M0 stop).
- **Do not** flatten because price touched the 2.5R target.
- Same-bar stop and target: **STOP_FIRST** (unchanged). If the stop is still the original −1R stop, a same-bar 2.5R print that also tags −1R is still a loss.

### 6.2 First touch of +2.5R

On a closed-bar evaluation (same bar OHLC rules as M0):

- LONG: `bar.high >= entry + 2.5 * risk`
- SHORT: `bar.low <= entry - 2.5 * risk`

Then:

1. Set `banked = true`.
2. Move stop to **+2.0R** (LONG: `entry + 2.0 * risk`; SHORT: `entry - 2.0 * risk`).
3. Do **not** exit at the 2.5R price.

If that same bar also trades through the **new** +2.0R stop after the 2.5R touch, exit at **+2.0R** (`TRAIL_STOP` / locked bank), not −1R. Implementation must apply lock before same-bar stop test once 2.5R is tagged.

### 6.3 Trail after banked

Each later bar, only ratchet:

- LONG: `stop = max(stop, extreme_high - 1.0 * ATR)`
- SHORT: `stop = min(stop, extreme_low + 1.0 * ATR)`

`extreme_*` = favorable extreme since entry (trade MFE price).  
`ATR` = **entry ATR** (the ATR used to size the original risk), not a live-shrinking ATR.

Stop never loosens. Exit when the bar tags the trail stop (`TRAIL_STOP`).  
**Max hold 60 minutes** still exits at close (`MAX_HOLD_60M`).

### 6.4 Journal

Closed trades must record:

- `exit_reason`: `M0_STOP` | `TRAIL_STOP` | `MAX_HOLD_60M` (no `M0_TARGET` while overlay is on)
- `banked_2r5`: bool
- `locked_r`: 2.0 after bank, else empty
- `mfe_r` / `mae_r` / `net_R` as today

---

## 7. Replay before live paper

Add a script (e.g. `phase74/tools/score_quality_gates.py`) that:

1. Reads `phase74/logs/bars.csv` and `phase74/logs/paper_trades.csv` (or dated exports).
2. For each historical TAKE, applies §4 on the 20 bars **before** the signal bar close.
3. Prints a table: unfiltered book vs gated book (trades kept, W/L, net R, max DD in R, skips by reason).
4. Optionally replays §6 trail on kept winners using following bars (mark as `SIMULATED_TRAIL` — the original exit was 2.5R so this is hypothetical).

**Gate to enable on the live paper process:** skip + halt + trail only after this replay is run on Sep 9 and Sep 10 and the skip reasons look sane (not empty, not skipping every winner). Thresholds in §4.2 are v1 defaults; change only with a replay table, not by feel mid-session.

---

## 8. Config

New `phase74/config/default.json` section (names exact):

```json
"quality_gates": {
  "enabled": true,
  "lookback_bars": 20,
  "chop_box_atr": 2.0,
  "false_break_percentile": 0.15,
  "false_break_edge_atr": 0.25,
  "late_move_atr": 1.0,
  "day_max_losers": 3,
  "day_max_loss_r": 2.0
},
"trail_overlay": {
  "enabled": true,
  "bank_trigger_r": 2.5,
  "lock_stop_r": 2.0,
  "trail_atr": 1.0
}
```

Flags default **on** for paper after replay. `--no-quality-gates` / `--no-trail` on `run_live.py` for A/B against the frozen M0 baseline.

---

## 9. Tests

- Unit: each skip reason on a 20-bar fixture (chop box, short at range low, long after 1.1 ATR drop, pass on expansion away from edge).
- Unit: trail — no exit at 2.5R; stop becomes +2.0R; later bar trails; same-bar 2.5 then back through +2.0R exits +2.0R.
- Unit: day halt after 3 losers; still manages open trade.
- Do not change Phase73 scenario hashes / freeze tests.

---

## 10. Implementation order

1. Replay scorer + fixtures (no live behavior change).
2. Quality gates + skip log, wired in `LiveStack` before fill.
3. Day halt in R / loser count.
4. Trail overlay (suppress M0 target flatten).
5. Paper session with flags on; compare to unfiltered journal.

---

## 11. Non-goals / risks

- Tight gates will skip some continuations (e.g. a late TAKE that still hit +2.5R). That is accepted for prop path.
- 20-bar / 2.0 ATR / 15% / 1.0 ATR are first cuts from Sep 9–10 observation, not a multi-year study.
- Trail can give back 0.5R+ after the 2.5R tag; locked floor is +2.0R, not +2.5R.
- Ledger Chart B will still show TAKEs the bot skipped. That is correct: Pine fired; Python refused.
