PHASE69A — WINNER PATH INTEGRITY AUDIT
======================================

ENTRY HASH: 0da41f282174679f
ENTRY PARITY: PASS
M0 PARITY: PASS
CAUSALITY: PASS

----------------------------------------
THE 73.2% DISCREPANCY
----------------------------------------
Phase69 claimed reaching +2.5R: 26,481 / 36,174 (73.2%)
M0 target exits: N = 10,432  % = 28.8%

ROOT CAUSE: Unconditional MFE_A — stop NOT enforced in Phase69 path_audit
POST-STOP CONTAMINATION: YES
POST-EXIT CONTAMINATION: YES (same mechanism — path not truncated at stop)
INDEXING ISSUE: MINOR (entry bar included in Phase69 slice)
OTHER: 'Stop held' was narrative only; never coded

----------------------------------------
FIRST-TOUCH ACCOUNTING
----------------------------------------
STOP_BEFORE_2P5: 25,508 (70.5%)
TARGET_2P5_BEFORE_STOP: 10,432 (28.8%)
SAME_BAR_STOP_AND_2P5: 81 (0.2%)
TIMEOUT_BEFORE_EITHER: 153 (0.4%)
DATA_END_BEFORE_EITHER: 0 (0.0%)
TOTAL: 36,174
M0 CONFUSION MATRIX PARITY: PASS (mismatches: 0)

----------------------------------------
MFE DEFINITIONS
----------------------------------------
UNCONDITIONAL FUTURE MFE: median=5.18 P75=9.78 P90=16.20
PRE-M0-EXIT MFE: median=0.97 P75=2.58 P90=3.11
STOP-ALIVE MFE: median=0.97 P75=3.09 P90=8.03

Pct reaching +2.5R:
  MFE_A: 73.2% | MFE_B: 29.1% | MFE_C: 29.2%

----------------------------------------
TRUE +2.5R WINNERS
----------------------------------------
N: 10,432  %: 28.8%
LONG: 5,692  SHORT: 4,740

----------------------------------------
AFTER TRUE +2.5R (denominator = TRUE_2P5_WINNER only)
----------------------------------------
Reach 3R peak: 94.3%
Reach 4R peak: 83.3%
Reach 5R peak: 72.9%
Reach 7R peak: 55.1%
Reach 10R peak: 35.4%
Median peak after 2.5R: 7.64R
P75: 12.32R
P90: 19.08R

----------------------------------------
FIRST-PASSAGE (after first +2.5R touch)
----------------------------------------
3 before 2: 43.5%
4 before 2: 13.6%
5 before 2: 6.5%
7 before 2: 3.0%
3 before 1.5: 56.0%
4 before 1.5: 27.4%
5 before 1.5: 17.8%
7 before 1.5: 10.6%
4 before 1: 43.1%
5 before 1: 31.3%
7 before 1: 20.4%

----------------------------------------
GIVEBACK REQUIRED (median R from peak before threshold)
----------------------------------------
To reach 4R: median giveback 0.63R  P90 4.11R
To reach 5R: median giveback 1.41R  P90 5.12R
To reach 7R: median giveback 2.38R  P90 6.69R
To reach 10R: median giveback 3.31R  P90 7.79R

----------------------------------------
TIME TO EXTENSION (minutes from first +2.5R)
----------------------------------------
2.5→4R: median 6m  P75 20m  P90 48m
2.5→5R: median 14m  P75 35m  P90 66m
2.5→7R: median 30m  P75 58m  P90 85m
2.5→10R: median 46m  P75 74m  P90 96m

IMMEDIATE CONTINUATION:
  ret_1m median: 0.000R
  ret_5m median: -0.110R
  new extreme within 3m: 99.8%
  new extreme within 5m: 99.9%

----------------------------------------
RUNNER RISK (retrace before extension target)
----------------------------------------
Retrace to 2.0R before 5R: 91.1%
Retrace to 1.5R before 5R: 75.6%
Retrace to 1.0R before 5R: 57.3%
Retrace to 0.0R before 5R: 33.5%
Retrace to -1.0R before 5R: 20.5%

----------------------------------------
PARTIAL RUNNER FEASIBILITY
----------------------------------------
100% @ 2.5R: 2.50R (after cost)
Option B full runner median R: -1.00R
Costs included: YES

----------------------------------------
MARKET OPEN (09:30–10:30 NY)
----------------------------------------
TRUE 2.5 winner rate: 28.5% (open) vs 28.9%
2.5→4 before 1.5: open 29.7% | non-open 27.3%
2.5→5 before 1.5: open 18.6% | non-open 17.8%
2.5→7 before 1.5: open 10.9% | non-open 10.6%

----------------------------------------
YEAR STABILITY
----------------------------------------
2017: TRUE_2P5=28.3%  5→1.5=23.8%  7→1.5=14.9%
2018: TRUE_2P5=28.4%  5→1.5=17.6%  7→1.5=10.9%
2019: TRUE_2P5=28.2%  5→1.5=16.6%  7→1.5=10.2%
2020: TRUE_2P5=28.4%  5→1.5=17.5%  7→1.5=10.2%
2021: TRUE_2P5=29.4%  5→1.5=16.5%  7→1.5=9.2%
2022: TRUE_2P5=28.2%  5→1.5=16.3%  7→1.5=9.5%
2023: TRUE_2P5=28.9%  5→1.5=18.8%  7→1.5=11.5%
2024: TRUE_2P5=28.5%  5→1.5=18.0%  7→1.5=10.5%
2025: TRUE_2P5=30.8%  5→1.5=17.8%  7→1.5=10.9%
2026: TRUE_2P5=28.6%  5→1.5=20.6%  7→1.5=12.0%

----------------------------------------
CENTRAL ANSWERS
----------------------------------------
WAS PHASE69 MFE ACCOUNTING CORRECT: NO
WAS 73.2% A TRADEABLE 2.5R RATE: NO
DO TRUE 2.5R WINNERS FREQUENTLY CONTINUE: YES (94% touch 3R peak; first-passage lower)
DO THEY CONTINUE BEFORE LARGE GIVEBACK: PARTIAL (17.8% hit 5R before 1.5R retrace)
IS A FULL-POSITION RUNNER JUSTIFIED: NO (Option B high variance; M0 2.5R lock preferred)
IS A SMALL PARTIAL RUNNER PLAUSIBLE: YES / NEEDS NARROW TEST
IS MARKET OPEN SPECIAL: NO

----------------------------------------
FINAL VERDICT
----------------------------------------
PATH ACCOUNTING: PASS
RUNNER OPPORTUNITY: RUNNER_OPPORTUNITY_CONFIRMED

BEST NEXT RESEARCH DIRECTION:
FULL TRAIL: NO
LARGER FIXED TARGET: NO (frontier already tested in Phase69)
SMALL PARTIAL RUNNER: NO
CHANGE ENTRY: NO
PINE CHANGE: NO
LIVE CHANGE: NO

NEXT STEP: If runner confirmed, narrow test 75/25 or 80/20 with 1.5R–2R protection on PREVIOUSLY_EXPOSED_HOLDOUT only

RECENT DATA: RECENT_TV_TRADE_NOT_IN_LOCAL_DATA (local data ends 2026-08-28 14:18:00-05:00)
Runtime: 228s