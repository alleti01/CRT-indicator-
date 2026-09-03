CAUSAL PRICE-ACTION ENTRY DISCOVERY AT PHASE58 LOCATIONS
=======================================================

CAUSALITY: PASS
PREFIX INVARIANCE: PASS
FUTURE LEAKAGE: NONE
PHASE58 LOCATION ENGINE MODIFIED: NO
PHASE58 DIRECTION USED: NO (stored for diagnostics only)

--------------------------------------------
POPULATION
--------------------------------------------

PHASE58 LOCATIONS: 87,798
LOCATIONS WITH E1: 44,172 (50.3%)
LOCATIONS WITH E2: 55,019 (62.7%)
LOCATIONS WITH E3: 39,766 (45.3%)
NO PRICE-ACTION EVENT (any family, T0–T+3): 15,591
CONFLICTING EVENTS: E1=3,482 E2=2,089 E3=2,873

--------------------------------------------
BASELINES
--------------------------------------------

PHASE58 ORIGINAL DIRECTION (T+1 open, 1 ATR stop, 2.5R target):
  N: 87,798
  +1/-1: 49.1%
  +2/-1: 33.0%
  MFE 15m: 1.70 ATR
  MAE 15m: 1.73 ATR
  Net AvgR: -0.2842

PHASE65 MARKET CHOICE (M3):
  N: 64,699
  +1/-1: 49.3%
  +2/-1: 33.3%
  Net AvgR: -0.5429

--------------------------------------------
E1 — FAILED PUSH / REJECTION
--------------------------------------------

Definition:
  E1: probe beyond 5-bar micro extreme, close back inside → fade
  E2: close breaks 5-bar level with open inside → continuation
  E3: break beyond 5-bar level, close reclaims, open on prior side → fade
Causal level: prior 5-bar high/low (excludes current bar)
Entry: next bar open after trigger bar close (timing B)

N: 44,172
LONG: 21,545
SHORT: 22,627
Retention: 50.3%
Expired (no event T0–T+3): 40,144
Conflicts: 3,482

Median delay: 2.0 bars
Median chase: 0.59 ATR

MFE 3m: 0.69 ATR
MAE 3m: 0.76 ATR
MFE 5m: 0.92 ATR
MAE 5m: 0.99 ATR
MFE 15m: 1.65 ATR
MAE 15m: 1.75 ATR
MFE 60m: 3.44 ATR
MAE 60m: 3.57 ATR

+1 before -1: 47.4%
+1.5 before -1: 38.0%
+2 before -1: 31.7%
+2.5 before -1: 27.3%
+1 before -1.5: 57.8%
+2 before -1.5: 41.2%
+2.5 before -1.5: 36.0%

Natural stop (median): 0.66 ATR
Gross AvgR: -0.0247
Cost R (avg): 0.4453
Net AvgR: -0.4700
PF net: 0.552
Net TotalR: -20761
MaxDD: 20763
1.5x cost Net AvgR: -0.6927
2x cost Net AvgR (est): -0.9153

VERDICT: REJECT

--------------------------------------------
E2 — BREAK + ACCEPTANCE
--------------------------------------------

Definition:
  E1: probe beyond 5-bar micro extreme, close back inside → fade
  E2: close breaks 5-bar level with open inside → continuation
  E3: break beyond 5-bar level, close reclaims, open on prior side → fade
Causal level: prior 5-bar high/low (excludes current bar)
Entry: next bar open after trigger bar close (timing B)

N: 55,019
LONG: 28,222
SHORT: 26,797
Retention: 62.7%
Expired (no event T0–T+3): 30,690
Conflicts: 2,089

Median delay: 2.0 bars
Median chase: 0.99 ATR

MFE 3m: 0.77 ATR
MAE 3m: 0.76 ATR
MFE 5m: 1.01 ATR
MAE 5m: 0.98 ATR
MFE 15m: 1.76 ATR
MAE 15m: 1.70 ATR
MFE 60m: 3.68 ATR
MAE 60m: 3.50 ATR

+1 before -1: 50.4%
+1.5 before -1: 40.6%
+2 before -1: 34.1%
+2.5 before -1: 29.2%
+1 before -1.5: 60.8%
+2 before -1.5: 44.0%
+2.5 before -1.5: 38.4%

