# Webhook Alerts — Full Analysis Log

All TradingView webhook POSTs captured via ngrok local inspect API.

## Summary

- **Total alerts:** 200
- **Accepted:** 48
- **Rejected:** 152

### Rejection reasons

- SIGNAL_STALE: 84
- WEBHOOK_INVALID: 68
- WEBHOOK_VALID: 48

### Issue categories

- static Jan 1 2026 timestamps (SIGNAL_STALE): 128
- none: 48
- literal REPLACE_* placeholders: 16
- signal_time_utc too old (>120s) — likely Time instead of Timenow: 4
- literal {{}} not substituted by TradingView: 4

## Fix reference

| Problem | Fix |
|---------|-----|
| REPLACE_NOW / REPLACE_* in payload | Add placeholder **Timenow** for signal_time_utc |
| 2026-01-01T00:00:00Z in payload | Same — use **Timenow** + **Time** placeholders |
| SIGNAL_STALE with real timestamps | signal_time_utc used **Time** (bar) not **Timenow** |
| Literal {{timenow}} in payload | Placeholders typed not inserted — redo via Add placeholder |

### Correct LONG message (after Add placeholder)

```json
{"schema_version":"1.0","strategy":"Phase72A","pine_hash":"d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f","signal_id":"{{timenow}}","event":"SIGNAL_LONG","symbol":"NQ","timeframe":"1m","signal_time_utc":"{{timenow}}","signal_bar_time_utc":"{{time}}","signal_price":"{{close}}","atr":"1.0","evidence":5,"context":"BULLISH","state":"IN_LONG"}
```

### Correct SHORT message

```json
{"schema_version":"1.0","strategy":"Phase72A","pine_hash":"d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f","signal_id":"{{timenow}}","event":"SIGNAL_SHORT","symbol":"NQ","timeframe":"1m","signal_time_utc":"{{timenow}}","signal_bar_time_utc":"{{time}}","signal_price":"{{close}}","atr":"1.0","evidence":5,"context":"BEARISH","state":"IN_SHORT"}
```

## All alerts (newest first)

| Time (ET) | Outcome | Event | Reason | Issue | Fix |
|-----------|---------|-------|--------|-------|-----|
| 2026-09-04 15:35:59 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 15:35:59 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 15:35:59 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 15:35:59 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 15:26:59 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 15:26:59 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 15:26:59 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 15:26:59 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 13:35:00 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 13:35:00 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 13:35:00 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 13:35:00 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 09:06:59 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 09:06:59 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 09:06:59 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 09:06:59 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 08:42:59 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 08:42:59 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 08:42:59 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 08:42:59 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 08:34:59 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 08:34:59 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 08:34:59 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 08:34:59 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 08:24:03 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 08:24:03 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 08:24:03 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 08:24:03 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 05:48:04 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 05:48:04 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 05:48:04 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 05:48:04 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 05:32:02 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 05:32:02 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 05:32:02 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 05:32:02 | ACCEPTED | SIGNAL_SHORT | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 05:10:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal {{}} not substituted by TradingView | Use Add placeholder: timenow for signal_ |
| 2026-09-04 05:10:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal {{}} not substituted by TradingView | Use Add placeholder: timenow for signal_ |
| 2026-09-04 05:10:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal {{}} not substituted by TradingView | Use Add placeholder: timenow for signal_ |
| 2026-09-04 05:10:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal {{}} not substituted by TradingView | Use Add placeholder: timenow for signal_ |
| 2026-09-04 04:32:01 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 04:32:01 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 04:32:01 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 04:32:01 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 03:43:00 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 03:43:00 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 03:43:00 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 03:43:00 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 02:32:00 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 02:32:00 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 02:32:00 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 02:32:00 | ACCEPTED | SIGNAL_LONG | WEBHOOK_VALID | none | no action needed |
| 2026-09-04 00:32:06 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | signal_time_utc too old (>120s) — likely Time inst | signal_time_utc must be {{timenow}}, not |
| 2026-09-04 00:32:06 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | signal_time_utc too old (>120s) — likely Time inst | signal_time_utc must be {{timenow}}, not |
| 2026-09-04 00:32:06 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | signal_time_utc too old (>120s) — likely Time inst | signal_time_utc must be {{timenow}}, not |
| 2026-09-04 00:32:06 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | signal_time_utc too old (>120s) — likely Time inst | signal_time_utc must be {{timenow}}, not |
| 2026-09-03 23:41:06 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 23:41:06 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 23:41:06 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 23:41:06 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 23:07:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 23:07:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 23:07:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 23:07:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 22:56:00 | REJECTED | SIGNAL_SHORT | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 22:56:00 | REJECTED | SIGNAL_SHORT | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 22:56:00 | REJECTED | SIGNAL_SHORT | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 22:56:00 | REJECTED | SIGNAL_SHORT | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 22:41:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 22:41:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 22:41:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 22:41:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | literal REPLACE_* placeholders | Use Add placeholder: timenow for signal_ |
| 2026-09-03 22:08:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 22:08:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 22:08:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 22:08:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 21:45:08 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 21:45:08 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 21:45:08 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 21:45:08 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 21:45:08 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 21:45:08 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 21:45:08 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 21:45:08 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 19:42:03 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 19:42:03 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 19:42:03 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 19:42:03 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 19:42:03 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 19:42:03 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 19:42:03 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 19:42:03 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 19:35:06 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 19:35:06 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 19:35:06 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 19:35:06 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 16:34:59 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 16:34:59 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 16:34:59 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 16:34:59 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 16:18:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 16:18:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 16:18:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 16:18:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 16:18:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 16:18:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 16:18:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 16:18:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:59:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:59:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:59:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:59:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:59:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:59:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:59:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:59:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:45:03 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:45:03 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:45:03 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:45:03 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:45:03 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:45:03 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:45:03 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:45:03 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:06:02 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:06:02 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:06:02 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:06:02 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:06:01 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:06:01 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:06:01 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 14:06:01 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:34:59 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:34:59 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:34:59 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:34:59 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:28:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:28:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:28:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:28:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:27:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:27:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:27:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:27:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:02:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:02:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:02:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:02:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:01:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:01:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:01:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 13:01:59 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:38:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:38:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:38:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:38:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:38:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:38:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:38:00 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:38:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:09:01 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:09:01 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:09:01 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:09:01 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:08:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:08:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:08:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 11:08:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 10:25:02 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 10:25:02 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 10:25:02 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 10:25:02 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 10:25:01 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 10:25:01 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 10:25:01 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 10:25:01 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 09:49:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 09:49:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 09:49:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 09:49:00 | REJECTED | SIGNAL_LONG | WEBHOOK_INVALID | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 09:48:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 09:48:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 09:48:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 09:48:59 | REJECTED | SIGNAL_LONG | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 07:34:02 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 07:34:02 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 07:34:02 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 07:34:02 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 07:09:00 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 07:09:00 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 07:09:00 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 07:09:00 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 06:59:00 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 06:59:00 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 06:59:00 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 06:59:00 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 05:51:02 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 05:51:02 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 05:51:02 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |
| 2026-09-03 05:51:02 | REJECTED | SIGNAL_SHORT | SIGNAL_STALE | static Jan 1 2026 timestamps (SIGNAL_STALE) | Replace static dates with Add placeholde |

Full payloads: WEBHOOK_ALERTS_FULL.csv