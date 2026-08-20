# Retest-Reclaim forensic research report

## Scope and controls

- Data: development/parity window only, 2026-06-29 through 2026-08-18, America/Chicago.
- Bars: 10,164 five-minute bars.
- Unseen OOS data: not accessed.
- Production Pine: not modified.
- Frozen Python baseline: not modified.
- Cost basis: $14.50 round turn (one NQ tick of slippage per side plus $4.50 commission), converted to R trade by trade at $20/point.
- Regression suite: 31 tests passed.

## Forensic finding

FORENSIC CSV BUG? **YES**

STRATEGY LOGIC BUG? **NO**

The old `near_miss_shorts.csv` combined two different observations:

1. `would_be_confirmation_timestamp/close` came from a retrospective diagnostic proxy search for the first later bearish bar; when none existed, the code fell back to the retest/closest-level anchor bar.
2. `exact_rejection_reason` came from the candidate's real terminal state-transition bar.

That made a proxy close appear to contradict an invalidation threshold calculated on another bar. All 12 rows had a proxy timestamp different from the actual terminal timestamp.

### Why candidates 86 and 221 looked contradictory

- Candidate 86: retest accepted at 2026-07-16 13:55. The active `WAIT_CONFIRM` candidate was terminally invalidated at 14:00 when close 28,910.50 exceeded BOS + 0.10 ATR = 28,905.277121. The displayed 14:05 close of 28,867.00 was a later bearish proxy after the candidate was already IDLE.
- Candidate 221: retest accepted at 00:10. No later bearish bar was found in the diagnostic search window, so the exporter fell back to the 00:10 retest bar (close 29,825.25), even though it was not a later confirmation bar. The real `WAIT_CONFIRM` invalidation occurred at 00:20 when close 29,832.50 exceeded 29,828.123090.

The other requested confirmation-failure cases show the same mixed-bar issue:

- 250: actual terminal 17:00, close 29,250.50 > 29,243.410870; proxy 17:10.
- 149: actual terminal 02:40, close 27,116.25 > 27,107.485922; proxy 02:45.
- 252: actual terminal 19:25, close 29,213.00 > 29,199.212923; proxy 19:45.

The corrected audit and every five-minute bar from BOS through termination for all 12 candidates are in the workbook's `Forensic Audit` and `Bar Trace` sheets.

## Current causal ordering

The current short gate evaluates `WAIT_RETEST` in this terminal order:

1. Opposite BOS cancellation.
2. Close invalidation beyond BOS + 0.10 current-bar ATR.
3. Retest-touch acceptance.
4. Expiry.

It evaluates `WAIT_CONFIRM` in this order:

1. Opposite BOS cancellation.
2. Valid later bearish close below stored BOS, which enters.
3. Close invalidation beyond BOS + 0.10 current-bar ATR.
4. Expiry.

Therefore a retest candle that touches the band but also closes beyond its invalidation threshold terminates the candidate before any later bearish reclaim can be considered. That is the frozen rule behaving as written, not a stale-state or lookahead defect.

## Research-only RETEST_RECLAIM definition

The experiment used a separate state machine:

`Setup → BOS → later Retest touch → later directional BOS Reclaim → later existing Confirm → Entry`

- Same-bar Setup + matching BOS remains possible, matching the frozen feed.
- Retest must be after BOS.
- Reclaim must be after retest.
- Confirmation must be after reclaim.
- Temporary penetration is measured by close distance beyond stored BOS using current-bar ATR.
- Opposite BOS and maximum-penetration invalidations remain causal.
- Long is the exact directional mirror of Short.
- No future MFE/MAE participates in qualification or selection.

Exactly 20 preregistered cells were tested: penetration 0.10/0.20/0.30/0.40/0.50 ATR crossed with reclaim windows of 1/2/3/4 loaded bars.

## Current model

CURRENT RETEST MODEL (Setup → BOS → Retest → Confirm):

- Gross: N 42; wins 17; losses 25; WR 40.48%; AvgR 0.01088; TotalR 0.45709; PF 1.02152; MaxDD 8.03531 R.
- Net after costs: N 42; wins 17; losses 25; WR 40.48%; AvgR -0.00846; TotalR -0.35512; PF 0.98369; MaxDD 8.37128 R.

## Grid result

No cell produced positive net expectancy or net PF above 1.

