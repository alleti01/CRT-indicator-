# Phase86 feature definitions

All features use only bars with `timestamp <= decision bar`. No future swings,
no right-side pivots, no MFE/MAE/outcome.

| FEATURE | FORMULA | LOOKBACK | KNOWN_AT | MISSING |
|---|---|---|---|---|
| range_width_20 | max(high) − min(low) on last 20 bars including T | 20 | close of T | none if <20 bars → no decision |
| range_atr_20 | range_width_20 / ATR | 20 | close of T | SKIP_DATA if ATR ≤ 0 |
| net_progress_20 | abs(close_T − close_{T−19}) | 20 | close of T | 0 if window short |
| total_path_20 | Σ abs(close_i − close_{i−1}) for i in window | 20 | close of T | 0 |
| directional_efficiency_20 | net_progress_20 / total_path_20 | 20 | close of T | 0 if path = 0 |
| overlap_20 (adjacent_overlap_ratio) | mean of pair overlap: max(0, inter) / union of consecutive [low, high] | 20 | close of T | 0 if no pairs |
| range_upper_prebreak | max(high of bars before T) in the 20-bar window | 19 prior | close of T−1 | none if <2 bars |
| range_lower_prebreak | min(low of bars before T) | 19 prior | close of T−1 | none if <2 bars |
| close_through | LONG: close_T > upper_prebreak + buf·ATR; SHORT: close_T < lower_prebreak − buf·ATR | 1 + prior 19 | close of T | false |
| false_break | LONG: high_T > upper and close_T ≤ upper; SHORT: mirrored | 1 + prior 19 | close of T | false |
| continuation_3_of_4 | ≥3 of last 4 bodies in trade direction | 4 | close of T | false if <4 |
| retest_hold | prior close-through of a wall frozen *before that bar*, later tag, all later closes hold outside | ≤8 bars | close of T | false |
| tight_chop | range_atr_20 < 2.0 (existing SKIP_CHOP uses full-20 box / ATR) | 20 | close of T | — |
| sideways_wide_range | range_atr ≥ 2 AND efficiency ≤ 0.25 AND overlap ≥ 0.45 | 20 | close of T | false |

Direction normalization: efficiency and overlap are unsigned. Escape and
false-break are direction-specific. 3-of-4 uses body vs trade direction.

Overlap uses union in the denominator (already frozen in
`phase74/quality/sideways.py`). Not mixed-candle count.

**Pre-break freeze:** the decision bar’s high/low cannot raise
`range_upper_prebreak` / `range_lower_prebreak`. Helper:
`capture_prebreak_boundary`.
