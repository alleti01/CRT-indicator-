PHASE63 — CAUSAL EARLY-LOCATION → REACTION ENTRY AUDIT
=======================================================

CAUSALITY: PASS
PREFIX INVARIANCE: PASS
FUTURE LEAKAGE: NONE
LOCATION ENGINE MODIFIED: NO

Population: 87,798 frozen first-signal opportunities (Phase58 causal cluster rank=1).
Management reference (frozen): Phase62 hybrid structure + 1.75 ATR cap, 2.5R target, 60m max hold.
Reaction budget: 5 independent families (R1–R5), max 3 candidate traders, max 1-bar wait (T+1).

--------------------------------------------
BASELINES
--------------------------------------------

PHASE58 FIRST SIGNAL:

N: 87,798
+1 before -1: 49.1%
+2 before -1: 33.0%
+2.5 before -1: 28.3%
MFE: 3.56 ATR (60m median)
MAE: 3.56 ATR (60m median)

ONE-BAR DELAY:

N: 87,798
+1 before -1: 48.6%
+2 before -1: 32.7%
+2.5 before -1: 28.0%
Median chase: 0.62 ATR

PHASE62 TRADER A:

AvgR: -0.0003
PF: 1.00
TotalR: -26R
MaxDD: 419R

One-bar delay alone does not improve path ordering; it adds 0.13 ATR median chase with no benefit.

--------------------------------------------
REACTION R1 — REJECTION
--------------------------------------------

T0 (same-bar):
N: 31,953
Median delay: 0 bars
Median chase: 0.24 ATR
+1 before -1: 49.9%
+2 before -1: 33.6%
+2.5 before -1: 28.8%
+2 move retention: 70.4%
+3 move retention: 57.2%
MFE: 3.60 ATR
MAE: 3.54 ATR

T1 (+1 bar):
N: 34,410
Median delay: 1 bar
Median chase: 0.52 ATR
+1 before -1: 49.5%
+2 before -1: 33.1%
+2.5 before -1: 28.4%
+2 move retention: 69.3%
+3 move retention: 55.8%
MFE: 3.50 ATR
MAE: 3.53 ATR

T2 DIAGNOSTIC:
N: 34,371 | +2/-1: 32.9% | retention: 39.1% | chase: 0.65 ATR

VERDICT: REJECT — marginal +0.6pp path gain at T0 destroys 59% of opportunities; no material path improvement at promotable timing.

--------------------------------------------
REACTION R2 — MICRO BREAK
--------------------------------------------

T0:
N: 28,874
Median delay: 0 bars
Median chase: 0.74 ATR
+1 before -1: 48.8%
+2 before -1: 32.6%
+2.5 before -1: 28.1%
+2 move retention: 69.5%
+3 move retention: 56.2%
MFE: 3.54 ATR
MAE: 3.57 ATR

T1:
N: 21,106
Median delay: 1 bar
Median chase: 1.33 ATR
+1 before -1: 49.0%
+2 before -1: 33.0%
+2.5 before -1: 28.3%
+2 move retention: 69.8%
+3 move retention: 56.5%
MFE: 3.52 ATR
MAE: 3.54 ATR

T2 DIAGNOSTIC:
N: 19,430 | +2/-1: 32.6% | retention: 22.1% | chase: 1.58 ATR

VERDICT: REJECT — high chase, low retention, no path ordering gain over baseline.

--------------------------------------------
REACTION R3 — DISPLACEMENT
--------------------------------------------

T0:
N: 42,447
Median delay: 0 bars
Median chase: 0.65 ATR
+1 before -1: 49.2%
+2 before -1: 33.0%
+2.5 before -1: 28.3%
+2 move retention: 69.4%
+3 move retention: 56.4%
MFE: 3.53 ATR
MAE: 3.59 ATR

T1:
N: 29,443
Median delay: 1 bar
Median chase: 0.51 ATR
+1 before -1: 50.4%
+2 before -1: 34.4%
+2.5 before -1: 29.6%
+2 move retention: 70.2%
+3 move retention: 56.7%
MFE: 3.55 ATR
MAE: 3.52 ATR

T2 DIAGNOSTIC:
N: 27,299 | +2/-1: 33.4% | retention: 31.1% | chase: 0.53 ATR

VERDICT: KEEP (best single family) — only family achieving >+1.5pp +2/-1 improvement at T+1 with acceptable chase; still loses 66% of opportunities.

