# True-failure cases

The question is whether early failure or the ratchet cuts these before the full structural loss, and whether that cut is actually smaller than the live loss.

## Thursday 1:39 AM long

Live −8.75 points. Structural distance is 12.1 points on both lookbacks. Shadow MFE is 7.2 points, 0.60R, then the stop is hit.

Early failure does not fire. MFE gets through 0.15R. The +0.5R ratchet does fire, and the stop exits at −3.0 points, −$61, instead of −12.1 points. That is tighter than the live loss too. It does not become a winner.

## Thursday 11:30 AM short

Live −14.25 points. 5-bar distance 46.5 points, $930. 10-bar distance 61.5 points, $1,230. Shadow MFE is only 10.2 points.

No ratchet. The 6-bar no-progress rule exits at −25.0 points, −$500, on both full adaptive versions. That is much smaller than the structural loss and larger than the live loss. The adaptive exit does not beat the bot here. It only beats leaving the wide stop on.

## Friday 4:30 PM short

Live −13.00 points. 5-bar distance is 2.7 points. 10-bar distance is 8.9 points. Both are inside the live stop. MFE is about 0 to 0.2 points. The structural stop is hit before either checkpoint. Full adaptive loses −2.7 points or −8.9 points. Neither is an enlarged structural loss. The early-failure rule never gets a turn.
