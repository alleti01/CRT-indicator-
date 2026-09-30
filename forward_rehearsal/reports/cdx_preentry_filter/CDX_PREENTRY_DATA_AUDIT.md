# CDX pre-entry data audit

Authority is the repository, not the earlier prose.

## Frozen trades

Five vision-confirmed MNQ signals with a broker fill inside 8 minutes. Timestamps are the vision `signal_id` values.

| Clock | signal_id | Side | CDX entry | Fill | CDX SL | TP1 |
| --- | --- | --- | --- | --- | --- | --- |
| Sep 28 7:42 AM ET | 2026-09-28T11:42:00Z | LONG | 30634.75 | 30639.25 | 30572.50 | 30705.50 |
| Sep 28 10:00 AM ET | 2026-09-28T14:00:00Z | SHORT | 30651.00 | 30649.50 | 30721.25 | 30582.25 |
| Sep 29 2:27 AM ET | 2026-09-29T06:27:00Z | LONG | 30508.25 | 30508.75 | 30478.75 | 30537.75 |
| Sep 29 9:51 AM ET | 2026-09-29T13:51:00Z | SHORT | 30591.75 | 30602.00 | 30638.25 | 30545.25 |
| Sep 29 9:06 PM ET | 2026-09-30T01:06:00Z | SHORT | 30662.00 | 30647.50 | 30680.75 | 30643.25 |

Fills and quantities come from `phase85/logs/audit.jsonl` entries that are immediately followed by `PROTECTION_SUBMITTED`.

## Outcome label

`TP1_BEFORE_SL` or `SL_BEFORE_TP1` from completed 1-minute bars in `phase74/logs/bars.csv`. The entry minute is excluded. If one bar trades both prices, the stop wins. This is not the broker exit.

Result: 4 TP1, 1 stop. The stop is the 9:51 AM short.

## What was available before the signal

Completed 1-minute bars whose close is at or before the signal timestamp. Three-minute bars are three consecutive clock-aligned minutes, and only a finished trio is used.

Confirmed signals for flip counts are `VISION_CONFIRMED` rows whose id starts with `2026-`. Fixture and test reads are excluded. Webhook alerts that vision did not confirm are not counted as flips.

## Unavailable

No numeric ribbon series is stored. No 1m/5m/15m/1h/4h/1D bias was captured at the signal time. Screenshots from the session are not in the repo. Those families are unavailable. They were not reconstructed.

## Sizing price

The CDX entry is known before the order, because the chart read happens before the send. No bid or ask is stored. Historical tables therefore show risk from the CDX entry and, separately, risk from the later fill. Live-capable sizing would use the CDX entry, not the fill.

## Production

`phase74/runtime/live_stack.py` still sizes from `contracts.default_quantity`. This research does not change that number, the stop, the target, or the reversal rule.
