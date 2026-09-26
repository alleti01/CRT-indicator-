# CDXHistoricalBarExport (NinjaTrader 8)

Research-only 1-minute OHLCV dump for CDX label alignment.

- Does **not** replace or edit `CRTBarBridge`
- No TCP, no orders, no Phase74 wiring
- Writes `Documents\NinjaTrader 8\cdx_export\nq_1m_ninjatrader_sep6_sep21.csv`

## Chart requirements

- Instrument: the NQ continuous (or the same contract the CDX screenshots use)
- Bar type: 1 Minute
- Session: **CME US Index Futures ETH / Electronic** — not RTH-only
- Days to load: **>= 30** (warmup before Sep 6 plus Sep 6–21)
- `ChartTimeZoneId`: `Eastern Standard Time` if the chart displays America/New_York

Then compile (F5), add the indicator, wait for `closed rows=...`, re-run `Recover-CdxData.ps1`.
