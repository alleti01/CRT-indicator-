# Phase57A E0 Causality Report

## CRITICAL FINDING: E0 CONTAINS RETROSPECTIVE LOOKAHEAD

### What triggers E0?
E0 enters at `pullback.deepest_i` — the bar of maximum retracement after Leg1.

### How is deepest_i determined?
`detect_pullbacks()` scans 60 bars forward from `leg.end_i + 1`, tracking maximum
retracement. The bar with max retrace becomes `deepest_i`. This requires seeing
ALL bars in the window, including those AFTER the pullback extreme.

### Is E0 known at E0?
**NO.** At bar `deepest_i`, the algorithm cannot know this is the maximum
retracement without seeing future bars. 97.0% of pullbacks have scan
window extending past `deepest_i`.

### Truncation test result
Parity: **100.0%** — removing future bars changes deepest_i
selection in 0 of 500 sampled cases.

### Does future Leg2 information influence E0?
YES — the scan sees bars where price reverses (Leg2 start), which is what
identifies the previous bar as the "deepest" point.

### Impact
| View | N | AvgR | PF |
|------|---|------|-----|
| RAW E0 (retrospective) | 76622 | 1.5539 | 7.557 |
| Causal next-bar | 76621 | 0.0989 | 1.125 |

### Conclusion
**E0 CAUSALITY: FAIL** — pullback deepest point is a retrospective label.
