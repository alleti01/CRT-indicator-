# Phase 45 — 15m Context + 1m Execution Study

## Phase 44 Parity (full accepted population): PASS — see phase44_parity.csv (N=2275, AvgR=0.568, PF=2.43)

## OOS control uses common 1m simulator at Phase44 entry (A_sim); Phase44 reference 15m outcomes preserved for parity.

## Best 1m Price Rule (full-sample diagnostic): B3 / 5 min
Walk-forward TEST uses train-selected rule per fold (see parameter_stability.csv).

## Models (stitched walk-forward TEST)
| Model | N | AvgR | PF | MaxDD | Fill |
|-------|---|------|----|-------|------|
| A 15m Phase44 (1m sim) | 1759 | 0.855 | 2.81 | 13.19 | 100% |
| B 15m+1m price | 1135 | 1.648 | 17.78 | 8.39 | 64.5% |
| C + volume | 466 | 1.561 | 14.95 | 4.21 | 26.5% |

## Incremental Value
- B − A: AvgR +0.793, PF +14.97, MAE +7.420, WD -0.3 pp
- C − B: AvgR -0.087, PF -2.82

## Unfilled Phase44 signals
N=624, original AvgR=-0.025

## Success Gates
{
  "N_filled_ge_500": true,
  "fill_rate_ge_50pct": true,
  "matched_avgr_delta_ge_0.10": true,
  "pf_improvement_ge_0.15": true,
  "mae_reduction_ge_10pct": true,
  "wrong_direction_reduced": true,
  "y2024_positive": true,
  "y2025_positive": true,
  "y2026_positive": true,
  "cost_1.5x_positive": true,
  "cost_2.0x_positive": true,
  "ex_top1pct_positive": true,
  "execution_improves_all_gates": true,
  "volume_useful": false,
  "matched_avgr_delta": 0.6050148024011666,
  "mae_reduction_pct": 97.51476635852666
}

## 1m execution improves Phase44: YES
## Volume adds edge: NO
