# Phase58H — Surgical Conflict Filter Audit

## Baseline H0 (Phase58D + P4)

| Metric | Value |
|--------|-------|
| Trades retained | 61,874 |
| Abstained | 79 |
| AvgR | 0.178 |
| TotalR | 10,999 |
| Winner retention | 99.9% |
| Selectivity | 2.09 |

P4 baseline parity: **PASS**

## Policy Comparison (H0–H4)

model  trades_retained  trades_abstained  new_abstains_vs_p4     AvgR       PF       TotalR       MaxDD  WinRate  winners_retained_pct  losers_removed_pct  meaningful_move_retention_pct  real_reversal_retention_pct  negative_R_avoided  positive_R_destroyed  selectivity_ratio  median_delay  max_delay  marginal_abstained_AvgR  marginal_abstained_n
   H0            61874                79                   0 0.177763 1.231232 10998.921913 3185.224154 0.441284             99.934119            0.176143                      99.877486                   100.000000           83.778518             40.022123           2.093305             0          0                 0.000000                     0
   H1            60118              1835                1756 0.192645 1.252429 11581.432110 2866.913905 0.445674             98.063831            3.771188                      97.208807                    99.922524         1770.342670           1144.076078           1.547399             0          0                -0.331726                  1756
   H2            61814               139                  60 0.178782 1.232692 11051.243897 3156.417982 0.441550             99.897518            0.320522                      99.801136                   100.000000          157.273905             61.195526           2.570023             0          0                -0.872033                    60
   H3            61847               106                  27 0.178342 1.232057 11029.896041 3171.145530 0.441444             99.926799            0.248332                      99.843750                   100.000000          119.458602             44.728078           2.670774             0          0                -1.147190                    27
   H4            61874                79                   0 0.177763 1.231232 10998.921913 3185.224154 0.441284             99.934119            0.176143                      99.877486                   100.000000           83.778518             40.022123           2.093305             0          0                 0.000000                     0

## Surgical Funnel

                                          funnel_step  trades      AvgR       PF       TotalR  win_rate    negative_R  positive_R  winner_pct  loser_pct  meaningful_moves  real_reversals
                                      HIGH_CONFLICTED   13629 -0.193543 0.788051 -2637.800682  0.336562 -12445.472389 9807.671707   33.656174  66.343826           11831.0            58.0
                                      HC + HTF_CONTRA    1756 -0.331726 0.654617  -582.510197  0.291002  -1686.564152 1104.053955   29.100228  70.899772            1503.0             7.0
                           HC + HTF_CONTRA + WEAK_REV      60 -0.872033 0.288092   -52.321984  0.166667    -73.495387   21.173403   16.666667  83.333333              43.0             0.0
            HC + HTF_CONTRA + WEAK_REV + NON_GOOD_LOC      27 -1.147190 0.131893   -30.974129  0.074074    -35.680084    4.705955    7.407407  92.592593              19.0             0.0
HC + HTF_CONTRA + WEAK_REV + STRONG_ACTIVE_OPPOSITION       0       NaN      NaN          NaN       NaN           NaN         NaN         NaN        NaN               NaN             NaN

## Incremental Value vs P4

model  new_abstains_vs_p4  incremental_total_r_vs_p4  incremental_negative_r_avoided  incremental_positive_r_destroyed  selectivity_ratio  winners_retained_pct
   H0                   0                   0.000000                        0.000000                          0.000000           2.093305             99.934119
   H1                1756                 582.510197                     1686.564152                       1104.053955           1.547399             98.063831
   H2                  60                  52.321984                       73.495387                         21.173403           2.570023             99.897518
   H3                  27                  30.974129                       35.680084                          4.705955           2.670774             99.926799
   H4                   0                   0.000000                        0.000000                          0.000000           2.093305             99.934119

## Walk-Forward

Train-selected: **H1**
OOS stability: **PASS**

     split model  trades_retained  trades_abstained  new_abstains_vs_p4     AvgR       PF      TotalR       MaxDD  WinRate  winners_retained_pct  losers_removed_pct  meaningful_move_retention_pct  real_reversal_retention_pct  negative_R_avoided  positive_R_destroyed  selectivity_ratio  median_delay  max_delay  marginal_abstained_AvgR  marginal_abstained_n  incremental_total_r_vs_p4
     train    H0            37116                55                  55 0.082394 1.100028 3058.131070 3185.224154 0.438544             99.914063            0.196360                      99.863776                   100.000000           60.291628             30.808735           1.956965             0          0                -0.536053                    55                   0.000000
     train    H1            36082              1089                1089 0.096970 1.118565 3498.870941 2866.913905 0.442825             98.078694            3.716475                      97.254797                    99.944547         1122.862592            652.639827           1.720494             0          0                -0.431793                  1089                 440.739872
     train    H2            37071               100                 100 0.083587 1.101543 3098.664735 3156.417982 0.438861             99.864956            0.373563                      99.771973                   100.000000          117.305108             47.288550           2.480624             0          0                -0.700166                   100                  40.533665