--------------------------------------------
REACTION R4 — FAILURE / RECLAIM
--------------------------------------------

T0:
N: 57,268
Median delay: 0 bars
Median chase: 0.48 ATR
+1 before -1: 49.1%
+2 before -1: 33.0%
+2.5 before -1: 28.3%
+2 move retention: 69.7%
+3 move retention: 56.6%
MFE: 3.56 ATR
MAE: 3.56 ATR

T1:
N: 14,903
Median delay: 1 bar
Median chase: 0.34 ATR
+1 before -1: 48.8%
+2 before -1: 32.6%
+2.5 before -1: 28.2%
+2 move retention: 69.4%
+3 move retention: 56.1%
MFE: 3.54 ATR
MAE: 3.54 ATR

T2 DIAGNOSTIC:
N: 12,899 | +2/-1: 32.7% | retention: 14.7% | chase: 0.34 ATR

VERDICT: REJECT — fires on 65% of bars at T0 with zero path improvement; T+1 over-filters without gain.

--------------------------------------------
REACTION R5 — IMMEDIATE CONTINUATION
--------------------------------------------

T0:
N: 47,222
Median delay: 0 bars
Median chase: 0.47 ATR
+1 before -1: 49.1%
+2 before -1: 33.0%
+2.5 before -1: 28.3%
+2 move retention: 69.7%
+3 move retention: 56.6%
MFE: 3.56 ATR
MAE: 3.56 ATR

T1:
N: 9,636
Median delay: 1 bar
Median chase: 0.52 ATR
+1 before -1: 48.9%
+2 before -1: 32.9%
+2.5 before -1: 28.1%
+2 move retention: 69.2%
+3 move retention: 55.9%
MFE: 3.51 ATR
MAE: 3.55 ATR

T2 DIAGNOSTIC:
N: 11,537 | +2/-1: 32.2% | retention: 13.1% | chase: 0.41 ATR

VERDICT: REJECT — continuation filter does not improve path ordering; mostly re-enters baseline population.

--------------------------------------------
DIRECTION AUDIT
--------------------------------------------

ORIGINAL_CONFIRMED:

N: 28,912
+2 before -1: 100% (by classification — original direction reached +2 before -1)

ORIGINAL_CONTRADICTED:

N: 29,664
Original +2 before -1: 0%
Opposite +2 before -1: 100% (by classification — opposite direction would have been favorable)

AMBIGUOUS:

N: 29,222
+2 before -1: 0% (neither direction cleanly favorable-first to +2)

REVERSAL_CONFIRMED:

N: 0
(Strict mutual-exclusion classification; no cases where both directions favorable-first)

Key insight: ~34% of opportunities are clearly good-location/good-direction; ~34% are good-location/bad-direction where opposite side wins path ordering; ~33% are ambiguous chop.

--------------------------------------------
GOOD LOCATION / BAD DIRECTION
--------------------------------------------

COUNT: 49,364

Correctly handled by reaction (pass or flip): 31.4%
Correctly reversed: ~8% (subset of handled — R3 D2 override cases)
Correctly passed: ~23%
Still entered wrong direction: 68.6%

Reaction layer catches only one-third of bad-direction cases. Majority of GLBD opportunities still entered on original direction.

--------------------------------------------
GOOD LOCATION / GOOD DIRECTION
--------------------------------------------

COUNT: 28,912

Preserved (entered original, TAKE): 16.8%
Delayed (WAIT/T+1 but still entered): ~12%
Incorrectly reversed: ~5%
Incorrectly passed: 66.5%

Critical failure: reaction filtering destroys most genuinely good original-direction trades. Confirmation bias toward waiting/passing hurts the best setups.

--------------------------------------------
WAIT AUDIT
--------------------------------------------

T0 (R3 D3):
Path quality: +2/-1 33.0%
Retention: 48.3%
Chase: 0.65 ATR

T+1 (R3 D3):
Path quality: +2/-1 34.4%
Retention: 33.5%
Chase: 0.51 ATR

T+2 DIAGNOSTIC:
Path quality: +2/-1 33.4%
Retention: 31.1%
Chase: 0.53 ATR

BEST LIVE-SAFE TIMING: T+1 — one closed 1M bar buys +1.4pp path ordering vs T0 with modest chase reduction; T+2 adds delay without further path gain.

--------------------------------------------
FINAL CANDIDATES
--------------------------------------------

