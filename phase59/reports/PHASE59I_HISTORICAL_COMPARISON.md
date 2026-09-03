# PHASE59I — FULL HISTORICAL COMPARISON

Diagnostic only. Frozen parameters. No optimization.  
Runtime: ~13 min pipeline + cached analysis (`phase59/tools/phase59i_historical.py`).

---

## Executive verdict

| Question | Answer |
|----------|--------|
| Does **ORIGINAL** (leaked HTF) show positive expectancy? | **YES** — strong and stable (AvgR 0.53, PF 1.95, 10/10 years, 66/66 rolling windows) |
| Does **CAUSAL A** (live-safe, last completed HTF) survive? | **Marginally YES statistically, effectively NO economically** — AvgR 0.022, PF 1.03, MaxDD 419R; train period +21R total; 43/66 rolling windows only |
| Does **CAUSAL B** (developing HTF) survive? | **YES with degraded edge** — AvgR 0.18, PF 1.28, stable across years/windows but ~64% TotalR vs ORIGINAL |
| Is ORIGINAL performance an artifact of HTF leakage? | **Largely YES** — removing leakage collapses edge (A) or cuts it ~3× (B) |
| Is performance stable under CAUSAL A? | **NO** — 3 negative years (2020–2022), 23/66 losing rolling windows, concentrated in recent years |

**Live architecture implication:** Frozen canonical results are **not** representative of live-safe HTF. **CAUSAL A** (`lookahead_off`) is the correct live model; current frozen parameters do **not** show a robust live edge without further research (not optimization in this audit).

---

## Overall M1 canonical (H1 KEEP)

| Mode | N | LONG | SHORT | AvgR | PF | TotalR | WinRate | MaxDD |
|------|---|------|-------|------|-----|--------|---------|-------|
| ORIGINAL | 61,335 | 31,434 | 29,901 | 0.530 | 1.95 | 32,534 | 43.9% | 22.0 |
| CAUSAL A | 34,691 | 18,400 | 16,291 | 0.022 | 1.03 | 747 | 29.3% | 419.1 |
| CAUSAL B | 64,502 | 33,141 | 31,361 | 0.182 | 1.28 | 11,727 | 33.9% | 56.5 |

Trade count drops ~43% under CAUSAL A (fewer signals pass with stale HTF context).

---

## Walk-forward (60% train / 20% val / 20% holdout)

| Split | ORIGINAL AvgR / TotalR | CAUSAL A | CAUSAL B |
|-------|------------------------|----------|----------|
| **Train** | 0.523 / +19,234 | **0.001 / +21** | 0.175 / +6,772 |
| **Validation** | 0.545 / +6,685 | 0.055 / +382 | 0.182 / +2,354 |
| **Holdout** | 0.539 / +6,615 | 0.050 / +344 | 0.202 / +2,600 |

ORIGINAL is stable across all splits. CAUSAL A **fails in-sample** (train ≈ breakeven). CAUSAL B holds positive expectancy in all splits but at ~⅓ the ORIGINAL rate.

---

## By year (every available year)

| Year | ORIGINAL AvgR | CAUSAL A AvgR | CAUSAL B AvgR |
|------|---------------|---------------|---------------|
| 2017 | 0.570 | 0.065 | 0.193 |
| 2018 | 0.559 | 0.020 | 0.193 |
| 2019 | 0.499 | 0.035 | 0.159 |
| 2020 | 0.495 | **−0.017** | 0.167 |
| 2021 | 0.534 | **−0.010** | 0.185 |
| 2022 | 0.514 | **−0.041** | 0.167 |
| 2023 | 0.551 | 0.044 | 0.175 |
| 2024 | 0.539 | 0.048 | 0.181 |
| 2025 | 0.519 | 0.041 | 0.222 |
| 2026 | 0.565 | 0.083 | 0.185 |

- ORIGINAL: **10/10** years AvgR > 0  
- CAUSAL A: **7/10** (2020–2022 negative)  
- CAUSAL B: **10/10** positive, min year AvgR 0.159  

---

## Long / Short

| Mode | LONG AvgR | SHORT AvgR |
|------|-----------|------------|
| ORIGINAL | 0.520 | 0.542 |
| CAUSAL A | 0.020 | 0.023 |
| CAUSAL B | 0.185 | 0.178 |

Direction balance survives causally; edge degradation is symmetric.

---

## Setup categories (top slices by TotalR)

Dominant positive ORIGINAL categories (`market_state`, `direction_confidence_band`, `15m_state`) shrink dramatically under CAUSAL A. Under CAUSAL B, `UNCERTAIN` / `HIGH` band setups retain modest positive TotalR but at lower AvgR than ORIGINAL.

Full breakdown: `phase59i_by_setup.csv` (all `market_state`, `high_subtype`, `direction_confidence_band`, `15m_state`, `5m_state` slices).

---

## Rolling periods (12-month windows, 3-month step)

| Metric | ORIGINAL | CAUSAL A | CAUSAL B |
|--------|----------|----------|----------|
| Windows | 66 | 66 | 66 |
| AvgR > 0 | **66/66** | **43/66** | **66/66** |
| TotalR > 0 | 66/66 | 43/66 | 66/66 |
| Min window AvgR | 0.477 | **−0.055** | 0.125 |
| Median window AvgR | 0.530 | 0.023 | 0.178 |
| Top-year share of TotalR | 11.7% | **28.3%** | 13.6% |

ORIGINAL: not concentrated (top year ≈12% of TotalR).  
CAUSAL A: **unstable** — 35% of rolling windows negative; edge concentrated in recent subset.  
CAUSAL B: stable rolling profile, but weaker magnitude.

Also exported: 6-month rolling windows in `phase59i_rolling.csv`.

---

## Artifacts

| File | Content |
|------|---------|
| `phase59i_overall.csv` | Full-sample metrics |
| `phase59i_walkforward.csv` | Train / val / holdout |
| `phase59i_by_year.csv` | Annual |
| `phase59i_by_direction.csv` | LONG / SHORT |
| `phase59i_by_setup.csv` | Setup category slices |
| `phase59i_rolling.csv` | 6m and 12m rolling |
| `phase59i_historical_audit.json` | Complete JSON |
| `phase59/diagnostics/cache/canon_full_*.parquet` | Cached canon trades per mode |

---

## Conclusions

1. **HTF future leakage materially inflates frozen canonical performance.** ORIGINAL TotalR 32,534 vs CAUSAL A 747 (~**97.7% reduction**).

2. **Positive expectancy does NOT robustly survive under live-safe CAUSAL A.** Technical PF>1 masks economically negligible edge and catastrophic drawdown profile.

3. **CAUSAL B retains a real but reduced edge** with good stability — possible research path, but still far below ORIGINAL and uses developing HTF semantics not matching TV `lookahead_off`.

4. **Do not use Phase59H (`lookahead_on`) for live trading** — it reproduces leaked semantics, not causal ones.

5. **Next step is architectural (not parameter tuning):** rebuild signal generation under CAUSAL A HTF and reassess whether any frozen logic remains valid — outside scope of this diagnostic audit.
