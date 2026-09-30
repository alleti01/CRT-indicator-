FILTER VERDICT: NO_CLEAR_PREENTRY_SEPARATION

SIZING VERDICT: NATIVE_STOP_SIZING_READY

SUPPORTED TRADES: 5

WINNERS: 4

LOSERS: 1

CAUSALITY: PASS

The 9:51 AM short is the only trade that hit the CDX stop before TP1. The features that sit outside the four winners point the wrong way for a chop filter: the loser was more efficient, had the wider recent range, had the smaller stop relative to ATR, and was filled better than the CDX entry. No skip was frozen.

9:51 AM LOSER

Side: SHORT

CDX Entry: 30591.75

Fill: 30602.00

CDX SL: 30638.25

TP1: 30545.25

Stop distance from fill: 36.25

1 MNQ full-stop risk: $72.50

Actual qty: 7 MNQ

Actual full-stop exposure: $507.50

From the CDX entry, before the fill, the stop is 46.50 points and 1 MNQ risks $93.00. A $75 cap rejects that planned entry. A $100 cap allows 1.

PRE-ENTRY FEATURE COMPARISON

| Feature | Loser | Winners | Separation |
| --- | --- | --- | --- |
| flips in last 3, 6, 10 bars | 0 | 0 to 0 | no |
| opposite signal, 3m bars earlier | 147 | 42 to 349 | no |
| efficiency, last 6 closes | 0.36 | 0.01 to 0.15 | yes, loser is higher |
| efficiency, last 10 | 0.45 | 0.30 to 0.59 | no |
| overlap, 6 and 10 | 0.75 / 0.67 | inside the winner span | no |
| ATR 14, 3m | 36.4 | 15.9 to 44.0 | no |
| 6-bar range / ATR | 3.60 | 0.98 to 2.55 | yes, loser is wider |
| 10-bar range / ATR | 4.94 | 2.22 to 4.39 | yes, loser is slightly wider |
| native stop / ATR | 1.28 | 1.18 to 2.43 | no |
| fill-stop / ATR | 0.99 | 1.35 to 2.60 | yes, loser is smaller |
| native stop, points | 46.50 | 18.75 to 70.25 | no |
| adverse fill, points | -10.25 | +0.50 to +14.50 | yes, loser is the favorable one |
| ribbon, HTF bias | unavailable | unavailable | unavailable |

AVAILABLE FEATURES: completed 3-minute efficiency, overlap, ATR, range, confirmed-signal flips, CDX stop and TP1 geometry, fill versus CDX entry.

UNAVAILABLE FEATURES: ribbon side, ribbon slope, ribbon width, entry inside the ribbon, 1m/5m/15m/1h/4h/1D bias text.

NEW FORWARD FIELDS REQUIRED: keep the available set on each new confirmed signal. Add a numeric ribbon and the higher-timeframe bias text only if the chart read can store the exact strings at signal time. Do not add a model judgment about the ribbon.

CANDIDATE FILTER F1: F1_RECENT_WHIPSAW

Predicate: one or more confirmed direction flips in the last 6 completed 3-minute bars.

Why it is being tested: whipsaw was the chop hypothesis.

Historical result: 0 flips on all five trades. It does not flag the 9:51 stop.

STATUS: NOT_FROZEN

CANDIDATE FILTER F2: F2_ADVERSE_FILL

Predicate: fill worse than the CDX entry.

Why it is being tested: chasing the CDX price was a possible failure mode.

Historical result: the loser was filled 10.25 points better than the CDX entry. The four winners were filled worse. The rule would skip the winners and take the loser.

STATUS: NOT_FROZEN

CANDIDATE FILTER F3: F3_RIBBON_CONFLICT

Predicate: none. Ribbon numbers were not stored.

STATUS: UNAVAILABLE

RISK SIZING

Dollars use $2 per MNQ point. Quantity is the floor of the cap divided by that risk. The CDX stop is not moved.

| Trade | Stop from fill | Actual qty | Exposure | $50 | $75 | $100 |
| --- | --- | --- | --- | --- | --- | --- |
| Sep 28 7:42 long | 66.75 | 5 | $667.50 | 0 | 0 | 0 |
| Sep 28 10:00 short | 71.75 | 5 | $717.50 | 0 | 0 | 0 |
| Sep 29 2:27 long | 30.00 | 5 | $300.00 | 0 | 1 | 1 |
| Sep 29 9:51 short | 36.25 | 7 | $507.50 | 0 | 1 | 1 |
| Sep 29 9:06 PM short | 33.25 | 7 | $465.50 | 0 | 1 | 1 |

Using the CDX entry instead of the fill, the 9:51 short is 46.50 points, $93 per MNQ: $50 and $75 reject, $100 allows 1. The 7:42 and 10:00 winners still reject at $100, because one MNQ already risks $124.50 and $140.50.

RISK REJECTION EXAMPLES

$50 on the 9:51 fill: quantity 0, RISK_MIN_CONTRACT_EXCEEDS_CAP, because $72.50 is above $50.

$75 on the 9:51 CDX entry: quantity 0, because $93 is above $75.

$150 on the 9:51 fill: quantity 2. That check is in the tests. It is not a recommended cap.

PRODUCTION ENTRY FILTER MODIFIED: NO

PRODUCTION POSITION SIZE MODIFIED: NO

LIVE STOP MODIFIED: NO

REVERSAL MODIFIED: NO

VISION EXECUTION: UNCHANGED

NEXT FORWARD BATCH: 20 qualifying signals

NEXT ACTION: Log the pre-entry row and the three risk tiers on each new confirmed signal. Do not skip or resize from this sample. Do not turn a low-efficiency rule back on. The 9:51 stop was the efficient trade in this set.
