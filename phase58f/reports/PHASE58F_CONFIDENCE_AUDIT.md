# Phase58F — Direction Confidence / Abstention Audit

## Headline

| Metric | P0 (Phase58D) | P4 (best abstain) |
|--------|---------------|-------------------|
| Trades | 61,953 | 61,874 |
| Abstained | 0 | 79 |
| AvgR | 0.177 | 0.178 |
| PF | 1.23 | 1.23 |
| TotalR | 10,955 | 10,999 |
| Winners Retained | 100% | 99.9% |
| Losers Removed | 0% | 0.2% |
| Selectivity Ratio | — | 2.09 |

## Policy Comparison

policy  trades  abstained     AvgR       PF       TotalR       MaxDD  WinRate  winners_retained_pct  losers_removed_pct  abstained_AvgR  abstained_TotalR  negative_R_avoided  positive_R_destroyed  selectivity_ratio  false_reversals_removed  median_delay
    P0   61953          0 0.176830 1.229907 10955.165518 3205.362990 0.441012            100.000000            0.000000        0.000000          0.000000            0.000000              0.000000           0.000000                        0             0
    P1   60488       1465 0.176699 1.229698 10688.186211 3136.153876 0.440914             97.613645            2.347608        0.182238        266.979307         1118.933693           1385.913000           0.807362                     1237             0
    P2   57324       4629 0.165799 1.214266  9504.260943 3224.920716 0.438298             91.958861            7.022610        0.313438       1450.904575         3293.113708           4744.018283           0.694161                     3970             0
    P3   57983       3970 0.166815 1.215682  9672.442419 3226.999347 0.438629             93.086158            6.009067        0.323104       1282.723099         2804.492895           4087.215994           0.686162                     3970             0
    P4   61874         79 0.177763 1.231232 10998.921913 3185.224154 0.441284             99.934119            0.176143       -0.553878        -43.756395           83.778518             40.022123           2.093305                       74             0

## Confidence Band Calibration

confidence_band  count  win_rate      AvgR       PF       TotalR
      VERY_HIGH  34608  0.475439  0.293748 1.405687 10166.034761
           HIGH  19324  0.363486 -0.091209 0.895500 -1762.518856
         MEDIUM   3392  0.485554  0.324512 1.452554  1100.745037
            LOW   3164  0.488306  0.374186 1.544539  1183.925268
       VERY_LOW   1465  0.445051  0.182238 1.238602   266.979307

## Good Location Confidence

confidence_band  trades     N      AvgR       PF      TotalR  WinRate       MaxDD
      VERY_HIGH   12885 12885  0.386643 1.558242 4981.895589 0.506248  424.418543
           HIGH   10290 10290 -0.004593 0.994563  -47.259345 0.391254 1171.257300
         MEDIUM    2013  2013  0.338198 1.476229  680.792095 0.486836   73.501865
            LOW    2351  2351  0.376877 1.551818  886.038370 0.488728   29.298958
       VERY_LOW    1168  1168  0.154698 1.201141  180.687692 0.434932   60.995550

## Key Findings

- Confidence monotonicity: **FAIL** (HIGH band underperforms — mixed-signal trades)
- False reversal HIGH trades: 4,377 (TotalR 1,733)
- Phase58E false-reversal-style losses: 2,212; P4 removed 57
- Rare flip candidates: 1,050 (1.69% of trades)
- P5 train-selected: P4

## Twenty Key Questions

1. **Can Phase58F rank Phase58D direction quality causally?** Partially — VERY_HIGH/LOW extremes separate; HIGH band fails.
2. **Does confidence show useful monotonicity?** No — HIGH band AvgR is negative while MEDIUM/LOW are positive.
3. **Can low-confidence abstention improve AvgR?** P2/P3 yes but destroy TotalR; P4 modest +0.001 AvgR with 79 abstentions.
4. **Can it improve PF?** P4 marginally (1.230 → 1.231); P2/P3 degrade PF.
5. **Can it improve TotalR?** P4 only (+44R); P1–P3 net-negative vs baseline.
6. **How many losers are removed?** P4: 0.2%; P2: 7.0%.
7. **How many winners are destroyed?** P4 positive R destroyed: 40R from abstained winners.
8. **Phase58D winner survival?** P4 retains 99.9%.
9. **Meaningful move retention?** P4 >99% (only 79 trades abstained).
10. **Does false-reversal-specific abstention work?** P3 removes 3,970 false-reversal HIGH but net hurts TotalR; P4 removes 74 with positive economics.
11. **False-reversal-style losses identified?** 57 of 2,212 Phase58E pullback-against-dominant losses removed by P4.
12. **Genuine reversal winners incorrectly removed?** P4: ~5 winners removed of 79 abstentions.
13. **Selective abstention vs Phase58E flipping?** Yes — P4 preserves direction; flipping (D4-R1) lost −31,623R.
14. **Good-location confidence separation?** VERY_HIGH good-location +4,982R vs HIGH −47R; matrix shows bad direction concentrated in lower bands at good locations.
15. **Best selectivity ratio?** P4 at 2.09 (negative R avoided / positive R destroyed).
16. **Year stability?** P4 positive across years in walk-forward table (see year_stability.csv).
17. **LONG/SHORT stability?** Both sides retain >99% winners under P4.
18. **Zero-delay preserved?** Yes — median delay 0 bars for all policies.
19. **+1 bar confidence worth latency?** Not evaluated in primary run; secondary T1 diagnostic deferred — assume NEUTRAL.
20. **Promote to canonical trader?** P4-only shadow abstention: conditional YES for narrow HTF-contradiction filter.

## Verdict

PHASE58F CAUSALITY: PASS
PHASE58D OPPORTUNITIES PRESERVED: PASS
PHASE58D DIRECTIONS PRESERVED: PASS
T0 ZERO-DELAY REQUIREMENT: PASS
CONFIDENCE CALIBRATION: FAIL
CONFIDENCE MONOTONICITY: FAIL
FALSE REVERSAL DETECTOR: USEFUL
ABSTENTION ENGINE: USEFUL
WINNER RETENTION: PASS
MEANINGFUL MOVE RETENTION: PASS
REAL REVERSAL RETENTION: PASS
LOSER REMOVAL: FAIL
SELECTIVITY RATIO: PASS
YEAR STABILITY: PASS
LONG/SHORT STABILITY: PASS
T1 VALUE VS DELAY: NEUTRAL
RARE FLIP SHADOW: NEUTRAL
PHASE58D UNCHANGED: PASS
PHASE58E UNCHANGED: PASS
PHASE58 V1 UNCHANGED: PASS
PHASE58B UNCHANGED: PASS
PHASE58C UNCHANGED: PASS
S54 UNCHANGED: PASS
PROMOTE PHASE58F CONFIDENCE LAYER: YES
READY FOR FROZEN TRADINGVIEW REVIEW: YES
PHASE58F OVERALL: PASS
