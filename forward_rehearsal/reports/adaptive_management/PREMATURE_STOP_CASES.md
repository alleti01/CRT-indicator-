# Premature-stop cases

These three were premature against a 10-bar stop in the prior replay: the live stop was hit, and the 10-bar stop was not hit during the later favorable move. Classification here uses the adaptive exits, not an 8-hour mark.

## Thursday 1:51 AM short

Live −10.50 points, −$210. Shadow MFE 288 points (about 5.4R to 5.6R) before the structural stop eventually broke much later.

Full adaptive 5 and 10 both pass the 3-bar and 6-bar checks. They reach +0.5R, +1R, +1.5R, and +2R. The V1 ratchet does not stop them. After +2R the existing 10-point trail exits: +93.5 points on the 5-bar stop, +102.5 points on the 10-bar stop. The rest of the 288-point shadow is given back to that trail, not to the ratchet floors.

Class: SAVED_PREMATURE_STOP. The runner trail banks about +2R and leaves the larger shadow.

## Thursday 7:03 AM long

Live −10.75 points. 5-bar distance 18.2 points. Shadow MFE on that stop is 1.5 points, then the stop is hit. Full adaptive 5 loses the full −18.2 points. The 5-bar stop is still inside the same early noise as the bot.

10-bar distance 69.2 points, $1,384. Shadow MFE if the stop is left alone is 511 points, and the stop is not hit. Full adaptive 10 exits at the 3-bar checkpoint, −14.5 points, because MFE is 0.02R. The large move arrives after that checkpoint.

Class on full adaptive 10: STILL_LOST, and the early-failure rule is what blocks the later move. Ratchet-only, without the early exit, also fails to reach +0.5R of a 69-point R inside 60 minutes and the max-hold exits at −36 points while the close is not green.

## Thursday 8:21 AM long

Live −10.75 points. 5-bar distance 73.8 points. Full adaptive 5 exits early failure at −26.5 points. It never ratchets.

10-bar distance 82.5 points. Shadow MFE 498 points, stop not hit. Full adaptive 10 also early-fails at −26.5 points. Ratchet without the early exit reaches +1.5R and exits at the protected floor, +20.6 points. The early-failure rule is what kills that version. The +0.5R / +1R / +1.5R floors did not.

Class: full adaptive STILL_LOST. Ratchet-only on the 10-bar stop is a small save, and it does not keep the 498-point shadow.
