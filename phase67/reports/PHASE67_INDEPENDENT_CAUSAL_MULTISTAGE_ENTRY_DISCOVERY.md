PHASE67 — INDEPENDENT CAUSAL MULTI-STAGE ENTRY DISCOVERY
========================================================

CAUSALITY: PASS
PREFIX INVARIANCE: PASS
FUTURE LEAKAGE: NONE
DATA: 2017-10-01 17:00:00-05:00 → 2026-08-28 15:59:00-05:00
BARS: 3,136,946
INSTRUMENT: NQ continuous 1M
PHASE58 USED IN DISCOVERY: NO
TOTAL STRUCTURAL HYPOTHESES TESTED: 7

--------------------------------------------
FAMILY A
EXPANSION → PULLBACK → RESUMPTION
--------------------------------------------

N episodes: 124,404
LONG: 62,258  SHORT: 62,146
Median delay: 5.0 bars
Median chase: 3.01 ATR
Median natural stop: 1.38 ATR

+1/-1: 49.4%
+1.5/-1: 39.6%
+2/-1: 33.0%
+2.5/-1: 28.1%
+2/-1.5: 42.5%
+3/-1.5: 32.7%

MFE 15: 1.69  MAE 15: 1.72  DAS: 0.98
MFE 60: 3.52  MAE 60: 3.57  DAS: 0.99

Gross AvgR: 0.0080
Net AvgR: -0.2756
PF: 0.680
TotalR: -34283
MaxDD: 34289
Cost R: 0.2836
Early gate: False (SYMMETRIC_NO_EDGE)
VERDICT: REJECT

--------------------------------------------
FAMILY B10
SWEEP → DISPLACEMENT → RETEST (10-bar)
--------------------------------------------

N episodes: 108,162
LONG: 53,987  SHORT: 54,175
Median delay: 3.0 bars
Median chase: 0.41 ATR
Median natural stop: 0.51 ATR

+1/-1: 49.3%
+1.5/-1: 39.6%
+2/-1: 33.2%
+2.5/-1: 28.5%
+2/-1.5: 42.6%
+3/-1.5: 33.1%

MFE 15: 1.72  MAE 15: 1.73  DAS: 0.99
MFE 60: 3.56  MAE 60: 3.58  DAS: 0.99

Gross AvgR: -0.0086
Net AvgR: -1.3189
PF: 0.253
TotalR: -142658
MaxDD: 142656
Cost R: 1.3104
Early gate: False (SYMMETRIC_NO_EDGE)
VERDICT: REJECT

--------------------------------------------
FAMILY B5
SWEEP → DISPLACEMENT → RETEST (5-bar)
--------------------------------------------

N episodes: 132,212
LONG: 66,100  SHORT: 66,112
Median delay: 3.0 bars
Median chase: 0.41 ATR
Median natural stop: 0.51 ATR

+1/-1: 49.4%
+1.5/-1: 39.7%
+2/-1: 33.3%
+2.5/-1: 28.6%
+2/-1.5: 42.7%
+3/-1.5: 33.1%

MFE 15: 1.71  MAE 15: 1.73  DAS: 0.99
MFE 60: 3.54  MAE 60: 3.57  DAS: 0.99

Gross AvgR: -0.0141
Net AvgR: -1.3123
PF: 0.253
TotalR: -173505
MaxDD: 173505
Cost R: 1.2982
Early gate: False (SYMMETRIC_NO_EDGE)
VERDICT: REJECT

--------------------------------------------
FAMILY B20
SWEEP → DISPLACEMENT → RETEST (20-bar)
--------------------------------------------

N episodes: 76,491
LONG: 38,060  SHORT: 38,431
Median delay: 3.0 bars
Median chase: 0.41 ATR
Median natural stop: 0.51 ATR

+1/-1: 49.8%
+1.5/-1: 40.0%
+2/-1: 33.5%
+2.5/-1: 28.7%
+2/-1.5: 42.8%
+3/-1.5: 33.1%

MFE 15: 1.71  MAE 15: 1.71  DAS: 1.00
MFE 60: 3.50  MAE 60: 3.53  DAS: 0.99

Gross AvgR: -0.0078
Net AvgR: -1.3351
PF: 0.252
TotalR: -102121
MaxDD: 102117
Cost R: 1.3272
Early gate: False (SYMMETRIC_NO_EDGE)
VERDICT: REJECT

--------------------------------------------
FAMILY C
COMPRESSION → EXPANSION → RETEST
--------------------------------------------

