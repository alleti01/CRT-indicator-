# Phase78B Final Report

**Verdict:** `PHASE78_SILVER_BULLET_NO_EDGE`

## Primary finding

Phase78 sweep rate was **100.0%** because the liquidity map places **163** levels (median) within **0.50 ATR** of window open, with nearest internal liquidity at **0.000 ATR** (median).

**39.9%** of first sweeps are **INTERNAL_SHORT_TERM** (swing/equal highs-lows); **60.1%** are external.

## Key answers

1. **Why 100% sweep?** Dense internal swing/equal levels within a few ticks of price; almost every window tags a nearby level on first bars.
2. **Internal-caused sweeps:** 100.0% windows sweep internal levels.
3. **External sweeps:** 89.7% windows.
4. **Most common first sweep:** CAUSAL_SWING_HIGH
5. **Nearest internal at open (median ATR):** 0.000
6. **Nearest external at open (median ATR):** 0.000
7. **Levels within 0.5 ATR (median):** 163
8. **Cluster inflation:** Yes — raw level count exceeds clustered count; multiple labels on same price band.
9. **Internal sweep speed (median min):** 0.0
10. **External sweep speed (median min):** 0.0
11. **External beats random +1/-1:** 0.445 vs 0.483 — NO
12. **Margin:** -0.038
13. **External beats flipped:** 0.445 vs 0.522
14. **Internal beats random:** 0.480 vs 0.497

21. **SHORT ~4x LONG:** Phase78 assigns SHORT on every buy-side (high) sweep; swing/session highs dominate sweep sources.
22. **Legitimate vs bug:** Implementation-driven asymmetry from sweep-side → direction mapping, not data artifact.
23. **101 invalid risk:** Stop on wrong side — entry occurred after price crossed structural stop (FVG retrace chase).
24. **Excluding invalid:** Gross AvgR unchanged materially (~-0.075).
25. **FVG entry late?** Median sweep→entry 1.0 minutes; significant move before entry.
26. **Phase78 invalid as selective raid test?** YES — 100% sweep rate proves map is not selective.
27. **Liquidity map over-inclusive?** YES — LIQUIDITY_MAP_OVERINCLUSIVE flag.
28. **Strict external test warranted?** Only if external subgroup beats random — it does NOT.
29. **Phase79 justified?** NO — external liquidity still fails directional gate.
30. **Final verdict:** PHASE78_SILVER_BULLET_NO_EDGE