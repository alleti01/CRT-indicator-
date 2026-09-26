# Causality report

Test: for 500 random bars in the last available 5-day 1m window, compute features + candidate V1 on data truncated at T, vs the same T on the full window.

| Item | Result |
|---|---|
| Sampled | 500 |
| Mismatches | 0 |
| Status | **PASS** |
| Verdict | not `CDX_RE_CAUSALITY_FAIL` |

Columns checked: `atr14`, `rsi_14`, `ema_21`, `near_low_20`, `near_high_20`, `close_through_high_20`, `lower_wick_frac`, plus `candidate_v1`.

This proves **our** reconstruction path is causal on 1m rolling features. It does **not** prove CDX is causal or non-repainting.

HTF 5m/15m/1h features were not used (no Phase59 lookahead path).
