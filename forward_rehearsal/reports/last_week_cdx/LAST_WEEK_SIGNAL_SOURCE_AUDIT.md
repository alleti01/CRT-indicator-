# Last-week signal source audit

Period: Monday Sep 22, 2026 through Saturday Sep 26, 2026, America/New_York.

No production orders were sent for this replay.

## Sources

| Priority | Source | What it supplied |
|---|---|---|
| 1 | `phase74/logs/signals.csv` | CDX webhook time, bar time, signal price, direction |
| 2 | `phase85/logs/audit.jsonl` | Live fill price and fill time |
| 3 | Account ledger already reconciled to those fills | Exit price and dollars when both prices exist |

The webhook `timeframe` field is `1m` on every row. That field is forced to `1m` so the bot will accept the alert. The CDX chart that fires the alerts is 3-minute. This replay treats the signal timeframe as 3-minute bars built from the 1-minute NinjaTrader bar log, and uses 1-minute bars only for path, MAE, and MFE after the fill.

3-minute bars are grouped on 180-second Unix buckets. A bar is completed when its bucket end is at or before the decision time. ATR14 is the simple average of the last 14 true ranges on those completed 3-minute bars.

Bar source: `phase74/logs/bars.csv`, written by the NinjaTrader bar bridge. Databento was not used.

## Signal versus fill

The signal minute and the fill minute are the same on every matched trade except Wednesday 10:56, where the webhook is one minute later. Confidence is high: the webhook exists, the direction matches, and the time gap is under one minute.

| Trade | CDX signal time (ET) | Signal price | Fill time (ET) | Fill | Source | Confidence |
|---|---|---|---|---|---|---|
| Tue 10:52 short | 10:52:00 | 30930.75 | 10:52 | 30926.75 | webhook + audit fill | High |
| Tue 3:12 long | 15:12:00 | 31001.50 | 15:12 | 31002.50 | webhook + audit fill | High |
| Wed 1:04 short | 01:04:00 | 31026.00 | 01:04 | 31025.50 | webhook + audit fill | High |
| Wed 2:07 long | 02:07:00 | 31051.00 | 02:07 | 31051.75 | webhook + audit fill | High |
| Wed 10:56 long | 10:57:00 | 30811.00 | 10:56 | 30810.50 | webhook + audit fill | High |
| Thu 1:39 long | 01:39:00 | 30691.75 | 01:39 | 30691.25 | webhook + audit fill | High |
| Thu 1:51 short | 01:51:01 | 30657.75 | 01:51 | 30658.00 | webhook + audit fill | High |
| Thu 7:03 long | 07:03:00 | 30488.75 | 07:03 | 30488.75 | webhook + audit fill | High |
| Thu 8:03 short | 08:03:00 | 30452.75 | 08:03 | 30455.00 | webhook + audit fill | High |
| Thu 8:21 long | 08:21:00 | 30500.00 | 08:21 | 30501.75 | webhook + audit fill | High |
| Thu 11:30 short | 11:30:00 | 30513.50 | 11:30 | 30512.75 | webhook + audit fill | High |
| Thu 12:24 long | 12:24:00 | 30687.00 | 12:24 | 30683.25 | webhook + audit fill | High |
| Thu 4:27 short | 16:27:00 | 30672.50 | 16:27 | 30671.75 | webhook + audit fill | High |
| Fri 12:24 long | 12:24:00 | 30859.75 | 12:24 | 30858.75 | webhook + audit fill | High |
| Fri 4:30 short | 16:30:00 | 30897.50 | 16:30 | 30897.75 | webhook + audit fill | High |

Fill time is not used as the CDX signal time. They match on the minute, and the signal price is the chart close, not the NinjaTrader fill.

## CDX displayed stop

No alert stored an exact CDX stop price. The Friday chart label was not treated as an exact native stop. `cdx_native_stop_if_known` is blank on every row.
