# Phase 25 — BOS Trade Architecture Optimization Report

## Frozen BOS signal (reproduced)

**Architecture:** Phase 14 Frozen CRT — BOS entry model only (`model == "BOS"`).

| Component | Definition |
|---|---|
| Setup | Score ≥ 70, Variant-C HTF/session filter, cooldown |
| BOS | Close-confirmed structure break after setup |
| Entry | BOS bar **close** (same bar as signal) |
| Stop | `entry ± 1.5 × ATR(14)` |
| Target | `2R` |
| Max hold | 60 minutes (12 × 5m bars) |
| Costs | `$14.50` round-turn / (`risk_points × $20`) applied as `net_R = gross_R − cost_R` |

**Population:** 4,150 BOS trades (2021–2023: 2,283 + 2024–2026: 1,867).

**Reproduction:** Gross `TotalR = +48.24R` (matches expected ~+47.2R). Discrepancy vs Phase 24 combined figure is rounding/window labeling only.

---

## Baseline performance

### Gross (frozen `result_R` in trades.csv)

| Metric | All | Long | Short |
|---|---:|---:|---:|
| N | 4,150 | 2,150 | 2,000 |
| Win rate | 41.7% | 43.8% | 39.4% |
| AvgR | +0.0116 | +0.0275 | −0.0054 |
| TotalR | **+48.2** | +59.1 | −10.9 |
| PF | 1.022 | 1.056 | 0.990 |
| MaxDD | 57.9R | 45.8R | 54.1R |

### Net (realistic 1.0× costs)

| Metric | Value |
|---|---:|
| AvgR | **−0.029** |
| TotalR | **−118.5** |
| PF | 0.947 |

**The historical +47R BOS edge is gross-only and does not survive realistic execution costs.**

### Yearly gross TotalR

| Year | N | TotalR | AvgR |
|---|---:|---:|---:|
| 2021 | 764 | +34.8 | +0.046 |
| 2022 | 754 | −2.4 | −0.003 |
| 2023 | 765 | +9.5 | +0.012 |
| 2024 | 782 | +4.3 | +0.006 |
| 2025 | 719 | −2.0 | −0.003 |
| 2026 | 366 | +3.9 | +0.011 |

4/6 years positive gross — not broadly distributed; 2022/2025 flat/negative.

### Baseline robustness (gross)

| Scenario | TotalR | AvgR |
|---|---:|---:|
| Full | +48.2 | +0.0116 |
| Ex best trade | +46.2 | +0.0111 |
| Ex top 3 | +42.2 | +0.0102 |
| Ex top 1% winners | **−35.8** | **−0.0087** |

Bootstrap AvgR 95% CI: **[−0.026, +0.048]** — spans zero.

---

## MFE / MAE geometry

| | All | Long | Short |
|---|---:|---:|---:|
| Median MFE | 1.69R | 1.64R | 1.80R |
| Median MAE | 1.65R | 1.53R | 1.76R |
| P(+0.5R before −0.5R) | 47.6% | 48.7% | 46.5% |
| P(+1R before −0.5R) | 32.9% | 34.2% | 31.6% |
| P(+1R before −1R) | 48.6% | 48.7% | 48.4% |
| P(+2R before −1R) | 28.9% | 28.7% | 29.1% |

Trades often reach +1R but fail to reach +2R — consistent with giveback under fixed 2R target / time exit.

---

## Entry execution study

| Model | Fill rate | Gross AvgR | Matched Δ AvgR vs CURRENT |
|---|---:|---:|---:|
| CURRENT | 100% | +0.0125 | — |
| NEXT_OPEN | 100% | +0.0110 | −0.0015 |
| NEXT_CLOSE | 100% | +0.0158 | **+0.0033** |
| RETRACE_25 | 82.7% | +0.0123 | +0.260* |
| RETRACE_50 | 66.2% | +0.0205 | +0.476* |
| BOS_RETEST | 69.8% | +0.0128 | +0.385* |

\*Limit models show large matched improvement because **unfilled signals had much higher CURRENT AvgR (+0.93 to +1.25R)** — strong selection effect. Unfilled CURRENT performance >> filled CURRENT on limit subsets.

---

## Stop / target / hold / management (gross, full sample)

**Best stop region:** 1.25–2.0 ATR (plateau AvgR +0.013 to +0.026). Current 1.5 ATR is mid-pack.

**Best target region:** 1.5–3.0R (plateau). Current 2R is not optimal in-sample but nearby.

**Hold:** 30–60m best; 90–120m degrades.

**Management:** FIXED and PARTIAL_1R modest; BE_AFTER_1R and TRAIL_AFTER_1R destroy expectancy.

---

## Walk-forward (stitched TEST periods)

| Metric | Gross | Net 1.0× costs |
|---|---:|---:|
| N | 1,987 | 1,987 |
| AvgR | +0.033 | **−0.019** |
| TotalR | +65.3 | **−37.3** |
| PF | 1.058 | 0.969 |
| MaxDD | 52.1R | 86.8R |

**Fold breakdown (gross):**

| Test period | Selected config | TotalR |
|---|---|---:|
| 2023 | NEXT_CLOSE / 1.25 ATR / 3R | +33.6 |
| 2024 | RETRACE_50 / 1.0 ATR / 3R | +60.0 |
| 2025 | RETRACE_50 / 1.0 ATR / 3R | **−16.2** |
| 2026 | RETRACE_50 / 1.0 ATR / 3R | **−12.1** |

Recent folds fail — architecture unstable out-of-sample.

**Parameter stability:** RETRACE_50 (3/4 folds), target 3R (4/4), stop 1.0 ATR (3/4).

---

## In-sample best (NOT deployable)

`RETRACE_50 / 1.0 ATR / 3R / 45m / FIXED` — gross AvgR +0.059, PF 1.10, N=2,749 (66% fill). In-sample excellence does not survive walk-forward + costs.

---

## Monte Carlo (walk-forward gross trade sequence)

| Metric | Value |
|---|---:|
| P(terminal R > 0) | 85.3% |
| Median terminal R | +65.2R |
| 5th percentile | −36.2R |
| 95th percentile | +168.2R |

---

## Success criteria: **3 / 10 passed** (walk-forward, gross-only)

Fails: AvgR > +0.05 (gross WF), PF ≥ 1.15, net cost robustness, stable recent years, baseline ex-top-1% gross positive.

---

## Final classification: **D — BOS EDGE DOES NOT SURVIVE VALIDATION**

The positive historical BOS TotalR is **gross pre-cost**. After realistic costs the baseline is **negative**. Optimized walk-forward architecture remains **net-negative at 1.0× costs** and **recent test folds (2025–2026) are losing**. Do not proceed to Pine indicator construction on this architecture.

**Next step:** Replace or fundamentally rebuild the signal architecture — not further BOS entry/exit tuning on this dataset.
