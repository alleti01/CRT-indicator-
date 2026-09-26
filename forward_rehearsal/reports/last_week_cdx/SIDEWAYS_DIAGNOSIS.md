# Sideways diagnosis, Sep 22–26 2026

Frozen V1, not tuned. On the 20 completed 3-minute bars before the signal:

- directional efficiency = net close change / sum of absolute close changes
- overlap = average of adjacent bar range overlap
- SIDEWAYS when efficiency is at or below 0.25 and overlap is at or above 0.60

This label does not skip a trade by itself.

## How many entries were sideways

12 of 15 signals were SIDEWAYS under that rule. The three that were not:

| Trade | Efficiency | Overlap | Range position | Actual result |
|---|---|---|---|---|
| Thu 11:30 AM short | 0.40 | 0.67 | 0.05 | −14.25 pts |
| Thu 12:24 PM long | 0.37 | 0.64 | 0.80 | +8.00 pts |
| Thu 4:27 PM short | 0.48 | 0.78 | 0.06 | −1.00 pt |

Of the complete sideways trades, the actual results were:

Winners: Thursday 8:03 AM short +19.0 pts. Friday 12:24 PM long about +9.75 pts, estimated.

Losers: Wednesday 1:04, Wednesday 2:07, Thursday 1:39, Thursday 1:51, Thursday 7:03, Thursday 8:21, Friday 4:30. Combined about −65.25 points.

## Hard skip

Skipping every sideways signal removes those winners and those losers.

- Winning points removed: 19.0 + 9.75 estimated = 28.75 points, about $575
- Losing points removed: about 65.25 points, about $1,305
- Net of the skip: about +36.5 points versus the actual book

The Thursday 8:03 short is the counterexample. It started sideways and it was a real +$380. A hard chop skip deletes it.

## Arm and wait

Armed entry keeps a sideways signal for up to 3 completed 3-minute bars and enters only on a close through the frozen range, or a close beyond the signal bar in the favorable direction when the signal is already at the favorable edge.

What it cancelled: Wednesday 1:04, Thursday 1:39, Thursday 7:03, Thursday 8:03, Thursday 8:21, Friday 12:24, Friday 4:30.

What it still took: Wednesday 2:07 (escape, then the structural stop, −26.6 pts) and Thursday 1:51 (escape, 8-hour mark +97.8 pts).

Compared with a hard skip, arming does not preserve the good chop trades. It cancels Thursday 8:03, the actual +$380, and Friday's estimated winner. It keeps Thursday 1:51, which is the clean premature stop, and it keeps Wednesday 2:07, which then loses more than the bot did.

The directional trades are unchanged by the arming rule, because they enter immediately. Thursday 12:24 stays. Thursday 11:30 and Thursday 4:27 stay, and both lose more under the structural stop than they lost live.