TRADER R-A:

Logic: D1 — original direction + R3 displacement confirmation, T+1
Trades: 9,214
Retention: 10.5%
Median delay: 1 bar
Median chase: 0.82 ATR
+1 before -1: 49.4%
+2 before -1: 33.2%
+2.5 before -1: 28.3%
+2 move retention: 69.8%
+3 move retention: 56.0%
AvgR: +0.014
PF: 1.02
TotalR: +132R
MaxDD: 115R
Net TotalR: -1,372R
1.5x cost TotalR: -2,125R

TRADER R-B:

Logic: D3 — reaction direction independent, R3 displacement T0
Trades: 42,447
Retention: 48.3%
Median delay: 0 bars
Median chase: 0.65 ATR
+1 before -1: 49.2%
+2 before -1: 33.0%
+2.5 before -1: 28.3%
+2 move retention: 69.4%
+3 move retention: 56.4%
AvgR: +0.005
PF: 1.01
TotalR: +199R
MaxDD: 218R
Net TotalR: -7,285R
1.5x cost TotalR: -11,027R

TRADER R-C:

Logic: D2 — original as soft prior, R3 displacement T+1, override on contradiction
Trades: 29,443
Retention: 33.5%
Median delay: 1 bar
Median chase: 0.51 ATR
+1 before -1: 50.4%
+2 before -1: 34.4%
+2.5 before -1: 29.6%
+2 move retention: 70.2%
+3 move retention: 56.7%
AvgR: +0.028
PF: 1.04
TotalR: +816R
MaxDD: 161R
Net TotalR: -5,320R
1.5x cost TotalR: -8,389R

--------------------------------------------
BEST CANDIDATE
--------------------------------------------

NAME: TRADER R-C

OPPORTUNITY: Frozen Phase58 first signal (unchanged)

DIRECTION LOGIC: D2 — original direction soft prior; reaction may override on strong contradiction

REACTION: R3 Displacement (body ≥0.35 ATR, close near extreme, not extended >1.2 ATR from origin)

WAIT: T+1 (one closed 1M bar after opportunity)

ENTRY: Next bar open after reaction bar closes

PASS: No displacement signal or excessive extension

REVERSE: When displacement direction contradicts original

MANAGEMENT: FROZEN PHASE62 REFERENCE (hybrid + 1.75 ATR cap, 2.5R, 60m)

Trades: 29,443
Opportunity retention: 33.5%
Large-move retention: 70.2% (+2 ATR), 56.7% (+3 ATR)

Median delay: 1 bar
Median chase: 0.51 ATR

+1 before -1: 50.4%
+1.5 before -1: 40.7%
+2 before -1: 34.4%
+2.5 before -1: 29.6%

MFE: 3.55 ATR (60m)
MAE: 3.52 ATR (60m)

AvgR: +0.028
PF: 1.04
TotalR: +816R
MaxDD: 161R

Net TotalR: -5,320R
1.5x cost TotalR: -8,389R

LONG:
N: 15,218
AvgR: +0.056
TotalR: +847R
+2 before -1: 34.9%

SHORT:
N: 14,225
AvgR: -0.002
TotalR: -30R
+2 before -1: 33.9%

--------------------------------------------
WALK-FORWARD
--------------------------------------------

TRAIN:

N: 17,665
AvgR: +0.040
PF: 1.06
TotalR: +708R
+2 before -1: 34.7%

VALIDATION:

N: 5,889
AvgR: -0.004
PF: 0.99
TotalR: -26R
+2 before -1: 33.3%

HOLDOUT:

N: 5,889
AvgR: +0.023
PF: 1.03
TotalR: +134R
+2 before -1: 34.5%

Path ordering improvement stable across splits (~34–35% vs 33% baseline). Gross expectancy unstable; validation near breakeven.

--------------------------------------------
ROBUSTNESS
--------------------------------------------

Positive years: 8 / 10

Parameter cliff: NO (body 0.30/0.40 and extension 1.1/1.3 variants within ±0.5pp path ordering)

Opportunity destruction: HIGH (66.5% passed)

Entry delay: LOW (median 1 bar)

Chase damage: LOW (0.51 ATR vs 0.49 baseline)

Cost stress: FAIL (net and 1.5× stress deeply negative)

--------------------------------------------
PRIMARY FINDING
--------------------------------------------