Natural stop (median): 0.41 ATR
Gross AvgR: -0.0028
Cost R (avg): 1.4102
Net AvgR: -1.4130
PF net: 0.252
Net TotalR: -77740
MaxDD: 77738
1.5x cost Net AvgR: -2.1181
2x cost Net AvgR (est): -2.8232

VERDICT: REJECT

--------------------------------------------
E3 — FAILED BREAK + RECLAIM
--------------------------------------------

Definition:
  E1: probe beyond 5-bar micro extreme, close back inside → fade
  E2: close breaks 5-bar level with open inside → continuation
  E3: break beyond 5-bar level, close reclaims, open on prior side → fade
Causal level: prior 5-bar high/low (excludes current bar)
Entry: next bar open after trigger bar close (timing B)

N: 39,766
LONG: 19,436
SHORT: 20,330
Retention: 45.3%
Expired (no event T0–T+3): 45,159
Conflicts: 2,873

Median delay: 2.0 bars
Median chase: 0.59 ATR

MFE 3m: 0.69 ATR
MAE 3m: 0.76 ATR
MFE 5m: 0.92 ATR
MAE 5m: 0.99 ATR
MFE 15m: 1.65 ATR
MAE 15m: 1.74 ATR
MFE 60m: 3.42 ATR
MAE 60m: 3.54 ATR

+1 before -1: 47.6%
+1.5 before -1: 38.3%
+2 before -1: 31.9%
+2.5 before -1: 27.5%
+1 before -1.5: 57.9%
+2 before -1.5: 41.4%
+2.5 before -1.5: 36.2%

Natural stop (median): 0.64 ATR
Gross AvgR: -0.0265
Cost R (avg): 0.4227
Net AvgR: -0.4492
PF net: 0.564
Net TotalR: -17864
MaxDD: 17871
1.5x cost Net AvgR: -0.6606
2x cost Net AvgR (est): -0.8720

VERDICT: REJECT

--------------------------------------------
PRICE ACTION WITHOUT PHASE58 (matched controls, n≈10k sample)
--------------------------------------------

E1 ONLY (no Phase58):
  N: 4,698
  +2/-1: 38.5%
  Net AvgR: -0.5250
E1 + PHASE58:
  N: 44,172
  +2/-1: 31.7%
  Net AvgR: -0.4700
  Phase58 path lift (+2/-1): -6.8%

E2 ONLY (no Phase58):
  N: 4,253
  +2/-1: 20.7%
  Net AvgR: -2.3713
E2 + PHASE58:
  N: 55,019
  +2/-1: 34.1%
  Net AvgR: -1.4130
  Phase58 path lift (+2/-1): +13.5%

E3 ONLY (no Phase58):
  N: 4,052
  +2/-1: 35.7%
  Net AvgR: -0.5885
E3 + PHASE58:
  N: 39,766
  +2/-1: 31.9%
  Net AvgR: -0.4492
  Phase58 path lift (+2/-1): -3.8%

--------------------------------------------
DIRECTION AGREEMENT (best family E2)
--------------------------------------------

PRICE ACTION AGREES WITH PHASE58:
  N: 44,699
  +2/-1: 34.1%
  Net AvgR: -1.3890

PRICE ACTION DISAGREES WITH PHASE58:
  N: 10,320
  +2/-1: 34.5%
  Net AvgR: -1.5167

PHASE58 DIRECTION ADDS VALUE: NO (path and net nearly identical)

--------------------------------------------
WALK-FORWARD (E2, chronological 60/20/20)
--------------------------------------------

TRAIN:
  N: 33,011
  +2/-1: (not stored per split)
  Net AvgR: -1.5955
  PF: 0.220
  TotalR: -52670

VALIDATION:
  N: 11,004
  +2/-1: (not stored per split)
  Net AvgR: -1.1387
  PF: 0.297
  TotalR: -12530

HOLDOUT:
  N: 11,004
  +2/-1: (not stored per split)
  Net AvgR: -1.1397
  PF: 0.322
  TotalR: -12541

