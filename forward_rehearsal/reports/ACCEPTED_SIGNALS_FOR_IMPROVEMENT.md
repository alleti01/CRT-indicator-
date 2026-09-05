# Accepted Signals — Bot Improvement Dataset

These are **real TradingView webhooks the bot accepted and processed**. Use this to improve engine behavior, data feed, and alert payload quality.

- **Session:** `20260903T053410Z-fd28c0a3`
- **Unique accepted signals:** 12
- **LONG:** 6 | **SHORT:** 6
- **Shadow WOULD_ENTER:** 0
- **PASS_DATA_UNHEALTHY:** 12

## Key finding

**Every accepted signal was passed** because live market data was `DATA_MISSING` at decision time. Webhooks work; the **Databento live bar feed** is the main blocker before any shadow entries.

## Improvement priorities

1. **Live data feed** — ensure Databento delivers current 1m NQ bars when signals arrive
2. **Alert ATR** — currently hardcoded `1.0`; real ATR from Pine improves entry quality checks
3. **Entry quality gates** — once data is healthy, review WOULD_ENTER vs WOULD_PASS behavior

## Signal table

| signal_time_utc | dir | pine_price | engine_action | health | would_enter |
|-----------------|-----|------------|---------------|--------|-------------|
| 2026-09-04T06:32:00+00:00 | LONG | 29638.5 | PASS_DATA_UNHEALTHY | DATA_MISSING | NO |
| 2026-09-04T07:43:01+00:00 | LONG | 29637.25 | PASS_DATA_UNHEALTHY | DATA_MISSING | NO |
| 2026-09-04T08:32:01+00:00 | LONG | 29661.0 | PASS_DATA_UNHEALTHY | DATA_MISSING | NO |
| 2026-09-04T09:32:03+00:00 | SHORT | 29620.75 | PASS_DATA_UNHEALTHY | DATA_MISSING | NO |
| 2026-09-04T09:48:03+00:00 | LONG | 29635.75 | PASS_DATA_UNHEALTHY | DATA_MISSING | NO |
| 2026-09-04T12:24:02+00:00 | SHORT | 29641.75 | PASS_DATA_UNHEALTHY | DATA_MISSING | NO |
| 2026-09-04T12:35:00+00:00 | LONG | 29666.5 | PASS_DATA_UNHEALTHY | DATA_MISSING | NO |
| 2026-09-04T12:43:00+00:00 | SHORT | 29547.75 | PASS_DATA_UNHEALTHY | DATA_MISSING | NO |
| 2026-09-04T13:07:00+00:00 | SHORT | 29531.5 | PASS_DATA_UNHEALTHY | DATA_MISSING | NO |
| 2026-09-04T17:35:00+00:00 | SHORT | 29517.75 | PASS_DATA_UNHEALTHY | DATA_MISSING | NO |
| 2026-09-04T19:27:00+00:00 | SHORT | 29511.5 | PASS_DATA_UNHEALTHY | DATA_MISSING | NO |
| 2026-09-04T19:36:00+00:00 | LONG | 29523.5 | PASS_DATA_UNHEALTHY | DATA_MISSING | NO |

Full detail (Excel): `ACCEPTED_SIGNALS_FOR_IMPROVEMENT.csv`

Raw session logs: `forward_rehearsal/sessions/2026-09-03/20260903T053410Z-fd28c0a3/`
