# Phase80 — Universal Causal Confluence Search

**VERDICT:** `PHASE80_VALIDATION_FAIL`

**RESEARCH ENTRY STREAM:** `PHASE60`

**PHASE72A_HISTORICAL_PARITY_NOT_ESTABLISHED** — Phase72A Pine is production signal authority; Phase60 is historical causal research anchor.

**Pine SHA256:** `d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f`
**Signal hash:** `0da41f282174679f`

## BASELINE (M0 frozen, net R)
- N: 36,174
- AvgR: 0.015992
- PF: 1.023
- TotalR: 578.5
- MaxDD: 170.2

**ELIGIBLE COMPONENTS:** 19 singles (entry-time Phase60 fields)
**EXCLUDED COMPONENTS:** see EXCLUDED_COMPONENTS.csv
**TOTAL HYPOTHESES TESTED:** 1,272

## BEST TRAIN
- Single: SINGLE_F_M5_DIRECTION_ALIGN ΔAvgR=0.0266
- Pair: PAIR_AND_F_M5_DIRECTION_ALIGN_F_MARKET_REVERSAL ΔAvgR=0.1728
- Triple: TRIPLE_AND_F_REACTION_SCORE_F_ALIGNED_ACTIVE_F_MARKET_REVERSAL ΔAvgR=1.3260
- Score: SCORE_GE_1 ΔAvgR=0.0000

## VALIDATION
- Survivors (ΔAvgR>0, N≥200): **0**
- Best validation ΔAvgR: **0.1214**

## Multiple-hypothesis warning
Tested 1,272 combinations on train; train-best is NOT trustworthy without validation. Validation survivors: 0.

## M0 (frozen)
STOP=1.0R, TARGET=2.5R, MAX_HOLD=60m, STOP_FIRST, cost=$14.50 RT

Completed in 32.1s
