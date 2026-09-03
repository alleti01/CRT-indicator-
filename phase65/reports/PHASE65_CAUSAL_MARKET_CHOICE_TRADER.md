PHASE65 — CAUSAL ACTIVITY ALARM → MARKET CHOICE → EARLY EXPANSION TRADER
=======================================================================

CAUSALITY: PASS
PREFIX INVARIANCE: PASS
FUTURE LEAKAGE: NONE
PHASE58 LOCATION ENGINE MODIFIED: NO
ORIGINAL PHASE58 DIRECTION USED FOR ENTRY: NO

--------------------------------------------
POPULATION
--------------------------------------------

PHASE58 ALARMS: 87,798

Decision window: T0–T+3 (expire if no market choice by T+3)

EXPIRED (best concept M3): 26.3% (23,099 alarms)

--------------------------------------------
REFERENCE BASELINES (origin stop, 2.5R target, net costs)
--------------------------------------------

ORIGINAL PHASE58 DIRECTION:
N: 87,798 | +2/-1: 24.1% | Gross AvgR: +0.004 | Net AvgR: -0.669 | Net TotalR: -58,737R

NAIVE ±0.5 FIRST BREAK:
N: 87,798 | Delay: 1 | Chase: 0.57 | +2/-1: 24.0% | Net AvgR: -0.605 | Net TotalR: -53,110R

NAIVE ±1.0 FIRST BREAK:
N: 87,788 | Delay: 2 | Chase: 0.98 | +2/-1: 23.5% | Net AvgR: -0.382 | Net TotalR: -33,510R

PHASE63 R-C:
N: 29,443 | +2/-1: 25.2% | Net AvgR: -0.548 | Net TotalR: -16,132R

Note: Origin-based invalidation with tight risk (~0.5–0.8 ATR) makes cost ≈ 0.4–0.7R per trade, dominating economics.

--------------------------------------------
EARLY SIGNATURE (observable by T+1..T+3, diagnostic sample)
--------------------------------------------

T+1: Explosive median up-excursion 0.77 ATR vs chaos 0.61 | asymmetry +0.25 vs -0.03
T+2: Explosive 1.10 ATR vs chaos 0.78 | asymmetry +0.67 vs 0.0
T+3: Explosive 1.21 ATR vs chaos 0.90 | asymmetry +0.85 vs 0.0

SIMPLE EARLY SIGNATURE EXISTS: YES — explosive/clean events show faster one-sided displacement and asymmetry by T+2.

--------------------------------------------
M1 — DISPLACEMENT (≥0.5 ATR)
--------------------------------------------

N: 87,355 | Retention: 99.5% | Median delay: 1 | Median chase: 0.58 ATR
Remaining MFE 15m: 1.71 | 60m: 3.56
+1/-1: 49.2% | +2/-1: 33.1% | +2/-1.5: 42.7%
Explosive retention: 100% | Clean retention: 99.3%
Gross AvgR: -0.005 | Net AvgR: -0.585 | Net TotalR: -51,146R
VERDICT: REJECT — no gross edge; over-trades chaos

--------------------------------------------
M2 — DISPLACEMENT + CLOSE
--------------------------------------------

N: 83,151 | Retention: 94.7% | Delay: 1 | Chase: 0.71
+2/-1: 33.2% | Explosive retention: 98.3% | Clean: 94.8%
Gross AvgR: -0.031 | Net AvgR: -0.455 | Net TotalR: -37,813R
VERDICT: REJECT

--------------------------------------------
M3 — DISPLACEMENT + LIMITED RETRACEMENT
--------------------------------------------

N: 64,699 | Retention: 73.7% | Delay: 1 | Chase: 0.78
Remaining MFE 15m: 1.70 | 60m: 3.56
+1/-1: 49.3% | +2/-1: 33.3% | +2/-1.5: 42.9%
Explosive: 78% captured, 95% correct side | Clean: 76% captured, 87% correct side
Gross AvgR: -0.025 | Net AvgR: -0.404 | Net TotalR: -26,109R
VERDICT: KEEP (best selectivity/path) — still fails economic gate

--------------------------------------------
M4 — ONE-SIDED DEVELOPMENT
--------------------------------------------

N: 85,656 | Retention: 97.6% | Delay: 1 | Chase: 0.61
+2/-1: 33.1% | Explosive retention: 99.8%
Gross AvgR: -0.023 | Net AvgR: -0.580 | Net TotalR: -49,646R
VERDICT: REJECT (over-trades)

--------------------------------------------
EXPIRATION AUDIT (M3)
--------------------------------------------

ALARMS EXPIRED: 26.3%
Expiration helps: YES — avoids 23k low-quality triggers; missed explosive 22%, clean 24%

--------------------------------------------
MARKET CHOICE QUALITY (M3, from entry)
--------------------------------------------

Median delay: 1 bar | Median chase: 0.78 ATR
+1 before -1: 49.3% | +2 before -1: 33.3% | +2 before -1.5: 42.9%
(Path ordering from market-choice entry beats original-direction baseline 24% +2/-1)

--------------------------------------------
STOP COMPARISON (M3)
--------------------------------------------

