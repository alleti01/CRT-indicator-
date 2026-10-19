# CDX model training report

Trained 2026-10-19 18:38 UTC on 195 signals (92 CDX). Walk-forward tested on 9 CDX days, 92 signals.

## Decision: **KEEP_RULE**

The model is promoted only when its walk-forward total R beats the best fixed rule on the same days.

## Walk-forward results (each day tested on a model that never saw it)

| Policy | Trades | Win rate | Avg R | Total R | Green / red days | Worst day R |
|---|---|---|---|---|---|---|
| model | 33 / 92 | 45% | -0.04 | -1.19 | 4 / 3 | -2.39 |
| take_all_fixed14_2R | 92 / 92 | 22% | -0.42 | -38.46 | 3 / 6 | -34.44 |
| 15m_agrees_atr1.5_2R | 19 / 92 | 74% | +1.09 | +20.75 | 8 / 1 | -2.07 |

## By day

| Day | Signals | Train rows | Model trades | Model R | 15m rule R | Take-all R |
|---|---|---|---|---|---|---|
| 2026-09-22 | 4 | 103 | 4 | -1.10 | +1.95 | -1.28 |
| 2026-09-23 | 9 | 104 | 5 | +0.74 | +1.93 | +2.37 |
| 2026-09-24 | 13 | 115 | 7 | -2.28 | +1.86 | -4.91 |
| 2026-09-25 | 2 | 128 | 0 | +0.00 | +0.38 | -2.14 |
| 2026-09-28 | 49 | 131 | 11 | -2.39 | +7.89 | -34.44 |
| 2026-09-29 | 2 | 180 | 1 | +0.29 | +1.97 | +0.86 |
| 2026-09-30 | 3 | 182 | 0 | +0.00 | +5.91 | +2.79 |
| 2026-10-01 | 6 | 184 | 1 | +0.64 | +0.93 | -0.42 |
| 2026-10-02 | 4 | 191 | 4 | +2.90 | -2.07 | -1.28 |

## Options the model chose when it traded

- `struct10_t1`: 7
- `atr1.5_t1`: 6
- `struct5_t1`: 5
- `atr2_t1`: 4
- `struct5_t2`: 3
- `struct5_t3`: 3
- `struct10_t3`: 1
- `fixed14_t1`: 1
- `atr1.5_t2`: 1
- `fixed14_t2`: 1
- `struct10_t2`: 1

## What moves the model's prediction most (final model, in-sample)

1. `atr3` (0.283 R)
2. `ret60_atr` (0.199 R)
3. `room_day_atr` (0.158 R)
4. `hour_et` (0.129 R)
5. `eff20` (0.122 R)
6. `ret15_atr` (0.117 R)
7. `atr_ratio` (0.114 R)
8. `pos20` (0.111 R)
9. `range20_atr` (0.096 R)
10. `is_cdx` (0.070 R)

## Limits

- Very small sample. With under ~300 CDX signals, a model beating the rule on a few days can be luck; treat a PROMOTE as a reason to shadow it, not to trade it.
- Results are per signal and ignore the one-position-at-a-time and daily-limit rules.
- Signals minutes apart share a price path, so per-signal results overstate independence.
