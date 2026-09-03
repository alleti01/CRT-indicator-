# Phase 26 — High-Expectancy Entry Trigger Discovery Report

## Final classification: **D — NO USABLE ENTRY EDGE**

---

## Data

- **Total bars:** 598,238 (2018-01-01 → 2026-06-26, NQ 5m)
- **Eligible labeled bars:** 598,214
- **Primary target:** +1.0 ATR before −0.5 ATR within 120 minutes
- **Walk-forward folds:** 6 chronological train→validate splits (2018–2020 train → 2021 val … → 2026 val)

---

## Unconditional baseline

| Direction | Target hit rate |
|---|---:|
| Long | 33.1% |
| Short | 32.2% |
| Chosen direction (WF stitched) | 33.3% |

At random, roughly one-third of bars reach +1 ATR before −0.5 ATR within 120m — paths are not rare, but that does **not** imply tradable edge after costs.

---

## Separability (first pass)

Univariate AUCs for predicting primary target peak near **0.511** (e.g. `ret_1_atr` short, `range_position` short). Cohen's d values are tiny (< 0.05). ExtraTrees walk-forward models produce modest hit-rate lift but **no net-positive economics**.

**Conclusion:** Weak statistical separability; insufficient economic separability.

---

## Stitched walk-forward (all scored bars)

| Metric | Gross | Net (1.0× costs) |
|---|---:|---:|
| N | 387,444 | 387,444 |
| Target hit rate | 33.3% | 33.3% |
| AvgR | +0.0039 | **−0.127** |
| TotalR | +1,491 | **−49,059** |
| PF | ~1.01 | **0.83** |

Every precision tier is **net-negative** after $14.50 round-turn costs (risk = 0.5× ATR at signal).

---

## Precision curve (net)

| Top fraction | N | Target hit rate | Net AvgR | Net PF | Signals/year |
|---:|---:|---:|---:|---:|---:|
| 100% | 387,444 | 33.3% | −0.127 | 0.83 | — |
| 50% | 193,722 | 34.0% | −0.141 | 0.82 | 35,396 |
| 30% | 116,233 | 34.4% | −0.148 | 0.81 | 21,238 |
| 10% | 38,744 | 35.4% | −0.146 | 0.81 | 7,079 |
| 5% | 19,372 | 36.1% | −0.141 | 0.82 | 3,540 |
| 1% | 3,874 | 36.0% | −0.168 | 0.79 | 708 |

**Precision improvement:** +1.4 to +2.7 percentage points hit rate (vs 33.3% baseline) — far too small to overcome costs.

**Score monotonicity (net AvgR vs decile):** **NO** (correlation ≈ −0.58). Higher deciles do **not** reliably improve net outcomes.

---

## Long / short (stitched WF)

| Direction | N | Hit rate | Net AvgR | Net PF |
|---|---:|---:|---:|---:|
| Long | 190,481 | 33.7% | −0.118 | 0.84 |
| Short | 196,963 | 33.0% | −0.135 | 0.82 |

Neither direction is net-viable.

---

## Top stable features (weak)

1. Short-term return (`ret_1_atr`, `ret_3_atr`)
2. Range position / close location
3. Distance from causal swing high/low
4. Wick ratios
5. Displacement-per-volume percentile

Importance is consistent in sign but **too weak** to convert into net edge.

---

## Simple rules

**Not extractable for deployment.** Candidate 3-condition rules on top-10% region remain net-negative (LONG ≈ −0.11R, SHORT ≈ −0.18R).

---

## False-signal diagnostics

High-score failures vs successes differ slightly on momentum and range-position features, but differences are small and insufficient for a robust filter without overfitting.

---

## Decision

**Entry edge large enough for strategy construction: NO**

Phase 27 should **not** build entry/stop/exit from this trigger.

NQ 5-minute OHLCV alone appears to contain **some** path predictability (hit-rate lifts of a few pp) but **insufficient asymmetric expectancy after realistic costs**. Richer information (order flow, cross-market lead/lag, deeper microstructure) may be warranted if research continues — but not another OHLCV feature sweep on the same bar stream.

---

## Next step

Stop bar-level OHLCV trigger mining on this dataset. If continuing research, explicitly evaluate **new information sources** (order flow, ES/NQ cross-market, L2) with the same frozen path targets — or accept that discretionary/systematic NQ 5m entries require a different paradigm than post-hoc bar scoring.
