# Phase 27 — Order-Flow Feature Definitions

All features are computed from Databento `trades` schema events with `ts_event <= 5m bar close` (America/Chicago).

## Aggressor flow (bar bucket)
- `buy_vol` — volume where `side == B` (buy aggressor)
- `sell_vol` — volume where `side == A` (sell aggressor)
- `delta` — buy_vol − sell_vol
- `delta_norm` — delta / total_vol
- `cum_delta_5m` — cumulative delta over pilot window (causal from start)
- `delta_accel` — delta − delta.shift(1)

## Trade intensity
- `trade_count`, `trades_per_sec`, `vol_per_sec`, `avg_trade_size`, `large_trade_pct`

## Causal rolling windows (30s, 1m, 2m, 5m, 10m ending at bar close)
- `delta_{window}s`, `delta_norm_{window}s`, `trades_per_sec_{window}s`

## Price response
- `price_change_atr` — 5m close change / frozen ATR
- `delta_price_response` — delta / ATR
- `flow_divergence` — delta_norm − price_change_atr

## OHLCV control (Model A)
- `body_atr`, `range_atr`, `close_location`, `ret_3_atr`, `ret_6_atr`, `volume_z`, `minute_of_day`, `day_of_week`
