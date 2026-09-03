# Displacement Failure / Reversal Report

**Classification:** B  
**Ready for Pine:** YES

## Executive Summary

Phase 33 tested whether **failed 15m momentum displacement** produces an independent reversal edge complementary to Phase 31 continuation. Stitched walk-forward (2020–2026 OOS) on the selected causal failure + entry + execution stack shows **positive net expectancy** after $14.50 RT costs, but with lower frequency and higher drawdown than Phase 31.

**Most important finding:** Reversal edge exists in walk-forward OOS (N=1,031, Net AvgR +0.185R, PF 1.46), driven mainly by **midpoint reclaim within 4 bars + RECLAIM_RETEST entry**. Phase 31 continuation remains the primary engine; reversal adds ~0.44 trades/day when run independently.

## Displacement Population

| Metric | Value |
|--------|------:|
| Total RTH displacement bars | 8,118 |
| Failure event rows (all definitions) | 32,245 |
| Displacements with ≥1 failure signal | 8,118 (100%) |
| Phase 31 continuation fill within 2 bars | ~99.8% of bars |

Most displacement candles still qualify for Phase 31 BOS_RETEST continuation on the next 1–2 bars because the displacement extreme **is** the BOS level. Reversal research therefore targets the subset where failure confirmation + reversal entry filters produce a **different** trade population.

## Best Walk-Forward Stack (stitched OOS)

| Parameter | Selection |
|-----------|-----------|
| Failure definition | **A_MID_4** (midpoint reclaim within 4 bars) |
| Entry | **RECLAIM_RETEST** |
| Stop | **0.75 ATR** |
| Target | **2.5R** |
| Hold | **45m** |
| Management | FIXED |

## Stitched Walk-Forward — Phase 33 Reversal

| Metric | Value |
|--------|------:|
| N | 1,031 |
| Trades/day | 0.44 |
| Win Rate | 49.4% |
| Net AvgR | +0.185R |
| Net TotalR | +190.3R |
| Net PF | 1.46 |
| MaxDD | 21.2R |
| Return/MaxDD | 8.96 |

## Directional Results

| Segment | N | Win Rate | AvgR | PF |
|---------|---:|---:|---:|---:|
| Bearish disp → Long reversal | 521 | 50.5% | +0.193R | 1.49 |
| Bullish disp → Short reversal | 510 | 48.2% | +0.176R | 1.44 |

Both directions positive OOS.

## Yearly (stitched WF)

| Year | N | Trades/day | AvgR | TotalR | PF |
|------|---:|---:|---:|---:|---:|
| 2020 | 31 | 0.12 | -0.094R | -2.9R | 0.79 |
| 2021 | 141 | 0.55 | -0.013R | -1.8R | 0.97 |
| 2022 | 147 | 0.57 | +0.241R | +35.5R | 1.67 |
| 2023 | 173 | 0.67 | +0.113R | +19.5R | 1.27 |
| 2024 | 219 | 0.85 | +0.322R | +70.5R | 1.87 |
| 2025 | 213 | 0.83 | +0.180R | +38.3R | 1.45 |
| 2026 | 107 | 0.86 | +0.291R | +31.1R | 1.76 |

2024–2026 combined: **positive** (+140R).

## Robustness

| Test | Result |
|------|--------|
| 1.5× costs | AvgR +0.171R, PF 1.42 |
| 2.0× costs | AvgR +0.158R, PF 1.38 |
| Exclude top 1% winners | AvgR +0.160R, PF 1.40 |
| Monte Carlo P(R>0) | **100%** |
| MC median terminal R | +190.3R |
| Failure-strength monotonicity | **NO** |

## Phase 31 Benchmark vs Phase 33 vs Combined

| System | N | Trades/day | AvgR | PF | MaxDD |
|--------|---:|---:|---:|---:|---:|
| Phase 31 continuation | 2,873 | 1.22 | +0.233R | 1.47 | 15.1R |
| Phase 33 reversal | 1,031 | 0.44 | +0.185R | 1.46 | 21.2R |
| Combined (INDEPENDENT) | 3,904 | 1.78 | +0.220R | 1.47 | 16.8R |

**Best conflict policy:** INDEPENDENT (exit/flip policies did not improve combined metrics in this causal simulation).

## Answers

- **Do failed displacements predict reversals?** YES — OOS reversal expectancy is positive after costs.
- **Can continuation vs failure be distinguished causally?** PARTIALLY — continuation BOS_RETEST fills dominate timing; failure filters select a distinct, sparser reversal population.
- **Does reversal logic improve the complete system?** YES modestly — combined AvgR +0.220R vs Phase 31 alone +0.233R on overlapping calendar; reversal adds diversification and total R (+860R combined vs +670R Phase 31).

## Next Step

Implement Phase 33 as a **complementary Pine reversal module** (keep Phase 31 continuation unchanged). Do **not** use EXIT_AND_FLIP until live-conflict policy is validated. Start with INDEPENDENT alerts.
