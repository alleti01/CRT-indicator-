# Phase53 Opportunity Discovery Report

## Executive Summary

Phase53 built a causal event-level dataset of **925,486** structural events (E1–E16) on canonical NQ 1M data (2017-10-01 → 2026-06-26 CT). Each event carries causal 1M/5M/15M features; outcomes use frozen Phase52 research exits (0.75 ATR stop, 2.5R target, 60min hold).

**Bottom line:** Raw 1M structure events are overwhelmingly negative (~**-0.35R**). A walk-forward logistic **quality score** produces **monotonic OOS deciles** (D1 −0.96 → D10 +0.81). Top-scored **CORE-unauthorized** events are positive OOS. However, the **unfiltered scored pool remains negative**, G3/C4 range-location is a **U-shaped extreme artifact** (not a smooth C4 mechanism), and implementation gates are **not met**.

---

## Event Base Rates (selected)

| EVENT | N | EVENTS/DAY | AVGR | CORE-UNAUTH AVGR |
|-------|---|------------|------|------------------|
| E1 bullish BOS | 104,030 | 32.6 | **-0.406** | -0.410 |
| E2 bearish BOS | 98,388 | 30.9 | **-0.438** | -0.441 |
| E13 failed range bull | 114,315 | 35.8 | -0.275 | -0.277 |
| E14 failed range bear | 104,095 | 32.6 | -0.291 | -0.294 |
| **All events** | 925,484 | 290.2 | **-0.351** | ~-0.35 |

Confirms Phase52: continuous micro-BOS without Phase44 is strongly negative.

---

## Score Deciles (Walk-Forward OOS, N=542,462)

| DECILE | N | AVGR | PF | CORE-UNAUTH AVGR |
|--------|---|------|-----|------------------|
| D1 | 54,248 | -0.957 | 0.16 | -0.959 |
| D5 | 54,245 | -0.472 | 0.52 | -0.471 |
| D8 | 54,246 | +0.092 | 1.12 | +0.089 |
| D9 | 54,246 | +0.413 | 1.64 | +0.413 |
| **D10** | 54,247 | **+0.814** | **2.62** | **+0.808** |

**Score monotonicity: PASS** — clear separation; top decile strongly positive including CORE-unauthorized.

Top 20% (score ≥ P80): N=108,493, **AvgR +0.61**, PF 2.07, ~59 trades/day.

---

## G3/C4 Mechanism Test (E13/E14 vs continuous 15M range position)

| Range Position Decile | AvgR |
|----------------------|------|
| Lowest (0–8%) | **+0.30** |
| Middle (38–56%) | **-0.89** |
| Highest (94–100%) | **+0.38** |

**Not a smooth monotonic C4 effect.** Expectancy is positive at **both extremes** and deeply negative in the middle — a **U-shape**, not Phase52's upper/lower-third bucket. 

**G3/C4 EXPLANATION: C** — isolated threshold / selection artifact; Phase52 C4 captured extremes but neighboring specs collapsed.

---

## Top Predictive Features (good vs bad events)

| Feature | Effect | Interpretation |
|---------|--------|----------------|
| `m15_body_atr` | Higher favorable | Stronger 15M displacement at event |
| `mtf_1m_5m_align` | Alignment favorable | 1M direction matches 5M momentum |
| `countertrend_15m` | Lower favorable | Continuation with 15M, not counter-trend |
| `m15_range_pos_*` | Minimal effect | Range location weak globally; extremes matter only for G3 family |

---

## Final Model (Top 20% score, OOS)

| MODEL | N | TRADES/DAY | AVGR | PF | CORE-UNAUTH AVGR |
|-------|---|------------|------|-----|------------------|
| P53-WF all scored | 542,462 | 297 | -0.268 | 0.70 | -0.270 |
| **P53 top 20%** | 108,493 | 59 | **+0.613** | **2.07** | **+0.610** |
| **P53 top 10%** | 54,247 | 30 | **+0.814** | **2.62** | **+0.808** |
| CORE reference | 1,135 | 0.48 | 1.648 | 17.78 | — |

Holdout (2025–2026, top 30% proxy): AvgR **+0.15**, PF 1.22.

---

## Verdict Checklist

| Item | Result |
|------|--------|
| PHASE53 CAUSALITY | **PASS** |
| TOTAL STRUCTURAL EVENTS | **925,486** |
| CAN GOOD EVENTS BE DISTINGUISHED OOS | **YES** (monotonic deciles) |
| BEST MODEL | Logistic regression, 8 features |
| BEST FEATURE SET | m15_body_atr, countertrend_15m, mtf_1m_5m_align, mtf_1m_15m_align, atr, atr_ratio, m5_range_pos_8, m5_range_pos_4 |
| OOS AVGR (all scored) | **-0.268** |
| OOS AVGR (top decile) | **+0.814** |
| CORE-UNAUTHORIZED AVGR (top decile) | **+0.808** |
| SCORE MONOTONICITY | **PASS** |
| PARAMETER STABILITY (thresholds) | **PASS** (P50–P90 all positive AvgR) |
| YEAR STABILITY (all scored) | **FAIL** (all years negative) |
| 2X COST (sample) | Degrades severely |
| EX-TOP-1% | **PASS** (-0.38 vs -0.35 base) |
| FINAL HOLDOUT | **PASS** (+0.15 top-filter proxy) |
| G3/C4 EXPLANATION | **C** — threshold artifact |
| REVERSAL EDGE (unfiltered) | **NO** |
| CONTINUATION EDGE (unfiltered) | **NO** |
| DOES PHASE53 IDENTIFY MOVES CORE MISSES | **YES** (top-score CORE-unauth positive) |
| DOES PHASE53 ADD PORTFOLIO VALUE | **Unclear** — high-score alone has large TotalR but very high frequency & MaxDD |
| SHOULD CORE CHANGE | **NO** |
| SHOULD PHASE51 CHANGE | **NO** |
| **SHOULD PHASE53 ADVANCE** | **NO** |
| READY FOR PINE | **NO** |

---

## Most Important Finding

**Yes — but only at the extreme tail of a quality score.** Information available before a 1M structural event *does* distinguish winners from losers OOS (monotonic deciles, top 10% ~+0.81R). However, **~90% of structural events remain untradeable**, the aggregate scored pool is still negative, Phase52 G3+C4 was an **extreme-range artifact** not a robust filter, and no implementation-ready threshold survives all stability gates. **Do not deploy a secondary layer from this research without a new frozen-spec phase.**

CORE / Phase51 unchanged. Continue Phase51 forward validation.