- P0.10/W1: N 22; W/L 8/14; WR 36.36%; AvgR -0.14855; TotalR -3.26806; PF 0.73149; MaxDD 8.69227.
- P0.10/W2: N 29; W/L 10/19; WR 34.48%; AvgR -0.17326; TotalR -5.02453; PF 0.69270; MaxDD 9.86697.
- P0.10/W3: N 31; W/L 12/19; WR 38.71%; AvgR -0.06793; TotalR -2.10585; PF 0.87121; MaxDD 8.92540.
- P0.10/W4: N 31; W/L 12/19; WR 38.71%; AvgR -0.06793; TotalR -2.10585; PF 0.87121; MaxDD 8.92540.
- P0.20/W1: N 23; W/L 8/15; WR 34.78%; AvgR -0.18590; TotalR -4.27580; PF 0.67556; MaxDD 9.70001.
- P0.20/W2: N 30; W/L 10/20; WR 33.33%; AvgR -0.20108; TotalR -6.03227; PF 0.65249; MaxDD 10.87471.
- P0.20/W3: N 32; W/L 12/20; WR 37.50%; AvgR -0.09730; TotalR -3.11360; PF 0.82063; MaxDD 9.93314.
- P0.20/W4: N 32; W/L 12/20; WR 37.50%; AvgR -0.09730; TotalR -3.11360; PF 0.82063; MaxDD 9.93314.
- P0.30/W1: N 26; W/L 9/17; WR 34.62%; AvgR -0.21623; TotalR -5.62205; PF 0.63011; MaxDD 10.03884.
- P0.30/W2: N 35; W/L 13/22; WR 37.14%; AvgR -0.18172; TotalR -6.36032; PF 0.67179; MaxDD 10.96222.
- P0.30/W3: N 37; W/L 15/22; WR 40.54%; AvgR -0.09302; TotalR -3.44165; PF 0.82240; MaxDD 10.02065.
- P0.30/W4: N 37; W/L 15/22; WR 40.54%; AvgR -0.09302; TotalR -3.44165; PF 0.82240; MaxDD 10.02065.
- P0.40/W1: N 26; W/L 9/17; WR 34.62%; AvgR -0.21623; TotalR -5.62205; PF 0.63011; MaxDD 10.03884.
- P0.40/W2: N 35; W/L 13/22; WR 37.14%; AvgR -0.18172; TotalR -6.36032; PF 0.67179; MaxDD 10.96222.
- P0.40/W3: N 39; W/L 15/24; WR 38.46%; AvgR -0.14043; TotalR -5.47670; PF 0.74424; MaxDD 11.03284.
- P0.40/W4: N 39; W/L 15/24; WR 38.46%; AvgR -0.14043; TotalR -5.47670; PF 0.74424; MaxDD 11.03284.
- P0.50/W1: N 26; W/L 9/17; WR 34.62%; AvgR -0.21623; TotalR -5.62205; PF 0.63011; MaxDD 10.03884.
- P0.50/W2: N 35; W/L 13/22; WR 37.14%; AvgR -0.18172; TotalR -6.36032; PF 0.67179; MaxDD 10.96222.
- P0.50/W3: N 40; W/L 15/25; WR 37.50%; AvgR -0.16281; TotalR -6.51223; PF 0.70991; MaxDD 12.06837.
- P0.50/W4: N 40; W/L 15/25; WR 37.50%; AvgR -0.16281; TotalR -6.51223; PF 0.70991; MaxDD 12.06837.

The workbook contains average MFE/MAE plus long/short, score-band, session, and HTF-regime breakdowns for the current model and every cell.

## Quality leader and recovered trades

BEST RECLAIM VARIANT by the preregistered quality ordering (net PF, then lower MaxDD, then higher AvgR):

- Penetration: 0.10 ATR.
- Reclaim window: 3 bars.
- Net N 31; wins 12; losses 19; WR 38.71%; AvgR -0.06793; TotalR -2.10585; PF 0.87121; MaxDD 8.92540 R.
- It recovered zero previously rejected trades because its maximum penetration remained at the frozen 0.10-ATR width; it only added the later reclaim stage.

The strongest wider-penetration cell by net PF was P0.30/W3 (tied in results with W4):

- Recovered count 6; wins 3; losses 3; AvgR -0.22263; TotalR -1.33580; PF 0.55887.
- The maximum-recovery cell P0.50/W3 recovered 9; wins 3; losses 6; AvgR -0.48960; PF 0.27749.

Recovered frequency therefore increased, but recovered-trade quality was negative in every cell that recovered anything.

## Special 12 cases

All 12 are `NO_ENTRY` under the current model.

- 86 entered only in P0.30/W2-4, P0.40/W2-4, and P0.50/W2-4 at 2026-07-16 14:10; net result +0.25132 R.
- 149 entered only in P0.40/W3-4 and P0.50/W3-4 at 2026-07-30 02:55; net result -1.01219 R.
- 195 entered only in P0.50/W3-4 at 2026-08-11 00:50; net result -1.03553 R.
- 228, 250, 117, 72, 140, 84, 133, 252, and 221 remained `NO_ENTRY` in all 20 cells.

The `Special 12` sheet provides all 240 candidate-by-cell rows, including entry timestamp, gross/net R, trade MFE/MAE when an entry occurred, and the original diagnostic MFE/MAE when it did not.

## Final decision

ROBUST ACROSS NEIGHBORING PARAMETERS? **NO**

RECOMMEND FREEZING A RECLAIM VARIANT FOR NEW OOS? **NO**

The hypothesis did not improve the development result, and the recovered trades were not profitable as a cohort. No production or frozen-strategy change is supported by this experiment.

