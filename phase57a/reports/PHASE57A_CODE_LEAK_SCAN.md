# Phase57A Code Leak Scan

Suspicious patterns: **12**

| File | Line | Description | Code |
|------|------|-------------|------|
| research/analysis.py | 122 | Global qcut — check if fitted on train only | `scored["decile"] = pd.qcut(scored["quality_score"], 10, labels=False, duplicates` |
| research/outcomes.py | 123 | Global max/min on full array (check scope) | `mfe = (hi[sl].max() - ep) / atr if atr > 0 else np.nan` |
| research/outcomes.py | 124 | Global max/min on full array (check scope) | `mae = (ep - lo[sl].min()) / atr if atr > 0 else np.nan` |
| research/outcomes.py | 126 | Global max/min on full array (check scope) | `mfe = (ep - lo[sl].min()) / atr if atr > 0 else np.nan` |
| research/outcomes.py | 127 | Global max/min on full array (check scope) | `mae = (hi[sl].max() - ep) / atr if atr > 0 else np.nan` |
| research/outcomes.py | 157 | Global max/min on full array (check scope) | `total_mfe = (hi[total_sl].max() - setup_price) / atr if atr > 0 else np.nan` |
| research/outcomes.py | 160 | Global max/min on full array (check scope) | `total_mfe = (setup_price - lo[total_sl].min()) / atr if atr > 0 else np.nan` |
| research/outcomes.py | 170 | Global max/min on full array (check scope) | `after = (hi[entry_i + 1:entry_end].max() - entry_price) / atr if entry_end > ent` |
| research/outcomes.py | 172 | Global max/min on full array (check scope) | `after = (entry_price - lo[entry_i + 1:entry_end].min()) / atr if entry_end > ent` |
| research/pullbacks.py | 96 | Global max/min on full array (check scope) | `holds = lo[start_i:deepest_i + 1].min() >= prior_swing` |
| research/pullbacks.py | 99 | Global max/min on full array (check scope) | `holds = hi[start_i:deepest_i + 1].max() <= prior_swing` |
| phase57/run.py | 87 | Global max/min on full array (check scope) | `print(f"  m1: {len(m1)} bars, {m1.index.min()} → {m1.index.max()}")` |