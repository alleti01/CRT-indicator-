# CDX model training report

Trained 2026-10-21 18:49 UTC on 201 signals (98 CDX). Walk-forward tested on 19 CDX days, 98 signals.

## Decision: **KEEP_RULE**

The model is promoted only when its walk-forward total R beats the best fixed rule on the same days.

## Walk-forward results (each day tested on a model that never saw it)

| Policy | Trades | Win rate | Avg R | Total R | Green / red days | Worst day R |
|---|---|---|---|---|---|---|
| model | 49 / 98 | 35% | -0.24 | -11.79 | 7 / 8 | -4.21 |
| take_all_fixed14_2R | 98 / 98 | 34% | -0.06 | -5.88 | 8 / 11 | -4.91 |
| 15m_agrees_atr1.5_2R | 40 / 98 | 57% | +0.59 | +23.57 | 14 / 4 | -3.13 |

## By day

| Day | Signals | Train rows | Model trades | Model R | 15m rule R | Take-all R |
|---|---|---|---|---|---|---|
| 2026-09-22 | 4 | 103 | 4 | -2.12 | +1.94 | -1.28 |
| 2026-09-23 | 9 | 104 | 5 | +0.97 | +1.93 | +5.37 |
| 2026-09-24 | 13 | 115 | 5 | -2.30 | +1.85 | -4.91 |
| 2026-09-25 | 2 | 128 | 0 | +0.00 | +0.38 | +0.86 |
| 2026-09-28 | 5 | 131 | 2 | +2.97 | +7.89 | +0.65 |
| 2026-09-29 | 2 | 136 | 0 | +0.00 | +0.95 | +0.86 |
| 2026-09-30 | 3 | 138 | 0 | +0.00 | +5.90 | +2.79 |
| 2026-10-01 | 6 | 140 | 2 | +0.35 | +0.93 | +2.58 |
| 2026-10-02 | 5 | 147 | 4 | -4.18 | -2.07 | -2.35 |
| 2026-10-05 | 4 | 152 | 3 | +0.79 | -2.06 | -1.28 |
| 2026-10-06 | 5 | 156 | 5 | +1.51 | +0.89 | +3.65 |
| 2026-10-07 | 1 | 161 | 1 | +1.23 | +1.23 | -1.07 |
| 2026-10-08 | 6 | 162 | 4 | -2.16 | +0.00 | -3.42 |
| 2026-10-09 | 5 | 167 | 2 | -0.32 | -3.13 | -2.35 |
| 2026-10-12 | 4 | 173 | 4 | -4.21 | +0.90 | -1.28 |
| 2026-10-13 | 9 | 176 | 4 | -4.16 | +0.92 | -0.63 |
| 2026-10-14 | 2 | 185 | 0 | +0.00 | +3.92 | +0.86 |
| 2026-10-20 | 7 | 188 | 3 | -1.08 | -2.74 | -4.49 |
| 2026-10-21 | 6 | 194 | 1 | +0.93 | +3.93 | -0.42 |

## Options the model chose when it traded

- `fixed14_t1`: 5
- `atr2_t1`: 5
- `fixed14_t2`: 5
- `atr2_t2`: 4
- `struct5_t1`: 4
- `atr2_t3`: 4
- `atr1_t1`: 3
- `struct10_t1`: 3
- `struct5_t2`: 3
- `struct5_t3`: 2
- `fixed14_t3`: 2
- `atr1_t3`: 2
- `atr1.5_t1`: 2
- `struct10_t3`: 1
- `atr1_t2`: 1
- `atr1.5_t3`: 1
- `atr1.5_t2`: 1
- `struct10_t2`: 1

## What moves the model's prediction most (final model, in-sample)

1. `room_day_atr` (0.187 R)
2. `atr3` (0.175 R)
3. `ret15_atr` (0.150 R)
4. `ret60_atr` (0.148 R)
5. `overlap20` (0.141 R)
6. `hour_et` (0.124 R)
7. `pos20` (0.111 R)
8. `atr_ratio` (0.087 R)
9. `mins_since_prev` (0.081 R)
10. `eff20` (0.072 R)

## Limits

- Very small sample. With under ~300 CDX signals, a model beating the rule on a few days can be luck; treat a PROMOTE as a reason to shadow it, not to trade it.
- Results are per signal and ignore the one-position-at-a-time and daily-limit rules.
- Signals minutes apart share a price path, so per-signal results overstate independence.
