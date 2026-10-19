# CDX model training report

Trained 2026-10-19 20:23 UTC on 151 signals (48 CDX). Walk-forward tested on 9 CDX days, 48 signals.

## Decision: **KEEP_RULE**

The model is promoted only when its walk-forward total R beats the best fixed rule on the same days.

## Walk-forward results (each day tested on a model that never saw it)

| Policy | Trades | Win rate | Avg R | Total R | Green / red days | Worst day R |
|---|---|---|---|---|---|---|
| model | 23 / 48 | 52% | +0.09 | +2.07 | 5 / 2 | -2.28 |
| take_all_fixed14_2R | 48 / 48 | 31% | -0.13 | -6.37 | 3 / 6 | -4.91 |
| 15m_agrees_atr1.5_2R | 19 / 48 | 74% | +1.09 | +20.75 | 8 / 1 | -2.07 |

## By day

| Day | Signals | Train rows | Model trades | Model R | 15m rule R | Take-all R |
|---|---|---|---|---|---|---|
| 2026-09-22 | 4 | 103 | 4 | -1.10 | +1.95 | -1.28 |
| 2026-09-23 | 9 | 104 | 5 | +0.74 | +1.93 | +2.37 |
| 2026-09-24 | 13 | 115 | 7 | -2.28 | +1.86 | -4.91 |
| 2026-09-25 | 2 | 128 | 0 | +0.00 | +0.38 | -2.14 |
| 2026-09-28 | 5 | 131 | 2 | +2.97 | +7.89 | -2.35 |
| 2026-09-29 | 2 | 136 | 1 | +0.29 | +1.97 | +0.86 |
| 2026-09-30 | 3 | 138 | 0 | +0.00 | +5.91 | +2.79 |
| 2026-10-01 | 6 | 140 | 1 | +0.64 | +0.93 | -0.42 |
| 2026-10-02 | 4 | 147 | 3 | +0.79 | -2.07 | -1.28 |

## Options the model chose when it traded

- `struct10_t1`: 7
- `struct5_t3`: 4
- `struct5_t1`: 3
- `atr2_t1`: 3
- `struct5_t2`: 2
- `struct10_t3`: 2
- `fixed14_t1`: 1
- `atr1.5_t2`: 1

## What moves the model's prediction most (final model, in-sample)

1. `atr3` (0.226 R)
2. `ret60_atr` (0.196 R)
3. `eff20` (0.182 R)
4. `ret15_atr` (0.144 R)
5. `atr_ratio` (0.141 R)
6. `range20_atr` (0.139 R)
7. `pos20` (0.134 R)
8. `hour_et` (0.121 R)
9. `room_day_atr` (0.104 R)
10. `opt_stop_atr` (0.084 R)

## Limits

- Very small sample. With under ~300 CDX signals, a model beating the rule on a few days can be luck; treat a PROMOTE as a reason to shadow it, not to trade it.
- Results are per signal and ignore the one-position-at-a-time and daily-limit rules.
- Signals minutes apart share a price path, so per-signal results overstate independence.