IS PHASE58 PRIMARILY A GOOD LOCATION DETECTOR: YES

IS ORIGINAL DIRECTION GOOD ENOUGH BY ITSELF: NO

DOES IMMEDIATE REACTION IMPROVE PATH ORDERING: YES (MARGINAL — +1.4pp best case)

BEST REACTION TYPE: R3 Displacement at T+1

SHOULD ORIGINAL DIRECTION REMAIN PRIMARY: SOFT PRIOR

SHOULD REACTION BE ALLOWED TO REVERSE: ONLY STRONG CASES (current override rate too low to help GLBD, too high to preserve GLGD)

DOES WAITING ONE BAR HELP: YES (for R3 displacement)

DOES WAITING TWO BARS HELP ENOUGH TO JUSTIFY DELAY: NO

--------------------------------------------
VERDICT
--------------------------------------------

CAUSAL REACTION EDGE: NO (gross positive at best candidate, not robust; fails cost-adjusted)

+2-BEFORE-1 IMPROVED MATERIALLY: NO (+34.4% vs 32.8% baseline = +1.6pp; threshold was ≥+3pp without heavy opportunity loss)

EARLY LOCATION PRESERVED: PARTIAL (33.5% retention; median 1-bar delay acceptable)

LARGE-MOVE RETENTION ACCEPTABLE: YES (70.2% +2 ATR retention vs 69.7% baseline)

COST-ADJUSTED EXPECTANCY POSITIVE: NO

OVER-OPTIMIZED: NO

READY TO FREEZE ENTRY LOGIC: NO

READY FOR PINE: NO

READY FOR LIVE TRADING: NO

READY FOR PHASE64: YES — redesign around location detector thesis, not forced directional entry

--------------------------------------------
COMPARISON VS PHASE58 FIRST SIGNAL
--------------------------------------------

                         PHASE58 FIRST    TRADER R-C (BEST)
---------------------------------------------------------
Opportunities            87,798           87,798
Trades                   87,798           29,443
+1 before -1             49.1%            50.4%
+2 before -1             33.0%            34.4%
+2.5 before -1           28.3%            29.6%
MFE 60m                  3.56 ATR         3.55 ATR
MAE 60m                  3.56 ATR         3.52 ATR
Median delay             0                1 bar
Chase                    0.49 ATR         0.51 ATR
+2 move retention        69.7%            70.2%
+3 move retention        56.7%            56.7%
AvgR (gross)             -0.0003          +0.028
PF                       1.00             1.04
TotalR (gross)           -26R             +816R
MaxDD                    419R             161R
Cost-adjusted TotalR     ~-5,800R*        -5,320R

*Estimated from Phase62 cost failure pattern on full opportunity set.

Reaction buys modest path ordering and gross expectancy at the cost of two-thirds of opportunities. It does not solve the core problem: ~67% of locations still hit -1 ATR before +2 ATR even with best reaction.

--------------------------------------------
STOP CONDITION — CONCLUSION
--------------------------------------------

Phase63 answers the central question:

**CAN WE KEEP PHASE58'S GOOD EARLY LOCATION WHILE USING THE FIRST 0–1 MINUTES OF PRICE REACTION TO MAKE A BETTER DIRECTIONAL ENTRY?**

**Answer: PARTIALLY, INSUFFICIENTLY.**

Immediate causal reaction (especially R3 displacement at T+1 with soft-prior override) produces the best observed path ordering (+34.4% +2-before-1) and positive gross expectancy (+816R) without large chase. However:

1. Improvement is marginal (+1.6pp), not material (+3pp target).
2. Opportunity retention collapses to 33.5%.
3. Good-direction trades are passed 66.5% of the time.
4. Bad-direction trades still entered 68.6% of the time.
5. Cost-adjusted expectancy remains deeply negative.

**Recommendation:** Do not force Phase58 into a directional-entry system via reaction filters. Treat Phase58 as a **location/opportunity detector**. Phase64 should explore architectures that trade the location without requiring immediate directional commitment — e.g. bracket/scaled approaches, optional pass, or asymmetric structures — rather than stacking more entry filters.

Artifacts:
- `phase63/reports/phase63_audit.json` — full numeric results
- `phase63/diagnostics/visual_review/phase63_sample.csv` — sample cases for manual review
- `phase63/python/reaction.py` — frozen R1–R5 detectors
- `phase63/tools/run_phase63_audit.py` — reproducible audit runner
