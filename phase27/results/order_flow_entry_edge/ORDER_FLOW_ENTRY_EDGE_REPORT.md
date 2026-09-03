# Phase 27 — Order Flow / Microstructure Entry Edge Report

**Classification: D — NO USABLE ORDER-FLOW ENTRY EDGE (pilot)**

**Early stop triggered.** Do not purchase expanded microstructure history.

---

## Executive summary

A **1-month NQ trades pilot** (Jan 2024, $10.43, 7.54M events) was aggregated to causal 5-minute aggressor-flow features and compared against a compact OHLCV control using identical walk-forward folds (train Jan 1–15 → validate Jan 16–31).

**Order flow does not materially outperform exhausted 5m OHLCV** on the frozen primary target (+1.0 ATR before −0.5 ATR, 120m). High-confidence regions remain **net-negative at 1.0× costs** except tiny top-1% slices (N=16–32) that fail minimum sample and stability standards.

---

## Data

| Item | Value |
|---|---|
| Schema | Databento `trades` (GLBX.MDP3) |
| Symbol | NQ.v.0 continuous |
| Range | 2024-01-01 → 2024-02-01 |
| Cost | **$10.43** |
| Microstructure events | **7,537,890** |
| 5m eligible decision points (pilot month) | **6,084** |
| Walk-forward validation stitched N | **3,288** |

Aggressor side: B=3,780,880 buy-initiated; A=3,756,987 sell-initiated; N=23 unknown.

---

## Primary target (frozen)

+1.0 ATR before −0.5 ATR within 120 minutes.

| Metric | Rate |
|---|---:|
| Unconditional long | **33.05%** |
| Unconditional short | **32.84%** |
| Direction-conditioned (max side) baseline | **~34.6%** |

Phase 26 full-sample baseline for reference: ~33.3% unconditional; top-10% OHLCV model ~35.4% (+2.1 pp).

---

## Model comparison (walk-forward stitched validation)

| Model | AUC | Top 10% hit | Top 5% hit | Top 1% hit | Top 10% net AvgR |
|---|---:|---:|---:|---:|---:|
| **A — OHLCV only** | 0.512 | 36.0% | 39.0% | 40.6% | **−0.095R** |
| **B — Order flow only** | 0.491 | 36.6% | 35.4% | 43.8% | **−0.077R** |
| **C — Combined** | 0.516 | 36.3% | 40.2% | 62.5% | **−0.087R** |

### Incremental value of order flow (C − A)

| Metric | Value |
|---|---:|
| AUC improvement | +0.004 |
| Top-10% precision lift | **+0.3 pp** |
| Top-10% net AvgR improvement | +0.009R (both negative) |

**ORDER FLOW MATERIALLY OUTPERFORMS OHLCV: NO**

---

## Precision curve (Model C)

| Tier | N | Hit rate | Lift vs baseline | Net AvgR |
|---|---:|---:|---:|---:|
| All | 3,288 | 34.6% | 0.0 pp | −0.110R |
| Top 10% | 328 | 36.3% | +1.7 pp | −0.086R |
| Top 5% | 164 | 40.2% | +5.6 pp | +0.035R |
| Top 1% | 32 | 62.5% | +27.9 pp | +0.720R |

Top 5%/1% economics look positive but **N too small**, single validation month, and not robust to costs/monotonicity — does **not** meet Phase 28 continuation gate (N≥200, net AvgR≥+0.10R at top tier with stability).

---

## Score monotonicity

Decile rank correlation (net AvgR vs decile): **PARTIAL** — isolated top buckets, negative middle tiers.

**Classification: PARTIAL** (insufficient for strategy construction)

---

## Economics & cost stress (Model C top 10%)

| Cost multiplier | Net AvgR (top 10%) |
|---:|---:|
| 0.5× | ~−0.04R |
| 1.0× | **−0.086R** |
| 1.5× | ~−0.13R |
| 2.0× | ~−0.17R |

All primary high-volume tiers remain net-negative at realistic costs.

---

## Early-stop checklist

| Criterion | Result |
|---|---|
| AUC ≤ ~0.53 | ✅ (~0.516 combined) |
| Top-10% lift ≤ ~3 pp | ✅ (+0.3 pp vs OHLCV; +1.7 pp vs baseline) |
| Top-10% net expectancy negative | ✅ |
| Meaningful improvement over OHLCV | ❌ not met |
| Score monotonicity | ❌ not convincing |

**→ STOP. Do not expand to 2–6 month datasets ($21–$61+).**

---

## Order-flow state diagnostics (top 5% success vs failure)

No systematic, stable flow-state separation emerged at pilot scale (see `false_signal_analysis.csv`). Failures did not show a consistent “absorption” or divergence signature strong enough to filter.

---

## Final classification

**D — NO USABLE ORDER-FLOW ENTRY EDGE**

Aggressor-side trade flow on 5m bar closes does not provide sufficient incremental directional asymmetry to survive realistic NQ costs at actionable signal volumes.

---

## Next step

**Stop bar-based order-flow entry feature mining on this architecture.** If research continues, pivot to a **fundamentally different information source** (cross-market ES/NQ lead-lag, scheduled-event response, or L2 book states via `mbp-1` only after a new hypothesis — not a V2 resweep of the same bar-close scoring framework).
