# Concurrent Reversal Parity Report

## Phase 31 L/S Parity
- Match: 3911 / 3911 (100.00%)

## Reversal Counts
| Implementation | RL | RS | Total |
|----------------|---:|---:|------:|
| Original Phase 33 batch | 976 | 925 | 1901 |
| Phase 36 single tracker | 677 | 622 | 1299 |
| Phase 37 concurrent | 976 | 925 | 1901 |

## Parity vs Phase 33 Batch
- Match rate: 100.00%
- RL matched: 976
- RS matched: 925
- Missing: 0
- Extra: 0

## Dedupe Semantics (documented)
Phase 33 batch applies `dedupe_signals()` at **reclaim (confirm) bar**, not displacement bar.
Duplicate key: `failure_event_id` = `A_MID_4_{displacement_timestamp}_{reversal_direction}`.
One active trade window (6 bars), 4-bar same-direction spacing, max 2/RTH day.

## Restored Signals (concurrent only)
- N: 684
- AvgR: +0.289R
- PF: 1.76

## Phase 37 Performance
- N: 1901, AvgR: +0.240R, PF: 1.59

## Concurrency
[{'max_concurrent': 5, 'median_concurrent': 1.0, 'p99_concurrent': 3.0, 'mean_concurrent': 1.1434225601499843}]

## Audit
Lookahead: PASS | Deterministic: PASS
