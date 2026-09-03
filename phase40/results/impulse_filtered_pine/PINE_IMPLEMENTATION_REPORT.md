# Phase 40 — Impulse-Filtered Pine Implementation

## Unfiltered parity (Phase 37)
{'L': 2075, 'S': 1836, 'RL': 976, 'RS': 925, 'total': 5812}

## Filter
- `impulse_3bar = abs(close - close[3]) / ATR(14)`
- Threshold: **0.65**
- Full-history retention: **65.2%**
- OOS stitched retention: **65.3%**

## Full-history economics (net costs)
| | N | AvgR | PF |
|---|---:|---:|---:|
| Unfiltered | 5812 | +0.229 | 1.48 |
| Filtered | 3791 | +0.341 | 1.75 |

## OOS stitched economics (net costs)
| | N | AvgR | PF |
|---|---:|---:|---:|
| Unfiltered | 4271 | +0.242 | 1.52 |
| Filtered | 2788 | +0.350 | 1.79 |

## Phase 39 reproduction
{
  "full_history_filtered_N": 3791,
  "full_history_retention": 0.6522711631108052,
  "phase39_full_target_N": 3791,
  "phase39_full_target_retention": 0.6522711631108052,
  "full_N_within_2pct": true,
  "full_retention_within_2pct": true,
  "oos_filtered_N": 2788,
  "oos_retention": 0.6527745258721611,
  "phase39_oos_target_N": 2773,
  "phase39_oos_target_retention": 0.6499648794193398,
  "oos_N_within_2pct": true,
  "oos_retention_within_2pct": true,
  "reproduced": true
}

## Lookahead audit
**PASS** — impulse uses close, close[3], and ATR(14) at entry bar only.

## Pine deliverables
- `NQ15_COMBINED_PHASE40.pine`
- `NQ15_COMBINED_PHASE40_STRATEGY.pine`

## Next step
Load indicator on NQ 15m and validate accepted/rejected markers against `pine_reference_map.csv` / `rejected_signal_map.csv`.
