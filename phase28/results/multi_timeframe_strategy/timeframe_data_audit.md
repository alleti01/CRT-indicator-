# Timeframe data audit

- Source: stitched local NQ **5m** OHLCV (3 files)
- Common comparison range: **2018-01-01 → 2026-06-26**
- Higher TFs built by causal aggregation from 5m (session-aware, no lookahead)
- No new Databento purchases

## Strategies included
- CONTROL
- RETEST_GATED
- BOS_ONLY
- SEQUENTIAL_BOS
- CRT_V2_B_LEGACY_EXP6

## Strategies excluded
- HIGH_EXPECTANCY (Phase 26 bar-level ML — not a standalone trade architecture; Classification D)
- ENTRY_PRECISION (Phase 24 ML ranker on frozen CRT — not a standalone architecture; Classification C)
