# Phase 17 causal regime definitions

All timestamps and regimes use `America/Chicago`. Values are attached at the
trade's entry-bar close, when the frozen engine enters.

- **Volatility:** ATR(14) divided by close. Low/medium/high are classified
  against the 33rd/67th percentiles of the preceding 17,280 five-minute bars
  (about 60 complete futures sessions), with a 1,000-bar minimum. Thresholds
  are shifted one bar, so the current bar does not classify itself.
- **Trend:** the already-validated Phase 16 previous-closed 60-minute HTF
  regime. It uses EMA(20), EMA(50), ATR(14), a 0.10 ATR neutral-width threshold,
  close/EMA alignment, and the prior fast-EMA slope. Values are bullish trend,
  bearish trend, or range/chop. No incomplete 60-minute bar is used.
- **Session:** the frozen exchange-local Phase 16 buckets. Report labels map
  Opening to Open, Morning to MidAM, and Afternoon to PM only for readability.
- **CRT distance:** absolute entry-price distance from the prior five-minute
  CRT boundary already calculated by Phase 16 (`crt_low` for longs and
  `crt_high` for shorts), normalized by entry ATR. This is descriptive and was
  not part of the frozen entry decision.

No future-derived outcome or bar is used in `trade_features.csv`.
