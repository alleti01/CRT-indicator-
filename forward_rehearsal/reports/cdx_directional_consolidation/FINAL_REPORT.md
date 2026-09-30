VERDICT: INSUFFICIENT_NATIVE_CDX_COVERAGE

SUPPORTED TRADES: 5

NATIVE CDX COVERAGE: 5 of 5 confirmed MNQ signals had a broker fill inside 8 minutes. Test and fixture vision rows were excluded. The 2:56 PM long had no confirmed Entry/TP1 read, so it is not in V1-V4.

CURRENT CHOP EXIT RULE: There is no live rule that flattens because candles overlap. The live post-entry pullback rule is REVERSAL in phase74/quality/trail.py: after favorable excursion >= management risk (the CDX stop distance once the chart stop is on), a 10-point giveback from the extreme flattens. TIME_PROGRESS_15M_LT_1R exists and is configured off. SKIP_CHOP is pre-entry and filter_signals is false.

HOW MANY TIMES IT FIRED: 2 REVERSAL rows in the paper journal. 4 of the supported broker-fill trades reach that predicate on the broker fill path.

PREMATURE LEGACY EXITS: 4

Every one of those reversal exits had already traded TP1 before the 10-point giveback. The later TP1 touch is a revisit, not a trade that was cut during the chop before +0.50R. The model reversal price was within a few points of TP1, or beyond it. None of these reversals fired before +1 execution R.

USEFUL LEGACY EXITS: 0

The one CDX-stop loss never reached +0.50R, so the reversal rule was not armed and saved nothing. V2 loses the same stop.

V0 LIVE BASELINE

Trades: 3 resolved, 0 still open at data end, 2 without an exit price
Wins/losses: 1/2
Points: -6.50
Dollars: -210.00
Largest loss (points): -36.25
Largest winner (points): 35.75
Max DD (dollars): 507.50

V1 CDX NATIVE

Trades: 5 resolved, 0 still open at data end, 0 without an exit price
Wins/losses: 4/1
Points: 130.50
Dollars: 1177.00
Largest loss (points): -36.25
Largest winner (points): 67.25
Max DD (dollars): 507.50

TP1 hits: 4
SL hits: 1

V2 CDX +0.50R STRUCTURAL

Trades: 5 resolved, 0 still open at data end, 0 without an exit price
Wins/losses: 4/1
Points: 130.50
Dollars: 1177.00
Largest loss (points): -36.25
Largest winner (points): 67.25
Max DD (dollars): 507.50

TP1 hits: 4
Structural exits: 0

V3 + OPPOSITE CDX SIGNAL

Trades: 5 resolved, 0 still open at data end, 0 without an exit price
Wins/losses: 4/1
Points: 130.50
Dollars: 1177.00
Largest loss (points): -36.25
Largest winner (points): 67.25
Max DD (dollars): 507.50

Exits caused by opposite signal: 0

V4 + ENTRY/RIBBON RECLAIM

Available: NO

No numeric ribbon series is stored. The reclaim rule was not fabricated.

TODAY CASE STUDIES

Signal: 2026-09-28T11:42:00Z
Side: LONG
Entry: 30634.75
Fill: 30639.25
CDX SL: 30572.5
CDX TP1: 30705.5
Legacy exit: REVERSAL 2026-09-28T12:09:00+00:00
Broker exit: WICK_TARGET FLATTEN_FILL
+0.50R reached: YES 2026-09-28T12:06:00+00:00
TP1 touched before that legacy exit: YES
TP1 later reached after a reversal exit: YES
V2 result: TP1 at 2026-09-28T12:08:00+00:00 points 66.25

Signal: 2026-09-28T14:00:00Z
Side: SHORT
Entry: 30651.0
Fill: 30649.5
CDX SL: 30721.25
CDX TP1: 30582.25
Legacy exit: REVERSAL 2026-09-28T14:08:00+00:00
Broker exit: UNPRICED POSITION_FLAT_UNPRICED
+0.50R reached: YES 2026-09-28T14:06:00+00:00
TP1 touched before that legacy exit: YES
TP1 later reached after a reversal exit: YES
V2 result: TP1 at 2026-09-28T14:07:00+00:00 points 67.25

Signal: 2026-09-29T06:27:00Z
Side: LONG
Entry: 30508.25
Fill: 30508.75
CDX SL: 30478.75
CDX TP1: 30537.75
Legacy exit: REVERSAL 2026-09-29T06:34:00+00:00
Broker exit: REVERSAL FLATTEN_FILL
+0.50R reached: YES 2026-09-29T06:31:00+00:00
TP1 touched before that legacy exit: YES
TP1 later reached after a reversal exit: YES
V2 result: TP1 at 2026-09-29T06:32:00+00:00 points 29.00

Signal: 2026-09-29T13:51:00Z
Side: SHORT
Entry: 30591.75
Fill: 30602.0
CDX SL: 30638.25
CDX TP1: 30545.25
Legacy exit: none 
Broker exit: M0_STOP STOP_FILLED
+0.50R reached: NO 
TP1 touched before that legacy exit: NO
TP1 later reached after a reversal exit: NO
V2 result: CDX_SL at 2026-09-29T13:57:00+00:00 points -36.25

Signal: 2026-09-30T01:06:00Z
Side: SHORT
Entry: 30662.0
Fill: 30647.5
CDX SL: 30680.75
CDX TP1: 30643.25
Legacy exit: REVERSAL 2026-09-30T02:15:00+00:00
Broker exit: UNPRICED 
+0.50R reached: NO 
TP1 touched before that legacy exit: YES
TP1 later reached after a reversal exit: YES
V2 result: TP1 at 2026-09-30T01:14:00+00:00 points 4.25

TIME NEAR ENTRY

Zone is CDX Entry ± 0.15 execution R, counted on completed 3-minute closes until the V2 exit. Diagnostic only.
Median 3-minute bars near Entry on V2 TP1 trades: 0.0
Maximum: 3

CAUSALITY: PASS

PRODUCTION MODIFIED: NO

RECOMMENDED NEXT STEP: Keep collecting exact Entry, SL, and TP1 on live signals. Do not change the live stop or the 10-point reversal from this sample. The overlap of candles is not what flattened these trades.