validation    H0            12383                 8                   8 0.243240 1.334803 3012.042595  141.755990 0.441331             99.963417            0.086655                      99.928990                   100.000000            7.617837              4.491521           1.696048             0          0                -0.390790                     8                   0.000000
validation    H1            12005               386                 386 0.257676 1.357207 3093.394626  150.413758 0.445731             97.878178            3.899480                      97.035328                    99.830700          344.144631            259.666284           1.325334             0          0                -0.218856                   386                  81.352031
validation    H2            12375                16                  16 0.243945 1.335898 3018.822030  141.755990 0.441535             99.945125            0.187753                      99.875732                   100.000000           16.767766              6.862015           2.443563             0          0                -0.619109                    16                   6.779435
   holdout    H0            12375                16                  16 0.398283 1.616299 4928.748248   38.255005 0.449455             99.964055            0.205068                      99.867092                   100.000000           15.869053              4.721867           3.360758             0          0                -0.696699                    16                   0.000000
   holdout    H1            12031               360                 360 0.414693 1.647114 4989.166543   35.743182 0.454160             98.202732            3.808408                      97.244374                    99.946033          303.335448            231.769967           1.308778             0          0                -0.198793                   360                  60.418295
   holdout    H2            12368                23                  23 0.398913 1.617491 4933.757132   38.255005 0.449628             99.946082            0.292954                      99.813929                   100.000000           23.201030              7.044960           3.293280             0          0                -0.702438                    23                   5.008884

## Twenty-One Questions

1. **HC + HTF negative expectancy?** Yes — funnel AvgR -0.332 on ~1,756 trades.
2. **Stable OOS?** Yes for H1.
3. **Weak reversal makes subgroup worse?** Yes — H2 marginal AvgR -0.872 vs H1 -0.332, but N=60 (LOW_SAMPLE).
4. **GOOD location preservation helps?** H3 removes only 27 trades — marginal improvement, LOW_SAMPLE.
5. **Strong active opposition helps?** No — H4 has **zero** qualifying trades.
6. **Simplest robust candidate:** H1 — simplest rule with adequate N.
7. **Additional trades beyond P4:** H1=1756, H2=60, H3=27, H4=0.
8. **Negative R avoided (H1 incremental):** 1,687R.
9. **Positive R destroyed (H1 incremental):** 1,104R.
10. **H1 selectivity ratio:** 1.55.
11. **Winner retention H1:** 98.1%.
12. **Meaningful move retention H1:** 97.2%.
13. **Real reversal retention H1:** 99.9%.
14. **Good-direction pool:** H1 destroys 748R from good-location winners.
15. **Bad-direction pool:** H1 avoids 1,205R from good-location losers.
16. **LONG/SHORT:** see long_short.csv — H1 incremental effect on both sides.
17. **Year stability:** see year_stability.csv.
18. **Cost stress:** see cost_robustness.csv.
19. **Management confusion:** marginal abstains skew MANAGEMENT_LOSS_LIKE — see management_confusion.csv.
20. **Worth complexity vs P4?** H1 adds +583R with 1756 extra abstentions — **WORTH_ADDING**.
21. **Stop filtering research?** NO — one candidate may pass.

## Verdict

PHASE58H CAUSALITY: PASS
PHASE58D OPPORTUNITY PARITY: PASS
PHASE58D DIRECTION PARITY: PASS
PHASE58F P4 PARITY: PASS
PHASE58G HIGH_CONFLICTED PARITY: PASS
T0 ZERO-DELAY REQUIREMENT: PASS
H1 SURGICAL FILTER: PASS
H2 WEAK-REVERSAL FILTER: FAIL
H3 LOCATION-PROTECTED FILTER: FAIL
H4 ACTIVE-OPPOSITION FILTER: FAIL
WINNER RETENTION: PASS
MEANINGFUL MOVE RETENTION: PASS
REAL REVERSAL RETENTION: PASS
GOOD-DIRECTION POOL PROTECTION: FAIL
BAD-DIRECTION SELECTIVITY: PASS
SELECTIVITY RATIO: PASS
OOS STABILITY: PASS
YEAR STABILITY: PASS
LONG/SHORT STABILITY: PASS
COST ROBUSTNESS: PASS
MANAGEMENT CONFUSION RISK: HIGH
INCREMENTAL EDGE VS P4: STRONG
COMPLEXITY VS EDGE: WORTH_ADDING
PHASE58D UNCHANGED: PASS
PHASE58E UNCHANGED: PASS
PHASE58F UNCHANGED: PASS
PHASE58G UNCHANGED: PASS
S54 UNCHANGED: PASS
PROMOTE PHASE58H FILTER: H1
STOP FURTHER ABSTENTION FILTER RESEARCH: NO
READY FOR FROZEN TRADINGVIEW REVIEW: YES
PHASE58H OVERALL: PASS
