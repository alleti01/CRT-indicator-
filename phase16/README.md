# Phase 16 — frozen CRT Python validation

This project recreates the frozen Phase 14 comparison engine from
`CRT_Core_Phase15_ROBUSTNESS_VALIDATION.pine`. It is a parity/OOS validator,
not an optimizer. No parameter search or automatic filtering is included.

Current status: Phase 16 execution is complete. Pine-to-Python development
parity passed for the inclusive 2026-06-29 through 2026-08-18
America/Chicago window (32/32 main metrics and 84/84 visible breakdown rows).
The untouched 2024-01-01 through 2026-06-26 OOS run then completed on acquired
Databento NQ data. The frozen Retest candidate **failed OOS** with 1,061 trades,
-31.83R, PF 0.942, and 39.52R maximum drawdown. See
`results/oos/PHASE16_OOS_REPORT.md`. No strategy parameter was optimized or
changed after observing the result; 13/13 mechanics tests pass.

## 1. Install

Use Python 3.10 or newer:

```bash
cd phase16
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the mechanics tests from the directory above `phase16/`:

```bash
python -m unittest discover -s phase16/tests -v
```

## 2. Input data

Put files under `phase16/data/` or pass any readable CSV path. Minimum columns:

```text
timestamp,open,high,low,close,volume
```

Accepted timestamp aliases include `datetime`, `date_time`, and `ts`. A
separate `date` plus `time` pair is also accepted. OHLC aliases `O/H/L/C` and
volume aliases `V/vol` are normalized. The loader sorts records, keeps the last
duplicate record, rejects missing/non-numeric values, validates OHLC bounds,
and converts timestamps to `America/Chicago`.

Timestamps are assumed to represent bar opens. If timestamps are naive, pass
their actual zone with `--source-timezone`; otherwise they are interpreted as
exchange-local. Supply history before the requested start so EMA, ATR, pivot,
liquidity, cooldown, and structure state can warm up. The engine processes that
warm-up causally but does not allow entries before the requested window.

One-minute input is detected and resampled to exact five-minute OHLCV:

- open: first
- high: maximum
- low: minimum
- close: last
- volume: sum

Resampling is separated by CME trading date and contract. It never fills a
session gap or combines two contracts. Incomplete five-minute groups are
dropped by default; `--keep-incomplete-resamples` is an explicit diagnostic
override.

## 3. Continuous contracts and rollover

Already prepared, back-adjusted continuous data:

```bash
python phase16/run_backtest.py \
  --data phase16/data/nq_5m.csv \
  --mode parity \
  --contracts prepared \
  --output phase16/results/parity
```

Individual-contract CSVs need a `contract` column. Three roll workflows are supported:

For a Databento continuous download that retains `instrument_id`, preserve the
provider's chosen roll schedule and remove its raw price jump with:

```bash
python phase16/run_backtest.py \
  --data phase16/data/nq_continuous_1m_raw.csv \
  --mode parity \
  --contracts provider-roll \
  --keep-incomplete-resamples \
  --output phase16/results/parity
```

`provider-roll` detects each underlying instrument transition, then applies the
same additive continuity adjustment. It does not infer a different roll date.

### Causal volume roll

```bash
python phase16/run_backtest.py \
  --data phase16/data/nq_contracts_1m.csv \
  --mode parity \
  --contracts volume \
  --contract-order NQH6,NQM6,NQU6,NQZ6 \
  --roll-confirm-sessions 1 \
  --output phase16/results/parity
```

The next session's contract is selected using only completed prior-session
volume. The selector only moves forward through `--contract-order`.

### Explicit rolls

Provide a CSV with `roll_timestamp,new_contract`:

```bash
python phase16/run_backtest.py \
  --data phase16/data/nq_contracts_1m.csv \
  --mode parity \
  --contracts explicit \
  --initial-contract NQH6 \
  --roll-schedule phase16/data/rolls.csv \
  --output phase16/results/parity
