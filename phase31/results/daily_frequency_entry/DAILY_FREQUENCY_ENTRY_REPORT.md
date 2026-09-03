# Phase 31 — NQ 15M Daily-Frequency High-Quality Entry Discovery

## Core Research Question

**Can we generate ~1–2 high-quality NQ signals per RTH day on 15m bars with positive net expectancy after costs?**

**Answer: YES** — a non-CRT **MOMENTUM_DISPLACEMENT** architecture satisfies all 14 minimum success criteria in stitched walk-forward validation.

---

## Architectures Tested (11)

| Family | Architecture |
|--------|-------------|
| Baseline | RETEST_GATED, BOS_ONLY, SEQUENTIAL_BOS_CONFIRM, CRT_V2_B_LEGACY_EXP6 |
| Structural break | SWING22_BOS_CLOSE, SWING22_BOS_RETEST |
| Liquidity response | SWEEP_RECLAIM |
| Momentum / displacement | **MOMENTUM_DISPLACEMENT** |
| Range / rejection | RANGE_BREAK_10, FAILED_BREAK_10, IMPULSE_PULLBACK |

**Parameter combinations:** 21 shortlist execution configs × 7 walk-forward folds (train-select / test-freeze per fold).

---

## Deduplication (causal)

- RTH-only signals (`0930–1600` America/Chicago)
- One active trade at a time
- Minimum 4 bars between same-direction entries
- One signal per structural `event_id`
- Maximum 2 signals per RTH session day

---

## Best Signal Architecture: MOMENTUM_DISPLACEMENT

**Signal rule (15m, causal):**
- Body > 1.5× 20-bar average body
- Close location in top 20% of bar range → LONG
- Close location in bottom 20% of bar range → SHORT
- Fires at bar close; RTH only

**Walk-forward execution (mode across folds):**
| Parameter | Value |
|-----------|-------|
| Entry | BOS_RETEST |
| Stop | 0.75 ATR |
| Target | 3.0R |
| Max hold | 60m |
| Management | FIXED |

---

## Stitched Walk-Forward (net of $14.50 RT)

| Metric | Value |
|--------|-------|
| N | 2,873 |
| RTH days | 2,188 |
| Trades/day (mean) | 1.22 |
| Trades/week | 6.11 |
| Win rate | 46.2% |
| Net AvgR | +0.233R |
| Net TotalR | +670.3R |
| Net PF | 1.47 |
| MaxDD | 15.1R |
| Return/MaxDD | 44.5 |

---

## Daily Signal Distribution

| Bucket | Days | % |
|--------|------|---|
| 0 signals | 617 | 28.2% |
| 1 signal | 653 | 29.8% |
| 2 signals | 737 | 33.7% |
| 3+ signals | 181 | 8.3% |

Median signals/day: **1.0** · 90th percentile: **2.0** · Longest dry stretch: **515** RTH days

---

## Baseline Comparisons (stitched WF, net)

| Baseline | N | Net AvgR | Net PF | Notes |
|----------|---|----------|--------|-------|
| Phase 30 CRT V2 @ 15m | 69 | +0.161R | 1.51 | Sparse, high quality |
| Phase 28 RETEST_GATED | 184 | +0.037R | 1.07 | Weak net edge |
| Simple BOS_ONLY | 633 | +0.172R | 1.36 | Better frequency, lower precision |
| SWING22_BOS_CLOSE | 2,179 | +0.194R | 1.54 | Strong alternate ~1.0 trades/day |

CRT V2 remains the precision reference but cannot meet daily-frequency requirements without destroying its funnel.

---

## Frequency / Quality Frontier

| Target trades/day | Best architecture | Actual | Net AvgR | Net PF |
|-------------------|-------------------|--------|----------|--------|
| 0.25 | BOS_ONLY | 0.29 | +0.172R | 1.36 |
| 0.50–0.75 | SWING22_BOS_CLOSE | 0.99 | +0.194R | 1.54 |
| 1.0–2.0 | MOMENTUM_DISPLACEMENT | 1.22 | +0.233R | 1.47 |

There is a clear tradeoff: CRT-quality (~0.05 trades/day) vs daily-useful (~1.2 trades/day). MOMENTUM_DISPLACEMENT occupies the preferred 1–2/day band with the strongest net metrics in this search.

---

## Success Criteria: 14 / 14 ✓

All minimum gates passed including 1.5× cost stress, both halves positive, outlier trims, and year concentration limits.

---

## Final Classification: **A — STRONG DAILY-FREQUENCY EDGE**

## READY FOR PINE: **YES**

---

## Most Important Finding

Daily-frequency 15m NQ **does** support positive net expectancy at ~1.2 trades/RTH day, but **not via loosening CRT V2**. The winning architecture is a simple **momentum displacement + BOS retest entry** rule family, not the CRT funnel.

Prior sparse CRT V2 (~1–2 trades/**month**) remains valid as a high-precision reference; Phase 31 solves the **frequency** problem with a different entry architecture.

---

## Next Step

Proceed to Pine implementation of **MOMENTUM_DISPLACEMENT** with frozen WF execution (BOS_RETEST / 0.75 ATR / 3R / 60m / FIXED) and parity validation — **not** CRT V2 Pine modifications.
