# Concurrent Pine Patch Report (Phase 38)

## Summary
Patched the combined NQ 15m Pine reversal engine from **single global tracker** to **concurrent candidate pool** (capacity 8), matching validated Phase 37 architecture.

Phase 31 continuation logic is **unchanged**.

## Continuation Parity
| Metric | Expected | Reference |
|--------|----------|-----------|
| L | 2075 | 2075 |
| S | 1836 | 1836 |
| Status | PASS | |

## Reversal Parity (vs Phase 37 pine_reference_map.csv)
| Metric | Expected | Reference |
|--------|----------|-----------|
| RL | 976 | 976 |
| RS | 925 | 925 |
| Restored vs Phase 36 single | ~684 | 684 |
| Status | PASS | |

## Pine-Equivalent Simulator
Python concurrent replay (Phase 37 engine) match rate vs reference: **100.00%**

## Key Architectural Fixes
1. **Multiple concurrent candidates** — each displacement owns independent A_MID_4 + RECLAIM_RETEST lifecycle
2. **Reclaim direction uses displacement direction** (`midpointReclaimed(dispDir, mid)`)
3. **Dedupe at reclaim bar** — not at displacement creation
4. **Same-bar display** — at most one RL and one RS per bar

## Files
- `NQ_15M_COMBINED_INDICATOR_CONCURRENT.pine`
- `NQ_15M_COMBINED_STRATEGY_CONCURRENT.pine`
- `pine_parity.csv` / `parity_windows.csv`

## TradingView Validation
Paste indicator into NQ 15m (America/Chicago) and verify rows in `parity_windows.csv`.
Original Phase 34 Pine files were **not** modified.

## Audit
Lookahead: PASS | Deterministic: PASS | Conflict policy: INDEPENDENT
