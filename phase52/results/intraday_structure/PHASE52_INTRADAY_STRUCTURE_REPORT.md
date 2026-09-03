# Phase52 Intraday Structure Report

## Executive summary
Walk-forward selected **G3 + C4 + RTH=True** (failed range-break / reclaim family with 15M range-location context).

## S52 OOS (stitched WF test periods)
| Metric | Value |
|--------|-------|
| N | 1885 |
| Trades/day | 0.798 |
| AvgR | 1.2114 |
| PF | 4.206 |
| TotalR | 2283.51 |
| MaxDD | 13.146 |

## S52-ONLY (non-overlapping CORE)
| Metric | Value |
|--------|-------|
| N | 1795 |
| AvgR | 1.1886 |
| PF | 4.085 |

## CORE overlap
- BOTH rate: 4.8%
- S52-ONLY retains positive expectancy: **YES**

## Portfolio
- CORE AvgR: 1.648 | CORE+S52 AvgR: 1.381
- Incremental portfolio value: **NO**
- Material DD increase: **NO**

## Robustness
- 2× cost AvgR: 1.0749 (PASS)
- Ex-top-1% AvgR: 1.1985 (PASS)
- Parameter stability (G3/C neighbors): **FAIL** — only G3+C4 positive; G3+C3 and G1+C4 collapse
- Year stability: PASS

## Verdict checklist
- PHASE52 CAUSALITY AUDIT: **PASS**
- BEST S52 FAMILY: **G3**
- BEST 15M CONTEXT: **C4**
- S52 LONG EDGE: **YES**
- S52 SHORT EDGE: **YES**
- S52-ONLY EDGE: **YES**
- DOES S52 CAPTURE MOVES CORE MISSES: **YES**
- DOES S52 ADD INCREMENTAL PORTFOLIO VALUE: **NO**
- SHOULD S52 ADVANCE: **NO — S52 = REJECTED** (parameter stability + portfolio AvgR dilution)
- READY FOR PINE: **NO**

## Most important finding
G3+C4 shows positive stitched OOS expectancy in isolation, but neighboring specs collapse immediately and combined CORE+S52 does not improve portfolio AvgR — insufficient robustness to promote S52. S52 = REJECTED.

CORE / Phase44 / B1 / Phase51 unchanged.
