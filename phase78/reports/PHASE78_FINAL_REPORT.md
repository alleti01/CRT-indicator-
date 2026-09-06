# Phase78 Final Report — ICT Silver Bullet (Independent Causal Validation)

**Verdict:** `PHASE78_NO_DIRECTIONAL_INFORMATION`

## Data
- Bars: 3140775
- Range: 2017-10-01 17:00:00-05:00 → 2026-09-02 10:48:00-05:00
- Symbol: NQ.v.0
- Continuous: Databento GLBX.MDP3 volume continuous (NQ.v.0)

## Causality
- PREFIX_PASS: True (201 checks, 0 mismatches)

## Funnel (window-level stages; multiple entries per window possible)
- WINDOWS: 6826
- SWEEP: 6826
- DISPLACEMENT: 6814
- MSS: 6017
- FVG: 3892
- RETRACE: 3892
- ENTRY_WINDOWS: 3825
- EXECUTABLE_ENTRIES: 6601

## Frequency
- Trading days: 2319
- Executable entries: 6601
- Entries/day: 2.846
- Entries/week: 14.23
- % days with ≥1 entry: 90.3%
- LONG: 1345 | SHORT: 5256

## Random Direction Gate
- Real +1R/-1R: 0.474
- Random mean: 0.494
- Flipped: 0.513
- Real percentile among random: 0.314
- Pass: False
- Note: Real direction underperforms random and flipped (symmetric 1R control stops)

## Path (means)
- +1R before -1R: 0.474
- +2R before -1R: 0.299
- +2.5R before -1R: 0.249
- MFE 15m: 19.47 | MAE 15m: 19.28

## Performance (2R target, structural stop, 60m max hold)
- Gross AvgR: -0.075
- N: 6601

## Costs
- Base net AvgR: -0.291
- 1.5x cost net AvgR: -0.399
- 2x cost net AvgR: -0.507

## Window comparison
- SB1: 2051 | SB2: 2453 | SB3: 2097
- Most opportunities: SB2

## Spec answers
1. Causal reconstruction: YES — prefix invariance audit
2. Eligible windows: 6826
3. Windows with sweep: 6826
4. Windows with displacement: 6814
5. Windows with MSS: 6017
6. Windows with FVG: 3892
7. Windows with retrace: 3892
8. Executable entries: 6601
9. % trading days with ≥1 entry: 90.3%
10. Avg entries/day: 2.846
11. Avg entries/week: 14.23
12. LONG 1345 / SHORT 5256
13. Most opportunities window: SB2
14. SB2 best: True
15. Real beats random: False (0.474 vs 0.494)
16. Margin vs random: -0.020
17. Real beats flipped: False (0.474 vs 0.513)
22. +1R/-1R: 0.474
23. +2R/-1R: 0.299
24. +2.5R/-1R: 0.249
29. Gross AvgR: -0.075
30. Net AvgR (base cost): -0.291
34. Train AvgR: -0.114
35. Validation AvgR: -0.042
36. Prev-exposed test AvgR: 0.008
37. Positive years: 2/10
38. Roughly daily opportunities: YES
39. Independently useful: NO — failed directional/cost gates
40. Forward testing warranted: NO
