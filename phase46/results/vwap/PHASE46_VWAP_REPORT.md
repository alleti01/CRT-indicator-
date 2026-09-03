# Phase 46 — VWAP Research on Phase44 + B1

## Phase45 Parity
- Phase44 full population: PASS (N=2275, AvgR=0.568, PF=2.43)
- B0 control: B1 @ 10 min — N=1212, AvgR=1.639, PF=17.10, fill=68.9%

## Required Output Table
See variant_results.csv and incremental_vs_b0.csv.

## Final Assessment

PHASE45 PARITY: PASS

BEST VWAP VARIANT: NONE

VWAP INCREMENTAL VALUE: All variants negative OOS vs B0 (best V1 dAvgR -0.078)

DOES VWAP IMPROVE PHASE44 + B1: NO

DOES VWAP IMPROVE LONGS: NO

DOES VWAP IMPROVE SHORTS: NO

DOES VWAP REDUCE MAE: NO (filters increase MAE)

DOES VWAP REDUCE WRONG-DIRECTION: NO (wrong-direction rate increases)

IS VWAP ROBUST OOS: NO

SHOULD VWAP BE ADDED TO THE EXECUTION LAYER: NO

SHOULD PHASE44 SIGNAL LOGIC CHANGE: NO

READY FOR PINE: NO

MOST IMPORTANT FINDING:
Every VWAP filter variant degraded stitched walk-forward expectancy versus B0 (Phase44 + B1). Rejected B1 trades averaged higher R than retained trades (e.g. V1 rejected AvgR 1.69 vs B0 1.64), meaning VWAP removed profitable executions rather than bad ones. Most B1 fills occur >2 ATR from session VWAP on NQ, so side-alignment and distance caps systematically skip the working population.

NEXT STEP:
Continue forward paper validation of Phase44 + B1 only. Do not add VWAP to the execution layer.
