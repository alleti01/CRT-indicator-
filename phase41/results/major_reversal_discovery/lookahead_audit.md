# Lookahead Audit — Phase 41

## PASS

- **Opportunity labels** use future price action for ground-truth labeling ONLY. These labels are never used as model inputs.
- **Signal features** use only data available at the decision bar (close, past bars, ATR, EMA, session context to date).
- **Walk-forward discovery** trains thresholds on past folds only; OOS evaluation is stitched chronologically.
- **No future highs/lows** enter the causal trigger at fire time.
