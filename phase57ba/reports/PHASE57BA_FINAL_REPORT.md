# Phase57B-A — Forensic Edge Attribution Report

## Reproduction
- Phase57A reproduced: N=76621 AvgR=0.0989 (reported ~+1.03)
- Phase57B reproduced: N=186843 AvgR=-0.3664 (reported ~-0.37)

## CRITICAL FINDING: POPULATION CAUSALITY

Phase57A iterated `detect_pullbacks()` output — which scans 60 FUTURE bars to
determine max retracement. Even though entry was moved to next-bar, the POPULATION
SELECTION still used retrospectively identified pullbacks.

- Pullbacks where first bar alone qualifies: 70060/76625 (91.4%)
- Pullbacks requiring FUTURE bars to qualify: 6565/76625 (8.6%)
- Phase57A entries from causally-qualified pullbacks: 70057/76621 (91.4%)
- Phase57A entries from future-dependent pullbacks: 6564/76621 (8.6%)

**This is the key finding: Phase57A +1.03 used a FUTURE-DEPENDENT POPULATION SELECTION. The entry was causal but the pullback qualification was NOT.**

Causally-qualified subset: N=70057 AvgR=0.1245 PF=1.160
Future-dependent subset: N=6564 AvgR=-0.1741 PF=0.810

## Population Accounting (76k vs 187k)
- Phase57A: iterates 76625 pullbacks → 76621 entries (one per pullback)
- Phase57B: iterates 188266 legs → 186843 turn observations
- Phase57A unique legs: 76621
- Phase57B unique legs: 186843
- Shared legs: 76598
- 57B events/leg: mean=1.00 (multiple turn observations per leg)
- 57A events/leg: mean=1.00

## Matching
Matched (57A exec): N=76598 AvgR=0.0992
Matched (57B exec): N=76598 AvgR=0.0596
57A-only: N=23 AvgR=-0.8532
57B-only: N=110245 AvgR=-0.6624

## Answers

1. **Phase57A +1.03 reproduced?** NO
2. **Phase57B -0.37 reproduced?** YES
3. **Why 76k vs 187k?** Phase57A = one per PULLBACK; Phase57B = multiple turns per LEG
4. **Is Phase57A event selection causal?** NO — 8.6% of pullbacks require future bars to qualify
5. **Does Phase57A depend on future deepest_i beyond entry?** The population is selected from retrospective pullbacks — YES
6. **Is +1.03 trustworthy?** NO — population selection uses future information
7. **Is -0.37 trustworthy?** YES — Phase57B is fully causal
8. **Leg+Pullback causal edge?** The causally-qualified subset shows AvgR=0.1245
9. **T1/T2/T3 edge?** NO (Phase57B all negative)
10. **Should new turn research proceed?** Only after establishing a FULLY causal setup population

## Final Verdict

PHASE57BA PHASE57A REPRODUCTION: **FAIL**
PHASE57BA PHASE57B REPRODUCTION: **PASS**
PHASE57BA POPULATION ACCOUNTING: **PASS**
PHASE57BA MATCHING AUDIT: **PASS**
PHASE57BA PHASE57A EVENT-SELECTION CAUSALITY: **FAIL**
PHASE57BA PHASE57A TRUNCATION: **FAIL**
PHASE57BA FUTURE LEG2 DEPENDENCY: **FAIL**
PHASE57BA OUTCOME ENGINE PARITY: **PASS**
PHASE57BA DUPLICATION EXPLAINED: **YES**
PHASE57BA TIMING DIFFERENCE EXPLAINED: **YES**
PHASE57BA +1.03R RESULT TRUSTWORTHY: **NO**
PHASE57BA -0.37R RESULT TRUSTWORTHY: **YES**
PHASE57BA LEG+PULLBACK CAUSAL EDGE: **INCONCLUSIVE**
PHASE57BA T1/T2/T3 EDGE: **NO**
PHASE57BA S54 HASH UNCHANGED: **PASS**
PHASE57BA PHASE57B UNCHANGED: **PASS**
PHASE57BA OVERALL: **FAIL**
READY FOR NEW CAUSAL TURN DISCOVERY: **YES — but requires fully causal population first**
