# Phase 28 — Multi-Timeframe Strategy Comparison Report

**Classification: B — PROMISING HIGHER-TIMEFRAME CANDIDATE**

**Common range:** 2018-01-01 → 2026-06-26 (615,898 stitched 5m bars; higher TFs aggregated causally)

**5m parity:** RETEST_GATED N≈705, BOS N≈4150, CRT V2 N≈193 on reference windows — **verified**

---

## Strategies tested

| Included | Excluded |
|---|---|
| CONTROL | HIGH-EXPECTANCY (Phase 26 bar ML — not standalone architecture) |
| RETEST_GATED | ENTRY-PRECISION (Phase 24 ML ranker — not standalone architecture) |
| BOS_ONLY | |
| SEQUENTIAL_BOS (SWING_2_2, expiry=3) | |
| CRT_V2_B_LEGACY_EXP6 | |

---

## Headline finding

**Higher timeframes improve cost efficiency and modestly improve net economics for gated architectures (RETEST_GATED, CRT V2), but do NOT rescue CONTROL or BOS_ONLY.**

The only combination meeting most Phase 28 continuation gates on the full common range is:

**CRT_V2_B_LEGACY_EXP6 @ 15m** — N=210, net AvgR **+0.094R**, net PF **1.31**, positive all three eras, survives 1.5–2.0× costs and outlier removal.

**SEQUENTIAL_BOS @ 15m** shows the highest net AvgR (+0.261R) but **N=47** and **ISOLATED_TIMEFRAME_EFFECT** — not robust enough to continue.

---

## Best net AvgR by timeframe (full range)

| TF | Best strategy | N | Net AvgR | Net PF | Trades/mo |
|---|---|---:|---:|---:|---:|
| 5m | CRT_V2 | 614 | +0.029R | 1.06 | 6.0 |
| 15m | SEQUENTIAL_BOS* | 47 | +0.261R | 1.87 | 0.46 |
| 15m robust | **CRT_V2** | **210** | **+0.094R** | **1.31** | **2.1** |
| 30m | RETEST_GATED | 372 | +0.048R | 1.21 | 3.7 |
| 60m | RETEST_GATED | 176 | +0.045R | 1.28 | 1.7 |

\*Sequential BOS fails sample-size and stability gates.

---

## Timeframe patterns

| Strategy | Pattern |
|---|---|
| CONTROL | NO_TIMEFRAME_IMPROVEMENT |
| BOS_ONLY | NO_TIMEFRAME_IMPROVEMENT |
| RETEST_GATED | BROAD_HIGHER_TF_EDGE (5m −0.087R → 30m +0.048R → 60m +0.045R) |
| SEQUENTIAL_BOS | ISOLATED_TIMEFRAME_EFFECT (15m only) |
| CRT_V2 | ISOLATED_TIMEFRAME_EFFECT label, but **15m robust across eras** |

---

## Cost efficiency (representative)

| TF | Avg cost R/trade (approx) | Example |
|---|---:|---|
| 5m | ~0.054R | BOS gross +0.017R → net −0.037R |
| 15m | ~0.029R | CRT V2 gross +0.120R → net +0.094R |
| 30m | ~0.019R | RETEST_GATED gross +0.067R → net +0.048R |
| 60m | ~0.013R | RETEST_GATED gross +0.058R → net +0.045R |

---

## Recommendation

**Do higher timeframes improve signal quality?** **YES, partially** — primarily via cost efficiency and gated-entry architectures.

**Robust enough to continue?** **YES for CRT V2 @ 15m only** (promising, not strong).

**Next step:** Freeze **CRT V2-B-LEGACY-EXP6 @ 15m** and run one focused entry/stop/target optimization. Do **not** micro-optimize intermediate timeframes (20m, 25m, etc.).

Do **not** proceed with SEQUENTIAL_BOS @ 15m without a larger validation sample.

---

See `strategy_timeframe_summary.csv`, `era_stability.csv`, `cost_stress.csv`, `outlier_robustness.csv`.
