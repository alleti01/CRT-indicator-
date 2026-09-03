PHASE64 — CAUSAL LOCATION EVENT & TWO-SIDED PATH AUDIT
========================================================

CAUSALITY: PASS
PREFIX INVARIANCE: PASS
FUTURE LEAKAGE: NONE
LOCATION ENGINE MODIFIED: NO

--------------------------------------------
POPULATION
--------------------------------------------
PHASE58 EVENTS: 87,798
MATCHED CONTROLS: 87,798
CONTROL RATIO: 1.00:1
MATCH QUALITY: POOR

--------------------------------------------
PRE-EVENT MATCH
--------------------------------------------
ATR — PHASE58: 4.07 | CONTROL: nan | ratio: 1.00
SESSION DISTRIBUTION DIFF: 0.645
MAJOR MISMATCH: YES

--------------------------------------------
ABSOLUTE EXPANSION (median abs excursion / ATR)
--------------------------------------------
                PHASE58    CONTROL     LIFT
5M:               1.71       1.51  +12.8%
10M:               2.42       2.04  +19.0%
15M:               3.00       2.46  +22.2%
30M:               4.32       3.99   +8.2%
60M:               6.28       6.34   -0.9%

--------------------------------------------
EITHER-SIDE THRESHOLDS (within 60M)
--------------------------------------------
±0.5 ATR: P58=100.0% Ctrl=97.4% Lift=+2.7% (NEGLIGIBLE)
±1.0 ATR: P58=100.0% Ctrl=97.0% Lift=+3.1% (SMALL)
±1.5 ATR: P58=99.8% Ctrl=96.7% Lift=+3.2% (SMALL)
±2.0 ATR: P58=99.1% Ctrl=96.0% Lift=+3.2% (SMALL)
±2.5 ATR: P58=96.9% Ctrl=94.0% Lift=+3.1% (SMALL)
±3.0 ATR: P58=92.8% Ctrl=89.4% Lift=+3.8% (SMALL)

--------------------------------------------
TIME TO EXPANSION (median bars, either side)
--------------------------------------------
±0.5 ATR: P58=1.00 | Ctrl=1.00
±1.0 ATR: P58=2.00 | Ctrl=3.00
±1.5 ATR: P58=4.00 | Ctrl=5.00
±2.0 ATR: P58=7.00 | Ctrl=10.00
±2.5 ATR: P58=11.00 | Ctrl=15.00
±3.0 ATR: P58=14.00 | Ctrl=20.00

--------------------------------------------
FIRST SIDE (±0.5 ATR)
--------------------------------------------
+0.5 FIRST: P58=46.8% Ctrl=41.8%
-0.5 FIRST: P58=45.8% Ctrl=46.9%
NEITHER:    P58=0.0% Ctrl=2.6%

--------------------------------------------
FIRST-BREAK CONTINUATION (±0.5 first)
--------------------------------------------
AFTER +0.5 FIRST reach +2: P58=77.8% Ctrl=84.7%
AFTER +0.5 FIRST fail opp:  P58=49.4% Ctrl=53.6%
AFTER -0.5 FIRST reach -2: P58=77.9% Ctrl=82.6%
AFTER -0.5 FIRST fail opp:  P58=46.6% Ctrl=47.4%

--------------------------------------------
TWO-SIDED SWEEPS
--------------------------------------------
±0.5 BOTH: P58=84.2% Ctrl=88.0% Lift=-4.3%
±1.0 BOTH: P58=69.5% Ctrl=79.5% Lift=-12.6%
±1.5 BOTH: P58=54.7% Ctrl=65.9% Lift=-17.1%
±2.0 BOTH: P58=41.0% Ctrl=52.3% Lift=-21.6%