--------------------------------------------
YEAR STABILITY (E2)
--------------------------------------------

  2017: N=1,259 Net AvgR=-5.500 PF=0.04 TotalR=-6924
  2018: N=5,994 Net AvgR=-1.862 PF=0.18 TotalR=-11159
  2019: N=5,812 Net AvgR=-1.973 PF=0.16 TotalR=-11469
  2020: N=6,039 Net AvgR=-1.169 PF=0.30 TotalR=-7060
  2021: N=6,250 Net AvgR=-1.134 PF=0.30 TotalR=-7086
  2022: N=6,434 Net AvgR=-1.199 PF=0.30 TotalR=-7712
  2023: N=6,381 Net AvgR=-1.107 PF=0.30 TotalR=-7065
  2024: N=6,298 Net AvgR=-1.274 PF=0.28 TotalR=-8026
  2025: N=6,225 Net AvgR=-1.225 PF=0.30 TotalR=-7626
  2026: N=4,327 Net AvgR=-0.835 PF=0.40 TotalR=-3614

POSITIVE NET YEARS: 0/10

--------------------------------------------
ROBUSTNESS
--------------------------------------------

PARAMETER CLIFF: NO (single broad definition per family, no grid search)
COST STRESS: FAIL (all families net negative at 1x, 1.5x, 2x)
OVERLAP INFLATION: not computed (independent-trade metrics reported)
ENTRY DELAY: MEDIUM (median 2 bars after alarm)
CHASE: MEDIUM–HIGH (E2 median 0.99 ATR; E1/E3 ~0.59 ATR)

--------------------------------------------
BEST ENTRY FAMILY
--------------------------------------------

NAME: E2
LOCATION: Phase58 causal alarm (frozen 87,798)
CAUSAL LEVEL: prior 5-bar high/low
TRIGGER: close breaks/ rejects 5-bar level on trigger bar
DIRECTION: price-action defined (LONG/SHORT from event)
ENTRY: next bar open (T+1 from trigger)
INVALIDATION: beyond failed extreme (E1/E3) or accepted level (E2)
MEDIAN DELAY: 2.0 bars
MEDIAN CHASE: 0.99 ATR
MEDIAN STOP ATR: 0.41
+1 BEFORE -1: 50.4%
+2 BEFORE -1: 34.1%
+2 BEFORE -1.5: 44.0%
GROSS AVGR: -0.0028
COST R: 1.4102
NET AVGR: -1.4130
PF: 0.252
NET TOTALR: -77740
MAXDD: 77738
HOLDOUT Net AvgR: -1.1397

--------------------------------------------
PHASE58 VALUE
--------------------------------------------

PRICE ACTION WORKS WITHOUT PHASE58: NO (E2 +2/-1 20.7% vs 34.1% at Phase58)
PHASE58 IMPROVES PRICE ACTION: LARGE (path ordering)
PHASE58 IMPROVES ECONOMICS: NO (both strongly net negative)
PHASE58 SHOULD REMAIN IN ARCHITECTURE: CONTEXT ONLY (location alarm, not entry filter)

--------------------------------------------
CENTRAL ANSWER
--------------------------------------------

FAILED PUSH HAS DIRECTIONAL EDGE: NO (+2/-1 31.7%, net negative)
BREAK + ACCEPTANCE HAS DIRECTIONAL EDGE: MARGINAL PATH ONLY (+2/-1 34.1%, best path family)
FAILED BREAK + RECLAIM HAS DIRECTIONAL EDGE: NO (+2/-1 31.9%)
ANY SIMPLE PRICE-ACTION ENTRY HAS REAL EDGE: NO
EDGE SURVIVES COSTS: NO
EDGE SURVIVES HOLDOUT: NO

--------------------------------------------
VERDICT
--------------------------------------------

NEW CAUSAL ENTRY EDGE FOUND: NO
ENTRY IS EARLY ENOUGH: YES (median 2 bars, T+3 window enforced)
DIRECTIONAL ASYMMETRY MEANINGFUL: NO (+1/-1 ~50% at best; MFE≈MAE)
NET EXPECTANCY POSITIVE: NO
ROBUST: NO (0 positive net years on E2)
OVER-OPTIMIZED: NO (single broad rule per family)
READY TO FREEZE: NO
READY FOR MANUAL VISUAL VALIDATION: NO (no candidate to validate)
READY FOR PINE: NO
READY FOR LIVE: NO

NEXT RESEARCH REQUIRED:
  STOP this branch. Simple causal E1/E2/E3 at Phase58 locations do not produce
  tradeable directional edge after costs. Phase58 remains a valid LOCATION alarm
  (Phase64) but entry must come from elsewhere — test price-action independently
  of Phase58, or begin a genuinely new edge-discovery branch. Do NOT combine
  weak families or optimize management to rescue negative expectancy.
