# Winner retracement

Sample is every non-failure trade whose unmanaged structural-stop shadow reached at least +2R before the stop. N is 3 on the 5-bar stop and 4 on the 10-bar stop. Giveback is in frozen initial R, measured from the running favorable extreme after the threshold until the bar of the final MFE.

5-bar stop, N=3 at every threshold from +0.5R through +2R:

- median giveback 2.27R
- 25th 1.42R
- 75th 2.32R
- 90th 2.36R
- 1 of 3 traded back below entry after +0.5R, +1R, +1.5R, and +2R

10-bar stop, N=4:

- after +0.5R, +1R, and +1.5R: median giveback 2.31R, 25th 2.15R, 75th 2.55R, 90th 2.76R, 1 of 4 back below entry
- after +2R: median 2.31R, 25th 1.68R, 75th 2.55R, 90th 2.76R, 0 of 4 back below entry

A floor at breakeven after +1R would have been traded through on at least one of these shadows before the final MFE. The V1 ratchet did not do that on Thursday 1:51, because price kept going and the trade reached +2R first. The existing 10-point trail then exited near +2R and did not hold the 5R shadow. That cut is the live runner, not the +0.5R or +1R floor.

Thursday 8:21 on the 10-bar stop, without the early-failure rule, reached +1.5R and exited at the +0.25R floor for +20.6 points. It never got to the 498-point shadow extreme. The +1.5R floor took the profit. It did not turn the trade into a loss.
