# Stop diagnosis, Sep 22–26 2026

Rules were frozen before the replay. Structural stops use completed 3-minute bars before the signal bar, minus or plus 0.05 times ATR14. They are not moved to fit a dollar cap.

An 8-hour mark is used only when the structural stop is never touched. That mark is not a profit-taking rule. It is there because "structural stop only" defines no target. Those rows are labeled HORIZON_8H in `LAST_WEEK_REPLAY.csv`.

## A. Premature bot stops

Eight trades exited at the live stop. Three of them never touched the 10-bar or 20-bar structural stop in the next 8 hours, and the favorable move after the fill was larger than the bot's own risk.

| Trade | Bot stop | Points lost | 8h MFE | 10-bar stop hit? |
|---|---|---|---|---|
| Thu 1:51 AM short | 10.50 pts, −$210 | 10.50 | 288 pts | No |
| Thu 7:03 AM long | 10.75 pts, −$215 | 10.75 | 339 pts | No |
| Thu 8:21 AM long | 10.75 pts, −$215 | 10.75 | 326 pts | No |

That is 32.0 points, $640, cut off by the bot stop while the 10-bar and 20-bar stops were still intact.

The 5-bar stop did get hit on Thursday 7:03 (−18.2 pts) and Thursday 8:21 (−73.8 pts). Calling those two premature depends on using the wider lookback. Thursday 1:51 is premature on all three lookbacks: none of the structural stops were hit, and the 8-hour close was still +81.8 points.

## B. True failures

The structural stop broke, and price did not first travel a full bot-risk in favor.

| Trade | Bot result | 10-bar structural result |
|---|---|---|
| Thu 1:39 AM long | −8.75 pts, −$175 | −12.1 pts, −$242 |
| Thu 11:30 AM short | −14.25 pts, −$285 | −61.5 pts, −$1,230 |
| Fri 4:30 PM short | −13.00 pts, −$260 | −8.9 pts, −$178 |

Thursday 4:27 PM short lost only 1 point. It was not a full stop-out. A 10-bar structural stop later lost 120.2 points, $2,405.

## C. Ambiguous

The bot stop was inside a real bounce, and the structural stop was hit later.

Wednesday 1:04 AM short. Bot lost 4.50 points. Price then went 19.5 points in favor (about +4R of that stop) within 18 minutes. The 10-bar stop was hit afterward for −27.1 points, −$542.

Wednesday 2:07 AM long. Detail is in the main report. Bounce of +43 points, then a structural loss of about −31 points.

## D. Money left because the bot stop sat inside the move

On the three premature 10-bar cases, the bot booked −$640. The structural stop was not the thing that failed. The trades were still open 8 hours later, with marks of +81.8, +253.5, and +174.5 points. Those marks are not cash. They are the distance the tight stop gave up.

## E. Wider stops and true failures

On the true failures, a wider stop did not improve the loss except Friday's short, where the 10-bar stop was slightly tighter than the bot and lost $82 less.

Thursday 11:30 is the expensive one. The bot lost $285. The 10-bar stop lost $1,230. The 20-bar stop lost $2,570. That is a real failure made larger, not a premature stop that was saved.

Across all three lookbacks, the 8-hour marks that make the week look profitable come from trades whose structural stop was never touched. The 5-bar stop touches Thursday 7:03 and 8:21 and turns those "saves" back into losses. The lookback that leaves the stop untested is not automatically the lookback that found the invalidation.
