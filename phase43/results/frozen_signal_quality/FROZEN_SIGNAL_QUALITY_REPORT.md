# Frozen Signal Quality Report

## Phase 40 parity
PASS — N=3791

## Baseline OOS
{
  "N": 2788,
  "WinRate": 0.5064562410329986,
  "AvgR": 0.3499974318258542,
  "TotalR": 975.7928399304815,
  "PF": 1.7882353286265988,
  "MaxDD": 17.42566144228806,
  "ReturnMaxDD": 55.997463462847804
}

## Monotonicity
{
  "classification": "STRONG_MONOTONIC",
  "spearman": 0.8787878787878788,
  "adjacent_improvements": 8,
  "decile_AvgR": [
    0.13249543097361113,
    -0.0621219049016516,
    -0.013962472158931124,
    0.019756360998088033,
    0.059344915516448375,
    0.3221996827233738,
    0.3476385699789405,
    0.4496326701719813,
    0.8348429453478622,
    1.408956005154788
  ]
}

## Best filter
{
  "reject_rate": 0.3999999999999999,
  "signals_removed": 1115,
  "retained_AvgR": 0.5848936616575857,
  "retained_PF": 2.5115594968604755,
  "rejected_AvgR": -0.0024522475539547,
  "rejected_PF": 0.995370246344373,
  "bad_signal_rejection_precision": 0.579372197309417,
  "good_signal_retention_rate": 0.6678470254957507
}

## Classification
**A** | Entry filter: YES | Confidence display: YES