--------------------------------------------
PATH ARCHETYPES (top differences)
--------------------------------------------
EXPLOSIVE_IMMEDIATE_MOVE: P58=21.0% Ctrl=8.7% Lift=+140.6%
TWO_SIDED_SWEEP_THEN_UP: P58=27.4% Ctrl=34.4% Lift=-20.5%
TWO_SIDED_SWEEP_THEN_DOWN: P58=26.8% Ctrl=30.9% Lift=-13.3%
COMPRESSION_NO_EXPANSION: P58=0.0% Ctrl=2.6% Lift=-100.0%
DOWN_BREAK_CONTINUATION: P58=2.1% Ctrl=4.2% Lift=-48.8%
DOWN_BREAK_FAILURE_TO_UP: P58=1.9% Ctrl=0.8% Lift=+129.8%
LATE_EXPANSION: P58=13.4% Ctrl=12.4% Lift=+7.8%
UP_BREAK_CONTINUATION: P58=2.8% Ctrl=1.8% Lift=+49.1%

--------------------------------------------
CLEANNESS
--------------------------------------------
NET DISPLACEMENT / TOTAL RANGE: P58=0.45 Ctrl=0.39
LARGEST EXCURSION / TWO-SIDED RANGE: P58=0.79 Ctrl=0.74
CLEAN UP (≥2 up, <1 dn): P58=15.9% Ctrl=6.4%
CLEAN DOWN: P58=14.3% Ctrl=10.6%
LARGE CHAOTIC (both ≥2): P58=41.0% Ctrl=52.3%
PHASE58 MOVEMENT IS CLEANER: YES

--------------------------------------------
ORIGINAL DIRECTION INFORMATION
--------------------------------------------
FIRST-SIDE ACCURACY: 81.1%
LARGEST-SIDE ACCURACY: 55.9%
CLEAN-EXPANSION ACCURACY: 73.2%
POST-SWEEP DIRECTION ACCURACY: 45.2%
INCREMENTAL VALUE OVER LOCATION ONLY: MODERATE

--------------------------------------------
PRE-EVENT CHARACTER
--------------------------------------------
COMPRESSION (5m/15m range): P58=0.64 Ctrl=0.67

--------------------------------------------
CONTROL / PLACEBO
--------------------------------------------
REAL abs_60m median: 6.43
PLACEBO abs_60m median: 6.50
EDGE REMAINS AFTER VOLATILITY MATCHING: NO

--------------------------------------------
WALK-FORWARD
--------------------------------------------
TRAIN: n=52,678 expansion_lift_60m=+0.22 clean_lift=+11.8% sweep_diff=-6.9%
VALIDATION: n=17,560 expansion_lift_60m=-0.45 clean_lift=+14.2% sweep_diff=-14.6%
HOLDOUT: n=17,560 expansion_lift_60m=-0.53 clean_lift=+16.3% sweep_diff=-16.5%

--------------------------------------------
PRACTICAL SIGNIFICANCE
--------------------------------------------
ABSOLUTE EXPANSION EDGE: NEGLIGIBLE
TWO-SIDED-SWEEP INFORMATION: MODERATE
PATH-CLEANNESS EDGE: LARGE
FIRST-BREAK CONTINUATION: MODERATE

--------------------------------------------
WHAT PHASE58 ACTUALLY DETECTS
--------------------------------------------
DIRECTION: WEAK
VOLATILITY EXPANSION: NONE
TWO-SIDED SWEEP: MODERATE
CLEAN EXPANSION: STRONG
GENERAL HIGH VOLATILITY ONLY: NO

--------------------------------------------
VERDICT
--------------------------------------------
PHASE58 LOCATIONS DIFFER FROM MATCHED CONTROLS: NO
DIFFERENCE IS PRACTICALLY MEANINGFUL: YES
PHASE58 IS A REAL LOCATION DETECTOR: NO / MARGINAL
PHASE58 IS PRIMARILY JUST A VOLATILITY DETECTOR: NO
FIRST-BREAK BEHAVIOR DESERVES TRADER RESEARCH: YES
TWO-SIDED-SWEEP BEHAVIOR DESERVES TRADER RESEARCH: YES
ORIGINAL DIRECTION SHOULD BE RETAINED: SOFT CONTEXT ONLY
READY TO DESIGN NEW TRADER ARCHITECTURE: YES
READY FOR PINE: NO
READY FOR LIVE TRADING: NO
READY FOR PHASE65: YES