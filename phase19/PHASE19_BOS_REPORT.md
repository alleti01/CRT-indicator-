# Phase 19 — BOS robustness and edge isolation

## Executive summary

**Classification: D. No robust tradable edge: ideal gross profit is thin, realistic costs reverse it, and no subset survives the full screen.**

The original BOS produced 4,150 trades, 48.24R gross, Avg R 0.0116, PF 1.022, and max drawdown 57.87R across the two exact development periods. At the predeclared realistic $14.50 round-trip cost, it falls to -118.50R and PF 0.947. Its constant round-trip break-even cost is only $4.19 per trade.

No Phase 17 candidate was reused. Phase 19 registered 155 BOS hypotheses; 111 had N≥50, 5 had raw one-sided p<0.05, and 0 survived BH-FDR q≤0.10 with positive expectancy. Final Phase 19 candidates frozen: 0.

## Mandatory baseline reproduction

Both source periods passed byte-for-byte comparison for `model_comparison.csv`, `trades.csv`, and `event_debug.csv`. Exact entry and exit timestamps therefore match every original BOS record.

- 2021-2023: N 2,283; wins 950; losses 1,329; Total 41.95R; Avg 0.0184R; PF 1.036; max DD 55.72R.
- 2024-2026: N 1,867; wins 779; losses 1,087; Total 6.29R; Avg 0.0034R; PF 1.006; max DD 39.73R.
- 2021-2026 combined: N 4,150; wins 1,729; losses 2,416; Total 48.24R; Avg 0.0116R; PF 1.022; max DD 57.87R.

## Temporal robustness

Positive calendar years: 4/6. Positive months: 34/66. Six-month rolling windows positive: 31/61; their worst Total R was -37.42R and best was 54.62R. Performance is not uniform through time.

The HTF trend-state row is deliberately the same previous-closed 60-minute regime as HTF bias under more descriptive labels; it is reported, not treated as an independent signal.

## Cost stress

- Zero ($0.00/trade): Total 48.24R; Avg 0.0116R; PF 1.022; DD 57.87R.
- Optimistic ($9.50/trade): Total -61.01R; Avg -0.0147R; PF 0.972; DD 132.85R.
- Realistic ($14.50/trade): Total -118.50R; Avg -0.0286R; PF 0.947; DD 182.43R.
- Conservative ($28.00/trade): Total -273.75R; Avg -0.0660R; PF 0.883; DD 323.04R.
- Severe ($40.00/trade): Total -411.74R; Avg -0.0992R; PF 0.830; DD 450.30R.

Costs are applied trade by trade as `cost dollars / (stop points × $20)`; this preserves the frozen per-trade R denominator. The strategy is not economically viable if ordinary round-trip friction exceeds the reported break-even cost.

## Outlier and Monte Carlo stress

- Unmodified: N 4150; Total 48.24R; PF 1.022; DD 57.87R.
- Remove largest win: N 4149; Total 46.24R; PF 1.022; DD 57.87R.
- Remove top 5 wins: N 4145; Total 38.24R; PF 1.018; DD 57.87R.
- Remove top 10 wins: N 4140; Total 28.24R; PF 1.013; DD 57.87R.
- Remove top 1% outcomes: N 4108; Total -35.76R; PF 0.983; DD 66.94R.
- Remove top 5% outcomes: N 3942; Total -367.76R; PF 0.829; DD 398.94R.
- Winsorize positive tail at 99%: N 4150; Total 48.24R; PF 1.022; DD 57.87R.
- Winsorize positive tail at 95%: N 4150; Total 48.24R; PF 1.022; DD 57.87R.
- IID bootstrap, 10,000 paths: P(terminal R>0) 73.4%; terminal p5/p50/p95 -75.6/48.9/173.8R; max-DD p50/p95 69.5/135.2R; losing-streak p95 19.
- Moving-block bootstrap (20 trades), 10,000 paths: P(terminal R>0) 74.0%; terminal p5/p50/p95 -72.0/47.4/170.0R; max-DD p50/p95 68.4/130.5R; losing-streak p95 21.

The moving-block bootstrap uses contiguous 20-trade blocks to retain local outcome dependence; IID results are provided only as a less conservative comparison.

## Edge-isolation and multiplicity

All categorical hypotheses and six predeclared interaction families appear in `hypothesis_registry.csv`, including empty buckets. Raw p-values and BH-FDR q-values are both retained. FDR-surviving positive hypotheses: 0.

The expanding walk-forward used five chronological folds. A training-only condition was selected in 3/5 folds; its subsequent evaluation result is marked by `selected_by_train` in `walk_forward_results.csv`. No held-forward fold influenced its own selection.

## Final answers

1. **Does original BOS demonstrate evidence of a persistent edge?** It has a positive gross historical mean, but not a defensible persistent edge. Classification **D — NO ROBUST EDGE**: ideal gross profit is thin, realistic costs reverse it, and no subset survives the full screen.
2. **Does BOS survive realistic NQ execution costs?** No; realistic Total R is -118.50 and PF is 0.947.
3. **What is BOS's break-even execution cost per trade?** $4.19 per round trip under the frozen trade-specific risk conversion.
4. **Is profitability broadly distributed or concentrated?** Concentrated. Two of six year buckets and 32 of 66 months were negative; 2021 supplied about 66% of all positive-year Total R, and deleting the top 1% of outcomes changes +48.24R to -35.76R.
5. **Which market conditions explain performance?** The strongest raw associations were 02:00-03:59 CT, Long × low volatility, small stops/targets, and Overnight × medium volatility. They are descriptive only: none survived the common multiplicity correction, so no condition is established as an explanation.
6. **Did any conditions survive multiple-hypothesis correction?** No. FDR-surviving positive hypotheses: 0.
7. **Did any candidate remain robust across walk-forward folds?** No. Training selected a rule in three folds; the first two lost in the next period and the third positive evaluation had only 22 trades. No rule met the final fold requirements.
8. **How sensitive are candidate parameters?** Not applicable: no hypothesis reached the preliminary candidate gate, so parameter-neighborhood testing was correctly not initiated. `parameter_sensitivity.csv` records this explicitly.
9. **Did P19-C1, C2, or C3 materially improve BOS robustness?** No P19 candidate qualified, so none was created or credited with an improvement.
10. **Are any candidates strong enough to justify another genuine OOS test?** No.
11. **Which candidates should be frozen for Phase 20?** None; `FROZEN_PHASE19_CANDIDATES.md` freezes a zero-candidate result.
12. **Final finding:** No robust BOS edge was found.

All 2021–2026 observations are now development/research. No Phase 19 result is described as out-of-sample, and no paid data was downloaded.
