# Phase 24 — Entry Signal Precision Report

## Architecture audited

**Baseline:** Phase 14 Frozen CRT (`FrozenConfig` in `phase16/config.py`), reproduced via `phase16/run_backtest.py`.

| Stage | Definition |
|---|---|
| Setup | BOS or SSL/BSL sweep, score ≥ 70, Variant-C (HTF ≠ neutral, not after-hours), cooldown |
| BOS | Close-confirmed break of prior active swing (5/5 pivots) |
| Retest | Later-bar touch of `bos_level ± 0.10×ATR` without invalidation |
| Confirm | Later-bar close beyond BOS level after retest |
| Entry | Control=setup close; BOS=BOS close; Retest=retest close; Confirm=confirm close |
| Stop | `entry ± 1.5×ATR(14)` |
| Target | `2R` |
| Max hold | 60 minutes (12 bars) |
| Costs | Frozen Phase 16 execution costs embedded in `result_R` |

**Population:** Combined frozen exports — `phase18/results/base_run/trades.csv` (2021–2023, 7,716) + `phase17/results/baseline_run/trades.csv` (2024–2026, 6,363) = **14,079 trades** across all four entry models. Not CRT_SETUP_V2 or SEQUENTIAL_BOS.

## 1. Can we predict higher-quality entries?

**Weakly, not reliably.** Walk-forward classifiers (logistic, tree, ExtraTrees, GBM) on entry-time features produce stitched forward-validation AUC ≈ **0.50–0.53** for `GOOD_ENTRY` (+0.5R before −0.5R). Univariate feature AUCs peak near **0.524** (`minutes_from_rth_open`). Effect sizes are tiny (|d| < 0.09).

## 2. Quality decile monotonicity?

**NO.** Forward-validation decile AvgR correlation with decile rank ≈ **0.00**. Decile 5 is the worst bucket (−0.093 AvgR); deciles 2, 4, 8 show modest positive AvgR, but the relationship is not monotonic.

## 3. Bad-signal rejection?

**Marginally.** Rejecting the top 30–50% `BAD_SCORE` signals on forward validation improves PF from **0.996 → 1.02–1.04** and reduces MaxDD, but improvement is far below deploy thresholds.

## 4. Approximate rejection rate?

**30–50%** rejection gives the most stable modest uplift on forward validation; **70–90%** rejection is unstable (non-monotonic retention curve).

## 5–8. Performance changes (forward validation, top 30% quality retention)

| Metric | Baseline FV | Top 30% quality | Change |
|---|---:|---:|---:|
| N | 8,969 | 2,690 | −70% |
| Win rate | 41.4% | 42.9% | +1.5 pp |
| AvgR | −0.0019 | +0.0165 | +0.018 |
| PF | 0.996 | 1.033 | +0.037 |
| MaxDD | 143.1R | 95.4R | −33% |

Full development baseline (14,079 trades): AvgR **−0.006**, PF **0.989**, MaxDD **269.7R**.

## 9. Top entry-time features (stable-ish across folds)

1. Upper wick ratio  
2. Day of week  
3. Trend aligned with HTF  
4. Body / range ratio  
5. Session bucket  
6. Direction (long vs short)  
7. Close location in bar  
8. HTF regime  
9. Setup score  
10. Body size percentile vs ATR  

## 10. Feature stability across time?

**Partial.** Session/time and candle-quality features recur in importance, but year splits of the top-half filtered set are mixed: 2023 positive, 2024 flat, 2025 modest positive, **2026 negative**.

## 11. Pine simplification?

**Possible but not worthwhile.** A small rule set using session + trend alignment + wick quality could approximate the weak ML ranking, but captured edge is too small to justify indicator work.

## 12. Strong enough for indicator?

**NO.** Forward validation fails success criteria (PF ≥ 1.20, AvgR ≥ +0.10R with N ≥ 150 in a stable region).

## Long / short

| Direction | Baseline AvgR | Top-half quality AvgR |
|---|---:|---:|
| Long | +0.003 | −0.008 |
| Short | −0.016 | −0.005 |

Shorts are weaker at baseline; quality ranking does not fix either side materially.

## Cost robustness (top 50% quality, forward validation)

| Cost mult | AvgR | PF |
|---:|---:|---:|
| 1.0× | +0.004 | 1.008 |
| 1.5× | −0.021 | 0.960 |
| 2.0× | −0.046 | 0.915 |

Filter edge disappears under stress costs.

## Outlier robustness

Top-half improvement survives excluding best trade / top 3 winners; not driven by a single outlier.

## Final classification

**C — WEAK / UNSTABLE IMPROVEMENT**

Entry-time information contains **small, noisy** separation. Quality ranking and bad-signal rejection produce minor PF/MaxDD changes that do **not** replicate cleanly across deciles, years, or cost stress.

## Next step

Do **not** proceed to Phase 25 indicator build on this filter. Document that the frozen CRT entry population is largely **not separable at entry** with available causal features; any Phase 25 work should revisit **signal generation** (setup/BOS gating) or **exit/trade management**, not entry-quality ML on the current population.
