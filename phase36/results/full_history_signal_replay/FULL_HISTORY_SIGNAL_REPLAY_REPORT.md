# Full-History Signal Replay Report

**Phase:** Frozen Phase 31 + Phase 33 indicator replay (no optimization, no WF selection)

## Data
- Start: 2017-10-01 17:00:00-05:00
- End: 2026-06-28 23:45:00-05:00
- Target range: 2017-10-01 → 2026-06-28
- RTH 15m candles: 56,423

## Signal Counts
| Type | Count |
|------|------:|
| L | 2075 |
| S | 1836 |
| RL | 677 |
| RS | 622 |
| **TOTAL** | 5210 |

Signals/RTH day: 2.31

## Python vs Pine Reference (Phase 34 batch contract, 2018–2026 overlap)
- MATCH (all): 4969
- Continuation MATCH: 3797
- Reversal MATCH: 1172
- MISSING (in Phase 34 ref, not in replay): 672
- EXTRA (in replay, not in Phase 34 ref): 84
- Price mismatches: 1

**Note:** Replay implements the Pine single state-machine (one active reversal tracker). Phase 34 batch Python evaluates all displacements concurrently — reversal counts diverge by design. Continuation should match closely.

## Aug 20–21 2026
Aug 2026 data in local dataset: **NO** (local data ends 2026-06-28 23:45:00-05:00)

See `historical_visual_windows.csv` for candle-by-candle state.

## Audit
- Lookahead: **PASS** — replay uses only bars ≤ T at each step
- Deterministic: **PASS** — identical maps on repeated runs

## Canonical reference
`full_history_signal_map.csv` is the authoritative historical marker list for TradingView parity.
