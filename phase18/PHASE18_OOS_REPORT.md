# Phase 18 — final unseen out-of-sample validation

## Scientific status

This was a one-time validation of the exact Phase 17 C1/C2 specifications. No Pine code, Phase 16 rule, Phase 17 candidate, threshold, filter, session, entry, stop, target, or scoring rule was changed. Phase 18 is now sacred observed data and may not be reused as OOS after any redesign.

## Data and baseline gates

- Baseline reproduction: **PASS** (exact model CSV, completed-trade CSV, and frozen-candidate SHA-256 matches).
- Databento: `GLBX.MDP3`, `ohlcv-1m`, continuous `NQ.v.0`.
- Cost estimate: **$3.9816**.
- Final unseen evaluation: **2021-01-01 through 2023-12-28 inclusive**, America/Chicago.
- OOS five-minute bars: **212,019**; raw one-minute rows: **1,090,620**.
- Data-validation gate: **PASS**; zero duplicate bars, zero invalid OHLC, zero adjusted roll gap, 13 provider rolls, zero development overlap.
- The preferred December 31 endpoint was shortened because the New Year closure supplied no bars to its end-exclusive boundary without entering 2024. See `data_validation.md`.

## Frozen model results

- Control: N 3,325; wins 1,366; losses 1,952; flat 7; win rate 41.08%; Avg R 0.0040; Total R 13.36; PF 1.008; Max DD 111.10R.
- BOS: N 2,283; wins 950; losses 1,329; flat 4; win rate 41.61%; Avg R 0.0184; Total R 41.95; PF 1.036; Max DD 55.72R.
- C1 (Control + Short + Premarket): N 414; wins 150; losses 263; flat 1; win rate 36.23%; Avg R -0.0372; Total R -15.40; PF 0.937; Max DD 43.25R.
- C2 (BOS + Short + score 90–94): N 469; wins 178; losses 290; flat 1; win rate 37.95%; Avg R 0.0126; Total R 5.92; PF 1.022; Max DD 20.73R.
- Retest reference: N 1,269; wins 517; losses 748; flat 4; win rate 40.74%; Avg R -0.0203; Total R -25.77; PF 0.961; Max DD 74.89R.
- Confirm reference: N 839; wins 333; losses 501; flat 5; win rate 39.69%; Avg R -0.0436; Total R -36.57; PF 0.917; Max DD 56.74R.

Full expectancy uncertainty, trade dispersion, drawdown duration, recovery factor, streaks, and time-count metrics are in `model_comparison.csv`.

## Annual stability

- Control: 2021 -3.41R; 2022 -50.32R; 2023 67.08R
- BOS: 2021 34.81R; 2022 -2.40R; 2023 9.55R
- C1: 2021 -6.38R; 2022 -23.89R; 2023 14.87R
- C2: 2021 14.59R; 2022 -10.30R; 2023 1.63R

Monthly, quarterly, and annual tables include all calendar periods, including zero-trade periods, in their respective CSV files.

## Execution-cost stress

NQ conversion uses $20/point and $5/tick. The predeclared standard conservative case is two ticks per side plus $8.00 round-turn commission ($28/trade). Severe is three ticks per side plus $10 ($40/trade); extreme is four ticks per side plus $12 ($52/trade).

- C1: Ideal/current -15.40R/PF 0.937; Modest -32.28R/PF 0.874; Standard conservative -47.99R/PF 0.820; Severe -61.96R/PF 0.775; Extreme -75.92R/PF 0.734
- C2: Ideal/current 5.92R/PF 1.022; Modest -20.11R/PF 0.928; Standard conservative -44.34R/PF 0.850; Severe -65.88R/PF 0.788; Extreme -87.42R/PF 0.730

## Monte Carlo sequence risk

Ten thousand bootstrap trade-order resamples were run per candidate using the observed return distribution.

- C1: median -15.45R; p05 -57.99R; p95 29.11R; P(terminal > 0) 27.9%; median Max DD 35.56R; p95 Max DD 68.35R
- C2: median 5.69R; p05 -38.33R; p95 51.94R; P(terminal > 0) 58.6%; median Max DD 27.81R; p95 Max DD 54.80R

Drawdown exceedance probabilities for 10R, 20R, 30R, 40R, and 50R thresholds and losing-streak percentiles are in `monte_carlo_summary.csv`.

## Outlier dependence

- C1: Observed -15.40R; Exclude largest winning trade -17.40R; Exclude top 5 winning trades -25.40R; Exclude top 1% winning trades -19.40R
- C2: Observed 5.92R; Exclude largest winning trade 3.92R; Exclude top 5 winning trades -4.08R; Exclude top 1% winning trades 1.92R

## Predeclared classifications

- C1: **D — OOS FAIL**. Primary pass: False; robust pass: False.
- C2: **D — OOS FAIL**. Primary pass: False; robust pass: False.

The numeric interpretation fixed before candidate metrics were evaluated defines “not catastrophically negative” as Monte Carlo terminal p05 >= −50% of observed positive Total R. Every individual criterion is recorded in `pass_fail.csv`.

## Required answers

1. **Did C1 replicate?** No; it failed at least one primary criterion.
2. **Did C2 replicate?** No; it failed at least one primary criterion.
3. **Did either outperform Control?** C1 did not on Avg R and PF; C2 did on Avg R and PF.
4. **Did either outperform BOS?** C1 did not on Avg R and PF; C2 did not on Avg R and PF.
5. **Did the Phase 17 edge survive unseen data?** Neither predeclared Phase 17 conditional edge met the primary unseen-OOS gate.
6. **Did it survive realistic costs?** No candidate remained positive under the standard conservative scenario.
7. **Ready for paper/live forward testing?** No. The predeclared candidates should not advance to paper/live validation as claimed edges.

## Overall conclusion

Neither predeclared Phase 17 conditional edge met the primary unseen-OOS gate. Phase 18 results must be accepted without tuning. Any strategy change informed by this report creates a new development strategy requiring a different untouched dataset.
