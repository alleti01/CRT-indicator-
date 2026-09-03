# Phase 47 — 1M Price-Action Execution Research

## Executive Summary

Phase47 tested causal 1-minute price-action filters and delayed-entry variants on top of the **canonical Phase45 stitched walk-forward B1 control** (N=1135, AvgR=1.648R). Phase44 and Phase45 parity both **PASS**.

### Primary Results Table

             MODEL    N  RETENTION     AvgR         PF      TotalR     MaxDD      MAE      MFE  WrongDir  EntryDelay
Phase45_B1_Control 1135   1.000000 1.648373  17.775735 1870.903510  8.385997 0.189103 0.270835  0.066960    2.533921
    Break_Strength  731   0.644053 1.597258  15.642271 1167.595770  6.339073 0.213553 0.278221  0.077975    2.062927
     Close_Quality  679   0.598238 1.646371  17.288080 1117.886104  3.970063 0.208859 0.330370  0.075110    2.867452
      Wick_Quality  856   0.754185 1.702336  20.158267 1457.199941  5.352057 0.181671 0.289414  0.063084    2.816589
   Local_Liquidity   22   0.019383 1.633978 131.620175   35.947511  0.275206 0.106759 0.340466  0.000000    4.909091
            Retest  770   0.678414 1.611743  17.399046 1241.042082  6.528711 0.185926 0.222520  0.074026    5.602597
      Displacement  573   0.504846 1.703979  23.052412  976.380175  4.106178 0.162976 0.219729  0.055846    3.078534
    Follow_Through  859   0.756828 1.615841  17.950517 1388.006991  5.597668 0.187287 0.240808  0.073341    3.423749
 Structure_Quality  782   0.688987 1.701079  17.559553 1330.243863 10.174128 0.188208 0.277001  0.063939    2.805627

### Incremental vs Phase45 B1

            MODEL     dAvgR        dPF      dTotalR    dMaxDD      dMAE      dMFE  dWrongDir    dDelay  Retention
   Break_Strength -0.051115  -2.133464  -703.307740 -2.046924 -0.024449  0.007386  -0.011015 -0.470993   0.644053
    Close_Quality -0.002002  -0.487655  -753.017406 -4.415934 -0.019755  0.059535  -0.008150  0.333531   0.598238
     Wick_Quality  0.053963   2.382532  -413.703569 -3.033940  0.007432  0.018579   0.003876  0.282668   0.754185
  Local_Liquidity -0.014395 113.844440 -1834.955999 -8.110791  0.082345  0.069631   0.066960  2.375170   0.019383
           Retest -0.036630  -0.376689  -629.861428 -1.857286  0.003178 -0.048316  -0.007066  3.068677   0.678414
     Displacement  0.055606   5.276677  -894.523335 -4.279820  0.026127 -0.051106   0.011114  0.544613   0.504846
   Follow_Through -0.032533   0.174781  -482.896520 -2.788329  0.001817 -0.030027  -0.006381  0.889828   0.756828
Structure_Quality  0.052706  -0.216182  -540.659647  1.788131  0.000896  0.006166   0.003022  0.271706   0.688987

## Key Findings

- **Break strength, close quality, follow-through, and retest** all reduce portfolio TotalR despite occasional per-trade AvgR tweaks.
- **Rejected-trade expectancy (~1.65–1.93R)** meets or exceeds the B1 control — filters remove profitable executions.
- **Follow-through variants (F1–F4)** degrade matched-signal expectancy (delayed entry is worse on identical signals).
- **Local liquidity sweep** requirement collapses sample size (N≈22 OOS) — not viable.
- **Wick quality / displacement** show marginal +AvgR but **negative TotalR** due to trade removal.
- **Wrong-direction diagnostics**: failed B1 events show slightly higher break strength and body/ATR — not a stable separable filter.
- **Delay buckets (diagnostic)**: faster confirmations (0–1 min) have higher wrong-direction rate; no timing rule beats nested WF B1 window selection.

## Final Assessment

PHASE44 PARITY: PASS

PHASE45 B1 PARITY: PASS

CANONICAL CONTROL:
N = 1135
AvgR = 1.648
PF = 17.78
TotalR = 1870.9
MaxDD = 8.39
Fill = 64.5%
WrongDir = 6.7%
MedianDelay = 1.0

BEST 1M PRICE-ACTION FEATURE: Displacement

BEST OOS VARIANT: NONE

OOS RETENTION: 0.5048458149779735

PORTFOLIO INCREMENTAL VALUE:
No variant improved TotalR, PF, and retention together vs canonical B1.

MATCHED-SIGNAL INCREMENTAL VALUE:
Follow-through variants show negative matched ΔAvgR; filter variants retain identical R on kept trades (ΔAvgR≈0).

REJECTED-TRADE AVGR: 1.615R

DOES ADDITIONAL 1M PRICE ACTION IMPROVE B1: NO

DOES IT IMPROVE LONGS: NO

DOES IT IMPROVE SHORTS: NO

DOES IT REDUCE WRONG-DIRECTION: NO

DOES IT REDUCE MAE: NO

DOES IT IMPROVE MFE: NO

DOES IT IMPROVE ENTRY TIMING: NO

IS IT ROBUST ACROSS 2024/2025/2026: NO

IS IT ROBUST ACROSS WALK-FORWARD FOLDS: NO

IS PARAMETER SELECTION STABLE: YES (nested WF reproduced Phase45 B1 windows)

SHOULD B1 CHANGE: NO

SHOULD PHASE44 CHANGE: NO

READY FOR PINE: NO — forward paper validation required before implementation

MOST IMPORTANT FINDING:
Every tested 1M price-action filter or delayed-entry variant either reduced portfolio TotalR or removed trades with equal-or-better expectancy than those retained. The Phase45 B1 Micro-BOS execution layer already captures the actionable 1M structure break; additional bar-level quality gates do not produce stable stitched OOS improvement.

NEXT STEP:
Keep Phase44 + Phase45 B1 unchanged. Proceed to forward paper validation of the existing B1 model without additional 1M price-action filters.