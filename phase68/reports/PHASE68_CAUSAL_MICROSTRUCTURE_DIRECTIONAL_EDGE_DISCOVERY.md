PHASE68 — CAUSAL MICROSTRUCTURE DIRECTIONAL EDGE DISCOVERY
==========================================================

**SCOPE: PILOT ONLY (Jan 2024 trades — full history microstructure NOT available)**

DATA LEVEL: 1 (trades + exchange aggressor side)
FULL-HISTORY MICROSTRUCTURE: DATA_BLOCKED
DATE RANGE: 2024-01-01 → 2024-02-01
INSTRUMENT: NQ.v.0 continuous (Databento GLBX.MDP3 trades)

CAUSALITY: PASS (causal rolling windows; train quantiles frozen)
PREFIX: PASS (pilot design)
FUTURE LEAKAGE: NONE
PHASE58 USED IN DISCOVERY: NO

--------------------------------------------
DATA AVAILABILITY
--------------------------------------------

TRADES: YES (pilot 1 month only)
AGGRESSOR: YES (Databento side B/A)
BID/ASK: NO
TOP SIZE: NO
DEPTH: NO (Families D/E NOT AVAILABLE)
BUY %: 50.2%
SELL %: 49.8%
UNKNOWN %: 0.0%

--- FAMILY A ---
N: 13,767
+0.5/-0.5: 47.4%
+1/-1: 50.0%
+2/-1: 33.8%
MFE 5m: 0.93  MAE 5m: 0.92  DAS: 1.02
Direction acc 5m: 48.7%
Random dir +1/-1: 49.4%
Gross AvgR: 0.0398
Net AvgR: -0.1996
VERDICT: REJECT

--- FAMILY B ---
N: 2,112
+0.5/-0.5: 47.1%
+1/-1: 49.1%
+2/-1: 34.0%
MFE 5m: 0.93  MAE 5m: 0.94  DAS: 0.99
Direction acc 5m: 48.7%
Random dir +1/-1: 50.0%
Gross AvgR: 0.0442
Net AvgR: -0.2802
VERDICT: REJECT

--- FAMILY C ---
N: 2,368
+0.5/-0.5: 45.3%
+1/-1: 49.1%
+2/-1: 32.2%
MFE 5m: 0.93  MAE 5m: 0.96  DAS: 0.97
Direction acc 5m: 50.8%
Random dir +1/-1: 50.4%
Gross AvgR: -0.0065
Net AvgR: -0.2299
VERDICT: REJECT

--- FAMILY F ---
N: 0
+0.5/-0.5: 0.0%
+1/-1: 0.0%
+2/-1: 0.0%
MFE 5m: 0.00  MAE 5m: 0.00  DAS: 0.00
Direction acc 5m: 0.0%
Random dir +1/-1: 0.0%
Gross AvgR: 0.0000
Net AvgR: 0.0000
VERDICT: REJECT

--- FAMILY G ---
N: 1,618
+0.5/-0.5: 48.1%
+1/-1: 49.9%
+2/-1: 32.6%
MFE 5m: 0.93  MAE 5m: 0.89  DAS: 1.04
Direction acc 5m: 49.4%
Random dir +1/-1: 49.4%
Gross AvgR: 0.0096
Net AvgR: -0.0745
VERDICT: REJECT

--- FAMILY H ---
N: 3,969
+0.5/-0.5: 47.6%
+1/-1: 50.2%
+2/-1: 34.5%
MFE 5m: 0.94  MAE 5m: 0.93  DAS: 1.01
Direction acc 5m: 48.3%
Random dir +1/-1: 49.1%
Gross AvgR: 0.0567
Net AvgR: -0.2549
VERDICT: REJECT

--- FAMILIES D/E ---
NOT AVAILABLE (no quote/book data locally)

--- DELTA ONLY BASELINE ---
+2/-1: 34.0%

--------------------------------------------
CENTRAL ANSWERS
--------------------------------------------

AGGRESSIVE FLOW PREDICTS DIRECTION: NO (pilot; ≈ random)
PRICE RESPONSE TO FLOW ADDS VALUE: NO (marginal vs delta-only)
ABSORPTION HAS EDGE: NO
CONTINUATION HAS EDGE: NO
BOOK IMBALANCE ADDS VALUE: NO DATA
REAL DIRECTION BEATS RANDOM: NO (pilot)
EDGE SURVIVES COSTS: NO

--------------------------------------------
FINAL VERDICT
--------------------------------------------

NEW INFORMATION FOUND: NO (beyond Phase27 pilot conclusion)
NEW CAUSAL DIRECTIONAL EDGE FOUND: NO
TRADEABLE MICROSTRUCTURE EDGE: NO
BEST FAMILY (pilot): H
PRIMARY INFORMATION SOURCE: N/A
ROBUST: NO (1 month pilot; full history blocked)
READY TO FREEZE: NO
READY FOR MANUAL REVIEW: NO
READY FOR PINE: NO
READY FOR LIVE: NO

NEXT STEP:
  1. Do NOT fabricate microstructure from OHLC.
  2. To run full-history Phase68: purchase Databento `trades` (~$10/mo/month)
     for 2017–2026, optional `mbp-1` for quote families D/E.
  3. Phase27 pilot already showed order flow ≈ OHLCV; no purchase justified
     until a NEW hypothesis (e.g. sub-minute response-aware rules) shows pilot lift.

Runtime: 110s

See also: phase68/reports/PHASE68_DATA_AVAILABILITY_AUDIT.md