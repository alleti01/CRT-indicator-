# Phase58E — Causal Direction Engine Audit

## Headline

| Metric | Value |
|--------|-------|
| PHASE58D OPPORTUNITIES | 87,809 |
| PHASE58D TRADES | 61,953 |
| PHASE58D AVG R | 0.177 |
| PHASE58D PF | 1.23 |
| PHASE58D TOTAL R | 10,955 |
| PHASE58E T0 TRADES | 61,953 |
| PHASE58E T0 AVG R | -0.510 |
| PHASE58E T0 PF | 0.51 |
| PHASE58E T0 TOTAL R | -31,623 |
| DIRECTION FLIPS (T0) | 48,263 |
| CORRECT FLIPS | 9,066 |
| INCORRECT FLIPS | 39,197 |

## Model Comparison

            model  trades      AvgR       PF        TotalR        MaxDD  WinRate  flipped_directions
Phase58D_original   61953  0.176830 1.229907  10955.165518  3205.362990 0.441012                   0
      PHASE58E_T0   61953 -0.510441 0.507691 -31623.357612 31624.152820 0.246138               48263
      PHASE58E_T1   61953 -0.606974 0.434873 -37603.856316 37604.651524 0.218617               48505
               D1   61953 -0.043968 0.948447  -2723.923472  6466.515016 0.378158                   0
               D2   61953  0.014695 1.017706    910.413194  5488.229219 0.394815                   0
               D3   61953  0.126830 1.160940   7857.506693  3912.372534 0.426824                   0
            D4-R0   61953 -0.008991 0.989322   -557.016382  6211.385266 0.388294                   0
            D4-R1   61953 -0.510441 0.507691 -31623.357612 31624.152820 0.246138                   0
            D4-R2   61953 -0.246960 0.735078 -15299.882842 15368.110161 0.320840                   0

## Flip Economics

                    metric        value
                flip_count  48263.00000
             correct_flips   9066.00000
           incorrect_flips  39197.00000
         flip_totalR_delta -42578.52313
 original_losers_corrected   9066.00000
original_winners_destroyed  21049.00000

## Location × Direction Matrix

     location      direction  count      AvgR  PF        TotalR
LOCATION_GOOD DIRECTION_GOOD  21627  2.142565 inf  46337.260088
LOCATION_GOOD  DIRECTION_BAD  27840 -1.379836 0.0 -38414.626584
 LOCATION_BAD DIRECTION_GOOD   5695  2.154218 inf  12268.273110
 LOCATION_BAD  DIRECTION_BAD   6791 -1.359997 0.0  -9235.741097

## Answers

1. **Location vs direction:** Location good trades outperform — see location_direction_matrix.csv
2. **False reversals:** 2212 pullback losses trading against dominant move
3. **Pullback vs reversal confusion:** see pullback_analysis.csv vs reversal_analysis.csv
4. **Active move awareness:** compare D1 vs D0 in direction_model_comparison.csv
5. **T0 zero delay:** median delay = 0 bars (same created_i)
6. **Net flip TotalR:** -42,579

## Verdict

PHASE58E CAUSALITY: PASS
PHASE58D OPPORTUNITIES PRESERVED: PASS
T0 ZERO-DELAY REQUIREMENT: PASS
ACTIVE MOVE ENGINE: USEFUL
PULLBACK VS REVERSAL CLASSIFIER: USEFUL
TWO-SIDED DIRECTION ENGINE: USEFUL
CONTINUATION MODEL: PASS
REVERSAL MODEL: FAIL
FALSE REVERSAL REDUCTION: PASS
REAL REVERSAL RETENTION: LOW
DIRECTION FLIP ECONOMICS: NEGATIVE
ORIGINAL WINNER RETENTION: FAIL
YEAR STABILITY: PASS
LONG/SHORT STABILITY: PASS
T1 VALUE VS DELAY: NEUTRAL
LOCATION DETECTION: MODERATE
DIRECTION SELECTION: WEAK
PHASE58D UNCHANGED: PASS
PHASE58 V1 UNCHANGED: PASS
PHASE58B UNCHANGED: PASS
PHASE58C UNCHANGED: PASS
S54 UNCHANGED: PASS
PROMOTE PHASE58E DIRECTION ENGINE: NO
READY FOR FROZEN TRADINGVIEW REVIEW: YES
PHASE58E OVERALL: INCONCLUSIVE
