# Candidate filters

No skip is frozen.

N is 5, with one stop. A cut that isolates that stop would be fit to one trade. The natural checks below were defined as round structural tests, then measured. They are not live.

## F1_RECENT_WHIPSAW

Predicate: at least one confirmed LONG/SHORT flip inside the last 6 completed 3-minute bars.

Why it was measured: rapid alternation is the whipsaw hypothesis.

Historical result: flips_3, flips_6, and flips_10 are 0 on all five trades. The previous opposite confirmed signal was 42 to 349 completed 3-minute bars earlier. The 9:51 short was 147 bars after the prior opposite signal, inside that range.

STATUS: NOT_FROZEN. It does not describe the loser.

## F2_ADVERSE_FILL

Predicate, observation only: adverse displacement > 0. Positive means a long filled above the CDX entry, or a short filled below it.

Historical result: the 9:51 short filled 10.25 points above the CDX entry, so the displacement is -10.25. That is a better short fill, not a chase. All four TP1 trades filled worse than the CDX entry, by 0.50 to 14.50 points. A rule that skips adverse fills would drop the four winners and keep the loser.

STATUS: NOT_FROZEN. Shipping it would do the opposite of the intended filter.

## F3_RIBBON_CONFLICT

Predicate: none.

Ribbon values and higher-timeframe bias text were not stored at the signal time.

STATUS: UNAVAILABLE.

## What the sample does show, still as a hypothesis

On the last 6 completed 3-minute bars, the loser's efficiency was 0.36. The winners were 0.01 to 0.15. The loser was the more directional of the five, not the choppier one. Its 6-bar range was also the widest versus ATR. A low-efficiency or tight-range skip would have removed winners and left this stop in.

That is not a threshold. It is a reason not to revive the old chop skip from this sample.
