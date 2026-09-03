# Phase 32 — Momentum Displacement Pine Implementation Report

## Frozen Architecture
- Signal: **MOMENTUM_DISPLACEMENT**
- Timeframe: **15m**
- Displacement: body > 1.5× 20-bar avg body; close in top/bottom 20%
- Entry: **BOS_RETEST** (phase29.simulator.resolve_entry literal)
- Stop: 0.75 ATR · Target: 3.0R · Hold: 60m (4 bars) · FIXED

## BOS_RETEST Rules (from phase29.simulator)
- BOS bar = displacement bar; `bos_level` = bar high (long) or bar low (short)
- Tolerance = 0.10 × ATR(14) on displacement bar
- Window = 2 bars strictly after displacement close
- Long fill when `low <= bos_level + tol`; price = min(bos_level + tol, close)
- Short fill when `high >= bos_level - tol`; price = max(bos_level - tol, close)
- Stop ATR measured at entry bar; ambiguous bar: **STOP before TARGET**

## Population Distinction
- **Stitched WF (Phase 31 headline):** N=2873, trades/day≈1.222
- **Full frozen parity (this Pine reference):** N=3801, Net AvgR=0.2254R

## Dry-Stretch Audit
- Phase 31 reported: **515** RTH days
- Correct (full frozen fills): **2** RTH days
- Correct (WF eligible 2020+): **2** RTH days
- Cause: Phase 31 daily_distribution counted stitched WF fills (2020-2026 test folds only) against the full 2018-2026 RTH calendar. The ~515-day stretch is almost entirely the 2018-2019 pre-test period with zero WF trades, not a strategy dry spell.

## TradingView Notes
Python uses stitched local NQ 5m→15m data. TradingView NQ1! may differ on rolls,
back-adjustment, and session boundaries. Logic parity first — do not retune to match TV data.

## Files
- MOMENTUM_DISPLACEMENT_15M_FINAL_STRATEGY.pine
- MOMENTUM_DISPLACEMENT_15M_FINAL_INDICATOR.pine
- pine_parity_reference.csv
- parity_windows.csv