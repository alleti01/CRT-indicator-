# CDX model training report

Trained 2026-10-20 17:06 UTC on 151 signals (48 CDX). Walk-forward tested on 9 CDX days, 48 signals.

## Decision: **KEEP_RULE**

The model is promoted only when its walk-forward total R beats the best fixed rule on the same days.

## Walk-forward results (each day tested on a model that never saw it)

| Policy | Trades | Win rate | Avg R | Total R | Green / red days | Worst day R |
|---|---|---|---|---|---|---|
| model | 21 / 48 | 38% | -0.16 | -3.29 | 3 / 3 | -3.16 |
| take_all_fixed14_2R | 48 / 48 | 40% | +0.12 | +5.63 | 6 / 3 | -4.91 |
| 15m_agrees_atr1.5_2R | 20 / 48 | 70% | +0.99 | +19.71 | 8 / 1 | -2.07 |

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
| 2026-10-02 | 4 | 147 | 3 | -3.16 | -2.07 | -1.28 |

## Options the model chose when it traded

- `atr2_t1`: 4
- `atr2_t2`: 3
- `atr2_t3`: 3
- `struct10_t1`: 2
- `fixed14_t2`: 2
- `struct10_t3`: 1
- `atr1_t1`: 1
- `fixed14_t1`: 1
- `atr1_t2`: 1
- `struct5_t1`: 1
- `struct5_t3`: 1
- `atr1.5_t3`: 1

## What moves the model's prediction most (final model, in-sample)

1. `room_day_atr` (0.180 R)
2. `overlap20` (0.168 R)
3. `ret15_atr` (0.161 R)
4. `ret60_atr` (0.154 R)
5. `atr_ratio` (0.153 R)
6. `atr3` (0.146 R)
7. `hour_et` (0.126 R)
8. `pos20` (0.097 R)
9. `eff20` (0.094 R)
10. `mins_since_prev` (0.090 R)

## Limits

- Very small sample. With under ~300 CDX signals, a model beating the rule on a few days can be luck; treat a PROMOTE as a reason to shadow it, not to trade it.
- Results are per signal and ignore the one-position-at-a-time and daily-limit rules.
- Signals minutes apart share a price path, so per-signal results overstate independence.
