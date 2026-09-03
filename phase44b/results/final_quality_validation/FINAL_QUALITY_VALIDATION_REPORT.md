# Phase 44B Final Quality Validation Report

## Phase 40 Parity: PASS

## Feature Parity: PASS

Phase 43 ret_n_atr = pct_change(n) * direction = ((close/close[n])-1)*direction

## Walk-Forward OOS (stitched TEST)

| Metric | Baseline | Filtered |
|--------|----------|----------|
| N | 2788 | 1750 |
| Retention | — | 62.8% |
| AvgR | 0.350 | 0.566 |
| PF | 1.79 | 2.44 |
| MaxDD | 17.43 | 15.32 |

## Rejected Population

N=1038, AvgR=-0.015, PF=0.97, wrong-direction=30.3%

## Quality Monotonicity

A: STRONG_MONOTONIC (Spearman=0.976)

## Fixed Phase 44 Rule (full-history constants — reference only)

N=2275, AvgR=0.568, PF=2.43

Constants: q05=-0.00496580294121185, q95 span=0.025571, threshold=36.49346328963349

## Threshold Stability

metric  train_threshold  train_q05  train_q95
   min        34.257986  -0.005136   0.017477
   max        37.064733  -0.003498   0.021542
median        36.030261  -0.004467   0.020605
   std         1.015564   0.000581   0.001463

## Bootstrap AvgR Improvement 95% CI

[0.1277, 0.3027] — excludes zero: YES

## Confidence Tier Validation: YES

## Success Gates: 15 / 15

## Decision

EXACT PINE SIMPLE SCORE VALIDATED: YES
FREEZE PHASE44: YES
Classification: A
