# Phase 44 Pine Quality Implementation

## Simple score (frozen causal proxy)
Features: ['ret_1_atr', 'ret_2_atr', 'ret_3_atr']
ret_n_atr: `((close/close[n])-1)*direction`
simple_raw: `ret_1_atr + ret_2_atr + ret_3_atr`
normalization: `clip((simple_raw - -0.00496580294121185) / (0.02060542475082916 - -0.00496580294121185) * 100, 0, 100)`

## Threshold
Quality pass: score >= **36.49346328963349**

## Confidence tiers
{
  "A+": 63.198239617422814,
  "A": 46.076841180646284,
  "B": 36.49346328963349,
  "Rejected": "< 36.49346328963349"
}

## Population
Phase 40: 3791
Phase 44 accepted: 2275
Phase 44 rejected: 1516
Retention: 60.0%

## Full-history fixed rule
{
  "N": 2275,
  "WinRate": 0.5617582417582417,
  "AvgR": 0.5683200798575244,
  "TotalR": 1292.928181675868,
  "PF": 2.430042753194928,
  "MaxDD": 15.563767849085934,
  "ReturnMaxDD": 83.07295471204309
}

## Phase 43 stitched evidence (reference)
{
  "N": 2788,
  "baseline_AvgR": 0.3499974318258542,
  "baseline_PF": 1.7882353286265988,
  "filtered_N": 1673,
  "filtered_AvgR": 0.5848936616575857,
  "filtered_PF": 2.5115594968604755
}
