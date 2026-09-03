# Feature Definition Audit

## Phase 43 source code trace

1. `phase35/features.py`: `ret_n = close.pct_change(n)` → `(close - close[n]) / close[n]`
2. `phase43/features.py`: `ret_n_atr = _dir_norm(ret_n * atr, direction, atr)`
3. `_dir_norm`: `(series * direction) / atr` → simplifies to `ret_n * direction`

Therefore:

**PHASE43 RET_1_ATR** = `((close / close[1]) - 1) * direction`
**PHASE43 RET_2_ATR** = `((close / close[2]) - 1) * direction`
**PHASE43 RET_3_ATR** = `((close / close[3]) - 1) * direction`

Note: NOT `(close - close[n]) / ATR * direction`. The `_atr` suffix cancels ATR in normalization.

## Phase 44 Pine

**PINE RET_N** = `((close / close[n]) - 1) * direction`

## EXACT FEATURE PARITY: YES

Verified numerically on all Phase 40 signals (`feature_parity_ok` column).
