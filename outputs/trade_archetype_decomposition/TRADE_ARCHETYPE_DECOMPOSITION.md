# Trade Archetype / Setup-Family Decomposition

## Executive summary

The complete 705-trade development baseline reproduced exactly with zero mismatches across every archived trade field. The analysis used only already-exposed 2024-01-01 through 2026-06-26 data, kept the $14.50 round-turn cost, and did not modify Pine or any frozen strategy component. Final classification: **D — STRATEGY HAS NO ROBUST EDGE**.

## Required final report

BASELINE REPRODUCED:
YES

705 TRADES VERIFIED:
YES

LONG:
N = 362
AvgR = -0.07919
TotalR = -28.66575
PF = 0.84813

SHORT:
N = 343
AvgR = -0.05943
TotalR = -20.38332
PF = 0.89483

SAME-BAR SETUP+BOS:
N = 664
AvgR = -0.06363
TotalR = -42.25108
PF = 0.88148

DELAYED BOS:
N = 41
AvgR = -0.16580
TotalR = -6.79798
PF = 0.73917

BEST STRUCTURAL FAMILY:
Definition = Short × Same-bar Setup+BOS × Penetration without same-bar reclaim
N = 31
Retention = 4.40%
AvgR = -0.03209
TotalR = -0.99481
PF = 0.94322
MaxDD = 3.97775R

COMPLEMENT:
N = 674
AvgR = -0.07130
TotalR = -48.05425
PF = 0.86836

YEAR STABILITY:
2024: N 17, AvgR -0.0992, TotalR -1.69, PF 0.8398; 2025: N 8, AvgR 0.4004, TotalR 3.20, PF 2.2771; 2026: N 6, AvgR -0.4187, TotalR -2.51, PF 0.4404

FIRST HALF:
AvgR = 0.05884
PF = 1.10626

SECOND HALF:
AvgR = -0.17606
PF = 0.69809

REMOVE TOP 1% WINNERS:
AvgR = -0.09941
TotalR = -2.98237
PF = 0.82977

WORST STRUCTURAL FAMILY:
Definition = Long × Same-bar Setup+BOS × Penetration + same-bar reclaim
N = 222
AvgR = -0.05899
TotalR = -13.09557
PF = 0.88441
Share of strategy losses = 29.62%

MULTIPLE-TESTING RESULT:
5 adequate-N structural families tested with two-sided Welch comparisons against their complements; 0 survived Benjamini-Hochberg FDR at 5%.

ROBUST ARCHETYPE FOUND:
NO

FINAL CLASSIFICATION:
D — STRATEGY HAS NO ROBUST EDGE

## Method and interpretation

Primary net baseline after costs: N 705, wins 284, losses 421, WR 40.28%, AvgR -0.06957, TotalR -49.05, PF 0.8718, MaxDD 60.30R.

The only three-dimension family definition tested was Direction × same-bar/delayed BOS × objective retest behavior. Retest behavior used the frozen BOS boundary without a fitted threshold: tolerance-only shallow touch, exact BOS touch, penetration with same-bar reclaim, or penetration without same-bar reclaim. Single-factor direction, frozen sessions, HTF regimes, actual setup triggers, liquidity context, CRT-bar sweep, timing, retest behavior, and causal volatility state are descriptive tables—not candidate searches.

MFE, MAE, exit, and outcome were used only as evaluation labels after the entry. No post-entry field defines any archetype. Families below N=30 remain visible but are labeled SMALL SAMPLE.

The decomposition does not rescue the negative larger-history expectancy. No entry filter or family exclusion should be implemented from this forensic phase.
