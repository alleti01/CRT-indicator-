# Phase82 — Causal 15M Context → 1M Execution

**Verdict:** `PHASE82_VALIDATION_FAIL`

## INTEGRITY
PHASE82_MODE = RESEARCH_ONLY
PRODUCTION_MODIFIED = NO
PHASE72A_MODIFIED = NO
PHASE73_MODIFIED = NO
PHASE74_MODIFIED = NO
M0_MODIFIED = NO
USES_5M = NO

Pine SHA256: `d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f`
PHASE72A_HISTORICAL_PARITY = NOT ESTABLISHED
RESEARCH_ENTRY_STREAM = PHASE60
EXPECTED_STREAM_HASH = 0da41f282174679f

## CAUSALITY
- Prefix test sampled: 500
- Failures: 0

## BASELINE
- P0 N=36174 AvgR=0.01599

## TOP MODELS
- P4: N=1058 ret=2.9% AvgR=0.1474 val=0.0000 test=0.0000 recovered=0
- P7: N=34007 ret=94.0% AvgR=0.0276 val=0.0570 test=0.0158 recovered=32810
- P8: N=34006 ret=94.0% AvgR=0.0276 val=0.0570 test=0.0160 recovered=32810
- P9: N=34006 ret=94.0% AvgR=0.0276 val=0.0570 test=0.0160 recovered=32810
- P5: N=33868 ret=93.6% AvgR=0.0272 val=0.0570 test=0.0203 recovered=32810

## ANTI-CHASE (P4 hard pass vs P5 wait-reset)
- P4: N=1058 AvgR=0.1474
- P5: N=33868 AvgR=0.0272 recovered=32810

## RANDOM DIRECTION
- Real P5 AvgR: 0.02721
- Random mean AvgR: -0.00396

## ANSWERS
1. Does causal 15M context improve 1M entries? Marginal in-sample only; validation did not confirm.
2. Does it improve SHORTS? See SIDE_RESULTS.csv — shorts remain weak without reset retention.
3. WAIT-for-reset vs hard reject? Compare ANTI_CHASE_RESULTS.csv.
4. Reversals? See REVERSAL_RESULTS.csv.
5. Real direction beats random? YES
6. Stable OOS? NO — see TEST vs baseline test (baseline test AvgR=0.0473)
7. Shadow testing? NO — no candidate passed full standard.
8. Do NOT change: Phase72A, Phase73, Phase74, M0, live execution.

Elapsed: 102.5s
