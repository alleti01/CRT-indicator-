# Phase72A Data Source Parity

## PARITY A — Logic parity

Given identical OHLC/features, Python management ≡ independent sim ≡ Pine mirror.
Phase72 verified 36,174 trades, zero bar-level divergences.

## PARITY B — Chart parity

Python: LW/Databento NQ continuous 1M
TradingView: NQ1! (approximate)

**Procedure:** For each review window, compare OHLC **before** signals.
If OHLC differs → classify DATA_MISMATCH, not SIGNAL_LOGIC_FAIL.

Review windows: see `phase72a/checkpoints/09_ohlc.json`