```

After selection, both methods use a causal forward additive splice. At each
roll, the incoming contract is shifted so its first adjusted open equals the
outgoing contract's last adjusted close. The same offset is applied to the new
contract's O/H/L/C. This prevents the rollover gap itself from becoming a fake
BOS, CHoCH, sweep, or setup. Volume is not adjusted. The output is suitable for
signal continuity, not absolute-price execution accounting across contracts.

Do not pass an unadjusted vendor continuous series straight to the backtester:
its roll jumps can create artificial events. Databento continuous prices are
unadjusted, so either prepare/back-adjust them first or download individual
contracts and use one of the builders above.

## 4. Frozen implementation

All values live in `config.py` under `FrozenConfig` and are written to each
run's `frozen_config.json`:

- structure pivots: 5 left / 5 right; close-confirmed breaks
- liquidity pivots: 5 left / 5 right; equal tolerance 4 NQ ticks; cap 100/side
- score threshold: 70; strong threshold: 85
- liquidity lookback: 20 bars
- displacement: 10-bar average body, 1.5×
- preferred session: 09:30–16:00; strict filter off
- anti-chase: on, maximum 3 ATR
- same-side cooldown: 5 bars
- HTF regime: prior closed 60-minute bar, EMA 20/50, neutral threshold 0.10 ATR
- Variant C: non-neutral HTF regime and not bucket 6 (16:00–17:59 CT)
- funnel expiry: 8 bars; retest tolerance: 0.10 ATR
- risk: 1.5 ATR; target: 2R; maximum hold: 60 minutes / 12 five-minute bars
- one active trade per model; stop checked before target

Execution order matches the Pine runner where it affects results:

1. Break existing structural levels; skip an ambiguous double break.
2. Confirm/update same-bar structure pivots.
3. Sweep/consume existing liquidity levels.
4. Add newly confirmed liquidity pivots (not eligible on that bar).
5. Update and score Phase 5 events; apply independent directional cooldowns.
6. Apply the frozen Variant-C feed, with long precedence if both directions fire.
7. Give Control every canonical attempt independently.
8. Advance one parent through BOS → later Retest → later Confirm.
9. Attempt model entries, then manage existing trades; stop is first.

The default chart-timeframe CRT previous-range/reclaim series is computed for
source parity, although it does not feed the frozen Phase 14 canonical event.
Phase 2 chart drawings are likewise not a Phase 14 input; the independent
Phase 4 liquidity engine that actually feeds Phase 5 is fully stateful here.

## 5. Development parity

The default parity window is inclusive 2026-06-29 through 2026-08-18 in the
exchange timezone:

```bash
python phase16/run_backtest.py \
  --data phase16/data/nq_continuous_1m_raw.csv \
  --mode parity \
  --contracts provider-roll \
  --keep-incomplete-resamples \
  --reference phase16/data/tradingview_reference.csv \
  --breakdown-reference phase16/data/tradingview_breakdowns.csv \
  --debug-events \
  --output phase16/results/parity
```

The reference file must contain `model,N,total_R`; add `wins`, `losses`,
`win_pct`, `avg_R`, `profit_factor`, and `max_drawdown_R` where available. Copy
`tradingview_reference.example.csv` and enter the actual TradingView export.
No TradingView target values are embedded in the engine.

Classification uses count and Total-R as the primary gate:

- PASS: count difference ≤ 2 and Total-R difference ≤ max(0.50R, 10%)
- WARNING: count difference ≤ 5 and Total-R difference ≤ max(1.50R, 25%)
- FAIL: anything materially larger or missing models

A partial date window is always a parity failure. A warning requires manual
investigation; it does not unlock OOS.

## 6. OOS gate and run

OOS refuses to run unless `--parity-report` points to a report whose overall
status is exactly `PARITY PASS`. It also rejects any date range overlapping the
development window.

```bash
python phase16/run_backtest.py \
  --data phase16/data/nq_5m.csv \
  --start 2025-01-01 \
  --end 2026-06-26 \
  --mode oos \
  --parity-report phase16/results/parity/parity_summary.csv \
  --output phase16/results/oos
```

The OOS report is frozen Retest analysis only. Bad results are reported; the
program never changes a threshold, session, stop, target, tolerance, or expiry.

## 7. Optional Databento download

The backtester does not import or require Databento. The downloader reads only
the `DATABENTO_API_KEY` environment variable. Do not paste a key into source or
commit it. `.env.example` shows the variable name, but the script intentionally
does not auto-load `.env` files.

First estimate cost:

```bash
export DATABENTO_API_KEY='your-key-here'
python phase16/download_databento.py \
  --start 2026-06-01 \
  --end 2026-08-19 \
  --symbols NQ.v.0 \
  --stype-in continuous \
  --estimate-only
```

After reviewing the estimate, explicitly cap acceptable spend:

```bash
python phase16/download_databento.py \
  --start 2026-06-01 \
  --end 2026-08-19 \
  --symbols NQ.v.0 \
  --stype-in continuous \
  --max-cost-usd 10 \
  --output phase16/data/nq_1m.csv
```

Downloads are split into resumable seven-day requests by default. If a remote
gateway times out, the client retries the failed chunk and keeps every completed
part under `<output>.parts/`. Rerunning the same command resumes those parts.
Use `--chunk-days 3` for an especially slow connection.

For individual contracts, use comma-separated raw symbols and
`--stype-in raw_symbol`, preserve the returned symbol as `contract`, then use a
documented roll method. Downloads default to `GLBX.MDP3` and `ohlcv-1m`.

## 8. Result files

Every run writes `trades.csv`, `diagnostics.json`, and `frozen_config.json`.
The trade export contains model, direction, setup/BOS/retest/confirm/entry/exit
timestamps, entry/stop/target/exit prices, R, score, HTF regime, session bucket,
and exit reason.

Parity adds:

- `parity_summary.csv`
- `python_summary.csv` when a reference is supplied
- `event_debug.csv` when `--debug-events` is enabled

OOS adds:

- `oos_summary.csv`
- `monthly_results.csv`
- `breakdowns.csv` (direction, month, quarter, score band, session, HTF regime)
- `equity_curve.csv`
- `equity_curve.png`
- `drawdown_curve.png`

The debug event log includes the bar timestamp, bullish/bearish BOS, any
liquidity sweep, raw directional setups, canonical directions, and the parent
funnel state.

## Parity caveats to investigate, not tune around

If results differ, compare `event_debug.csv` and `trades.csv` chronologically.
Likely data-definition causes include vendor OHLC differences, whether input
timestamps denote opens or closes, exchange session templates, exact contract
roll adjustment, and tie handling at equal pivot plateaus. Fix data/event
parity only—do not alter frozen trading rules.
