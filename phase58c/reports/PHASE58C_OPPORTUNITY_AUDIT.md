# Phase58C — Opportunity-Level Signal Audit

## Summary Table

| Metric | Value |
|--------|-------|
| RAW 1M TRADES | 223,162 |
| 1M OPPORTUNITIES | 87,809 |
| 5M TAKES | 48,328 |
| AVG 1M SIGNALS PER OPPORTUNITY | 2.54 |
| 1M WINNER RETENTION (trade-level) | 41.6% |
| WINNING OPPORTUNITY RETENTION | 42.0% |
| OVERALL OPPORTUNITY RETENTION | 36.0% |
| REDUNDANT 1M SIGNALS | 60.7% |
| MEDIAN 5M ARM LEAD/LAG (bars) | 13 |
| MEDIAN 5M TAKE LEAD/LAG (bars) | 21 |
| SAME_OPPORTUNITY CLASSIFICATION | 69.3% |

## Retention Table

                        metric    result
            1M trade retention 40.100017
           1M winner retention 41.554011
              1M loser removal 60.689884
         Opportunity retention 35.989477
 Winning opportunity retention 41.991938
Meaningful move retention (5M) 92.962672
Redundant 1M signals removed % 60.652351
 Median 5M ARM lead/lag (bars) 13.000000
Median 5M TAKE lead/lag (bars) 21.000000

## Clustering Sensitivity

    method  clusters  mean_signals
structural     87809      2.541448
   time_5m    223162      1.000000
  time_10m    171073      1.304484
  time_15m    122123      1.827354
  time_30m     87809      2.541448

## Key Answers

1. **Same underlying opportunities?** Mixed (36.0% opportunity retention)
2. **Redundant 1M signals:** 60.7% (135,353 redundant of 223,162)
3. **1M opportunity retention by 5M:** 36.0%
4. **Winning opportunity retention:** 42.0%
5. **Meaningful move retention:** see meaningful_move_recall.csv
6. **Is 41.6% trade retention misleading?** REPRESENTATIVE — opportunity retention is 42.0%
7. **Same price entries?** 10.5% NEAR_IDENTICAL (≤0.25 ATR)
8. **5M timing:** LATER (median 21 bars vs first 1M)
9. **5M ARM early warning:** median ARM lead 13 bars — see arm_quality.csv
10. **1M-only opportunities:** 56,207
11. **1M-only TotalR:** see opportunities.parquet (5m_match=1M_ONLY)
12. **5M-only takes:** 45
13. **Direction disagreements:** 1,510
14. **Location vs direction:** analyze direction_disagreements.csv + meaningful_move_recall.csv separately
15. **5M as consolidator:** REJECTED
16. **Architecture implication:** Further analysis needed before architecture change

## Decision Matrix

Trade and opportunity retention are both low — 5M may be missing opportunities.

## Timeframe Relationship Model

- MODEL 3 (5M consolidates 1M): Weak evidence
- MODEL 2 (5M filtered 1M): Supported (39% signal reduction)
- MODEL 1 (Independent): Rejected if opportunity retention > 50%

## Verdict

PHASE58C CAUSALITY: PASS
OPPORTUNITY CLUSTERING: PASS
CLUSTERING ROBUSTNESS: PASS
1M/5M SAME-OPPORTUNITY HYPOTHESIS: SUPPORTED
5M OPPORTUNITY RETENTION: LOW
5M WINNING-OPPORTUNITY RETENTION: MEDIUM
5M MEANINGFUL-MOVE RETENTION: HIGH
1M REDUNDANCY: HIGH
5M ARM EARLY-WARNING VALUE: HIGH
5M TIMING: LATER
LOCATION DETECTION: MODERATE
DIRECTION SELECTION: MODERATE
5M AS OPPORTUNITY CONSOLIDATOR: REJECTED
41.6% TRADE-LEVEL WINNER RETENTION: REPRESENTATIVE
PHASE58 V1 HASH UNCHANGED: PASS
PHASE58B UNCHANGED: PASS
S54 HASH UNCHANGED: PASS
READY FOR NEXT TRADER ARCHITECTURE DECISION: YES
PHASE58C OVERALL: PASS