N episodes: 21,291
LONG: 10,617  SHORT: 10,674
Median delay: 3.0 bars
Median chase: 0.35 ATR
Median natural stop: 0.72 ATR

+1/-1: 49.3%
+1.5/-1: 39.5%
+2/-1: 32.8%
+2.5/-1: 27.9%
+2/-1.5: 42.3%
+3/-1.5: 32.4%

MFE 15: 1.75  MAE 15: 1.79  DAS: 0.98
MFE 60: 3.63  MAE 60: 3.65  DAS: 0.99

Gross AvgR: -0.0108
Net AvgR: -0.8120
PF: 0.384
TotalR: -17287
MaxDD: 17302
Cost R: 0.8012
Early gate: False (SYMMETRIC_NO_EDGE)
VERDICT: REJECT

--------------------------------------------
FAMILY D
FAILED AUCTION → DISPLACEMENT → RETEST
--------------------------------------------

N episodes: 97,317
LONG: 48,763  SHORT: 48,554
Median delay: 4.0 bars
Median chase: 0.30 ATR
Median natural stop: 0.76 ATR

+1/-1: 49.4%
+1.5/-1: 39.8%
+2/-1: 33.4%
+2.5/-1: 28.6%
+2/-1.5: 42.8%
+3/-1.5: 33.4%

MFE 15: 1.72  MAE 15: 1.73  DAS: 0.99
MFE 60: 3.56  MAE 60: 3.60  DAS: 0.99

Gross AvgR: 0.0093
Net AvgR: -0.6829
PF: 0.436
TotalR: -66454
MaxDD: 66452
Cost R: 0.6921
Early gate: False (SYMMETRIC_NO_EDGE)
VERDICT: REJECT

--------------------------------------------
FAMILY E
STRUCTURE BREAK → RETRACE → SECOND IMPULSE
--------------------------------------------

N episodes: 79,045
LONG: 40,139  SHORT: 38,906
Median delay: 2.0 bars
Median chase: 1.19 ATR
Median natural stop: 1.92 ATR

+1/-1: 48.5%
+1.5/-1: 38.7%
+2/-1: 32.4%
+2.5/-1: 27.8%
+2/-1.5: 42.1%
+3/-1.5: 32.6%

MFE 15: 1.71  MAE 15: 1.77  DAS: 0.97
MFE 60: 3.55  MAE 60: 3.59  DAS: 0.99

Gross AvgR: -0.0081
Net AvgR: -0.1880
PF: 0.754
TotalR: -14857
MaxDD: 14865
Cost R: 0.1799
Early gate: False (SYMMETRIC_NO_EDGE)
VERDICT: REJECT

--------------------------------------------
FAMILY RANKING (+2/-1)
--------------------------------------------

1. B20 (SWEEP → DISPLACEMENT → RETEST (20-bar)): +2/-1=33.5%
2. D (FAILED AUCTION → DISPLACEMENT → RETEST): +2/-1=33.4%
3. B5 (SWEEP → DISPLACEMENT → RETEST (5-bar)): +2/-1=33.3%
4. B10 (SWEEP → DISPLACEMENT → RETEST (10-bar)): +2/-1=33.2%
5. A (EXPANSION → PULLBACK → RESUMPTION): +2/-1=33.0%
6. C (COMPRESSION → EXPANSION → RETEST): +2/-1=32.8%
7. E (STRUCTURE BREAK → RETRACE → SECOND IMPULSE): +2/-1=32.4%

--------------------------------------------
CENTRAL ANSWERS
--------------------------------------------

A HAS REAL DIRECTIONAL EDGE: NO
B HAS REAL DIRECTIONAL EDGE: NO
C HAS REAL DIRECTIONAL EDGE: NO
D HAS REAL DIRECTIONAL EDGE: NO
E HAS REAL DIRECTIONAL EDGE: NO
ANY FAMILY HAS GROSS EDGE: YES
ANY FAMILY HAS NET EDGE: NO
RANDOM DIRECTION CONTROL: FAIL

--------------------------------------------
FINAL VERDICT
--------------------------------------------

NEW CAUSAL ENTRY EDGE FOUND: NO
BEST FAMILY: B20
DIRECTIONALLY MEANINGFUL: NO
ECONOMICALLY MEANINGFUL: NO
READY FOR PINE: NO
READY FOR LIVE: NO

NEXT STEP: See phase67/reports/phase67_audit.json for full metrics.
Runtime: 299s