# Parameter mapping across timeframes

## A. Price/volatility based (unchanged)
- `trade_stop_atr=1.5`, `trade_target_r=2.0`, `p12_retest_atr_tolerance=0.10`
- ATR length = 14 bars on each timeframe

## B. Time-based (elapsed minutes preserved)
- `trade_max_minutes=60` → bars = 60/chart_minutes
  - 5m=12, 15m=4, 30m=2, 60m=1
- HTF regime remains **60-minute** wall clock

## C. Structural bar-count (unchanged)
- Pivots 5/5, `p12_expiry_bars=8`, `se_cooldown_bars=5`, sequential expiry=3, CRT V2 expiry=6
- These represent **different elapsed time** on higher TFs (documented, not rescaled)
