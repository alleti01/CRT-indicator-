# Combined Pine Implementation Report

## Architecture
- **Phase 31:** MOMENTUM_DISPLACEMENT continuation — BOS_RETEST, 0.75 ATR stop, 3R target, 60m hold
- **Phase 33:** DISPLACEMENT_FAILURE_REVERSAL — A_MID_4, RECLAIM_RETEST, 0.75 ATR stop, 2.5R target, 45m hold
- **Conflict policy:** INDEPENDENT

## Python reference counts (full history)
- Phase 31 fills: 3,801
- Phase 33 fills: 1,841
- Combined: 5,642

## Research benchmarks (WF OOS — not Pine targets)
| System | N | Trades/day | AvgR | PF |
|--------|---:|---:|---:|---:|
| Phase 31 | 2873 | 1.22 | +0.233R | 1.47 |
| Phase 33 | 1031 | 0.44 | +0.185R | 1.46 |
| Combined | — | 1.78 | +0.22R | 1.47 |

## Files
- `NQ_15M_COMBINED_INDICATOR.pine` — primary chart indicator (tiny L/S/RL/RS markers)
- `NQ_15M_COMBINED_STRATEGY.pine` — Strategy Tester parity
- `combined_parity_reference.csv` — Python deterministic reference
- `parity_windows.csv` — manual TV validation samples

## Ready for live trading
**NO** — visual parity validation required first.

## Phase 34B visualization patch (Aug 2026)
- Entry markers: bar-anchored `belowbar`/`abovebar` only; one-shot on fill bar
- Trade lines: explicit `xloc.bar_index` + `yloc.price`; guarded against na/invalid levels
- Historical lines: archived to capped arrays; active lines deleted before reuse
- No scale-polluting overlay plots (diagnostic plots use `na` when inactive)
- **Show Placement Debug** (default OFF): bar_index + entry price label + entry price dot
- Trading logic unchanged — Python signal count remains 5,642
