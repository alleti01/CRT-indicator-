# Good-trade damage, Sep 22–26 2026

Baseline winners are the live results, not the 8-hour marks. A rule damages a winner when it cancels the trade or turns it into a loss. 10-bar structural stop. R uses that stop's distance.

## Thursday 8:03 AM short, live +19.0 pts, +$380

| Rule | Alternative | Points given up versus live |
|---|---|---|
| 5-bar structural stop | Stop hit, −7.3 pts | 26.3 pts, about $526 |
| 10-bar structural stop | Stop hit, −47.0 pts | 66.0 pts, about $1,320 |
| 20-bar structural stop | Stop hit, −58.8 pts | 77.8 pts, about $1,556 |
| Sideways armed entry | Cancelled | 19.0 pts, about $380 |
| 3-bar and 6-bar progress rules | Not what closed it. The structural stop was hit first | — |

The live exit was a flatten one minute after entry, while price was in favor. Holding to the structural stop gave that profit back and then lost.

## Thursday 12:24 PM long, live +8.0 pts, +$160

Not sideways. Armed entry does not delay it. The 10-bar stop was not hit in 8 hours. The 8-hour close is +35.8 points. The progress rules do not apply. This winner is not damaged. The structural risk on this entry is 178.8 points, $3,576 per NQ, because the 10-bar low is far under the fill.

## Friday 12:24 PM long, estimated +9.75 pts, about +$195

Sideways. Armed entry cancels it. That removes the estimated winner.

The 5-bar stop is already above the fill (30892 versus 30858.75), so a long is through that stop at entry. The 10-bar and 20-bar stops were not hit in 8 hours. Progress management did not fire. The damage on this winner comes from the armed-entry cancel, not from the progress exit.

## Shadow runners that are not live winners

Thursday 1:51, 7:03, and 8:21 lost money live. Under a 10-bar stop they were still open 8 hours later. Armed entry cancels 7:03 and 8:21, so the full state machine does not participate in those shadows. It keeps 1:51. That is reported so the cancel is visible. They are not counted as damaged live winners, because the live book lost on them.
