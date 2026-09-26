# Feature catalog (causal 1m OHLCV)

Built by `cdx_research/python/features.py`. Every feature at bar T uses only bars ≤ T.

HTF table from screenshots: **not used**.

## Families

| Family | Columns | Notes |
|---|---|---|
| Returns | `ret_1/2/3/5/10/20`, `log_ret_1`, `close_open`, `close_close_1` | Simple close/open changes |
| Candle | `body`, `body_frac`, `upper/lower_wick(_frac)`, `close_loc`, `bullish/bearish`, `inside/outside`, `engulf_*`, `consec_dir` | Structure only |
| Volatility | `tr`, `atr14`, `body_atr`, `*_atr`, `vol_expand`, `stdev20` | ATR period 14 |
| MA | `sma/ema_{5,8,9,10,13,14,20,21,34,50,100,200}`, distances in ATR, slopes, close crosses | Coarse lengths only |
| MA transition | `ema8_gt_ema21`, `ema8_cross_21_up/dn` | Fast/slow change |
| RSI | `rsi_{7,9,14,21}`, reclaim 30 / lose 70 | Wilder-style ewm |
| Structure | `roll_high/low_{5,10,15,20,30,50}`, distances, close-through, wick-through, near-extreme | Transitions vs T-1 |
| Range | `efficiency_10`, `overlap_1` | Path vs net |
| Volume | `rel_volume`, `vol_z`, `vol_rising` | 20-bar mean |
| Session | `rth`, `overnight` | NY 09:30–16:00 vs rest |

## Higher timeframe

Not computed in this pass. If added later:

- 5m / 15m / 1h must be aggregated from 1m
- A HTF bar is usable only after `known_at = floor(T, tf) + tf`
- Helper: `known_at_htf_close(index, minutes)`

## Smoke artifact

`features/all_bar_features.parquet` is the last **5 days of available research data** (ends 2026-09-02). It has **no CDX labels** (`cdx_target=0`). It exists to prove the library runs, not to score CDX.