S1 ORIGIN: Median stop 0.78 ATR | Gross -1,595R | Net -26,109R
S2 ORIGIN+0.25 buffer: Median stop 1.03 ATR | Gross +731R | Net -19,815R
S3 HYBRID 1.75 cap: Median stop 1.75 ATR | Gross +886R | Net -10,676R

BEST INVALIDATION: S3 hybrid (least negative net; only stop achieving positive gross)

--------------------------------------------
TARGET REFERENCES (M3, origin stop)
--------------------------------------------

2R: Net TotalR -26,212R | 2.5R: -26,109R | 3R: -25,367R

--------------------------------------------
FINAL CANDIDATES
--------------------------------------------

TRADER A (M3 + origin + 2.5R): Net TotalR -26,109R | Explosive capture 78%
TRADER B (M2 + origin buffer + 2.5R): Net TotalR -28,352R | Gross +580R
TRADER C (M4 + hybrid + 2.5R): Net TotalR -15,241R | Gross +122R | Best net

--------------------------------------------
BEST CANDIDATE: TRADER C
--------------------------------------------

ALARM: Phase58 first signal | MARKET CHOICE: M4 one-sided (1.5× asymmetry, ≥0.5 ATR)
ENTRY: Next bar after choice | EXPIRATION: T+3 | INVALIDATION: Hybrid 1.75 ATR | TARGET: 2.5R

N: 85,656 | Retention: 97.6% | Median delay: 1 | Chase: 0.61 ATR | Stop: 1.75 ATR
Remaining MFE 60m: 3.56 ATR | +2/-1: 33.1%
Gross AvgR: +0.001 | Cost R: 0.18 | Net AvgR: -0.178 | Net TotalR: -15,241R
1.5× cost TotalR: ~-22,800R (est.)

--------------------------------------------
ORIGINAL DIRECTION DIAGNOSTIC (M3)
--------------------------------------------

MARKET CHOICE AGREES: N=50,458 | Gross -1,733R | Net -20,515R
MARKET CHOICE DISAGREES: N=14,241 | Gross +138R | Net -5,593R
ORIGINAL DIRECTION ADDS MATERIAL VALUE: NO (disagreement slightly better gross)

--------------------------------------------
WALK-FORWARD (M3, origin stop)
--------------------------------------------

TRAIN: Net TotalR -19,123R | VALIDATION: -4,439R | HOLDOUT: -2,547R
All splits negative net; holdout least bad but still negative.

--------------------------------------------
YEAR STABILITY (M3)
--------------------------------------------

Positive net years: 0 / 10 | 2020 gross +170R, 2025 gross +65R — no year net positive
MAJOR REGIME FAILURE: YES (consistent net losses all years)

--------------------------------------------
OVERLAP
--------------------------------------------

Independent TotalR: -26,109R | One-position TotalR: -25,003R | OVERLAP INFLATION: LOW

--------------------------------------------
CENTRAL QUESTION
--------------------------------------------

USEFUL ACTIVITY ALARM: YES
MARKET DIRECTION CHOSEN CAUSALLY: YES (M3/M4 achieve ~87–95% correct side on clean/explosive)
EARLY ENOUGH: YES (median 1 bar)
ENOUGH EXPANSION LEFT: YES (3.56 ATR remaining MFE 60m)
CLEAN/EXPLOSIVE CAPTURED: YES (76–78% retention M3)
SURVIVES COSTS: NO

--------------------------------------------
VERDICT
--------------------------------------------

CAUSAL TRADING EDGE: NO
NET EXPECTANCY POSITIVE: NO
HOLDOUT POSITIVE: NO
COST STRESS PASS: NO
EARLY EXPANSION CONVERTED TO TRADEABLE EDGE: NO
ORIGINAL PHASE58 DIRECTION REQUIRED: NO
OVER-OPTIMIZED: NO
READY TO FREEZE ARCHITECTURE: NO
READY FOR MANUAL VISUAL VALIDATION: YES (phenomenon capture works; economics fail)
READY FOR PINE: NO
READY FOR LIVE TRADING: NO
READY FOR PHASE66: NO

--------------------------------------------
STOP CONDITION — CONCLUSION
--------------------------------------------

Phase58 IS a useful early activity alarm. Causal market choice CAN identify expansion direction early (especially M3 on clean/explosive events) with meaningful remaining MFE.

However, this architecture CANNOT be converted into positive net expectancy:

1. Gross edge is zero to slightly negative for all market-choice concepts with origin stop
2. Even best hybrid-stop candidate (Trader C) is net -15,241R
3. Origin invalidation creates tight stops → cost consumes 0.2–0.7R per trade
4. Path ordering improves vs forced Phase58 direction but not enough for profit
5. No year produces net positive results

**Accept:** Phase58 contains real descriptive information (timing, cleanliness, phenomenon capture) that is NOT directly monetizable via alarm → market choice → origin stop → fixed target.

**Do NOT:** Force Phase65 into profitability with more filters, management, or Pine port.

Artifacts: phase65/reports/phase65_audit.json, phase65/diagnostics/visual_review/phase65_sample.csv
