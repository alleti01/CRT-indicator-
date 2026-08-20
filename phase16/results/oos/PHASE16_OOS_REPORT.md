# Phase 16 — Databento acquisition and frozen OOS validation

## Final status

**RETEST FAIL.** Pine-to-Python parity remained passed, the untouched OOS run
completed with FULL DATA coverage, and no strategy rule or parameter was
changed. The frozen Retest candidate produced negative expectancy over the
requested OOS window.

## Databento cost and range

- Dataset/schema: GLBX.MDP3 / ohlcv-1m.
- Instrument: Databento continuous `NQ.v.0` (CME E-mini Nasdaq-100 futures).
- Main request estimate: $3.3127.
- Post-window coverage segment: $0.0015.
- Total estimated acquisition cost: **$3.3142**.
- Raw acquisition range: 2023-12-01 00:00 UTC through 2026-06-29 05:00 UTC
  exclusive, including causal warm-up and right-side coverage bars.
- Frozen OOS evaluation range: 2024-01-01 through 2026-06-26 inclusive in
  America/Chicago.
- Development range begins 2026-06-29; overlap rows: **0**.

## Data preparation and validation

- Downloaded/merged raw 1m rows: **907,810**.
- Unique normalized 1m rows: **907,810**.
- Final processed 5m rows including warm-up/post-window coverage: **181,614**.
- Final 5m bars inside the OOS window: **176,022**.
- Sorted timestamps: pass.
- Duplicate raw identities: 0.
- Duplicate 5m timestamps: 0.
- Invalid OHLC rows: 0.
- Timezone: America/Chicago during processing; UTC ISO timestamps are stored in
  the CSV and converted back to exchange time by the loader.
- Provider-selected contract transitions: 11.
- Maximum adjusted roll gap: 0.0 points.
- Short intraday gaps in the final 5m series: 0.
- Non-empty 5m buckets with fewer than five emitted Databento 1m records: 230;
  retained to match the data semantics used by the passed parity run.

Roll method: preserve Databento's continuous-contract `instrument_id`
transitions, then apply the existing causal forward additive splice. At each
transition, the incoming contract is shifted so its first adjusted open equals
the outgoing contract's last adjusted close. No future observations select or
price a roll.

Databento emitted degraded-quality warnings for 2024-09-18, 2025-09-17,
2025-09-24, 2025-11-28, 2026-01-31, 2026-03-15, 2026-03-16, 2026-03-21,
2026-04-10, and 2026-05-24. Seven Retest trades touched those dates and summed
to -2.1533R. Excluding them as a diagnostic only—not as the reported result—
would leave approximately -29.68R, so the warnings do not explain the OOS
failure.

## Frozen funnel

- Raw setups: 4,921 (2,552 Long / 2,369 Short).
- Canonical Variant-C opportunities: 3,355.
- Control: 3,355 attempts / 2,730 entries.
- BOS: 1,958 attempts / 1,867 entries.
- Retest: 1,093 attempts / 1,061 entries.
- Confirm: 715 attempts / 705 entries.
- Entry retention versus Control: Control 100.00%, BOS 68.39%, Retest 38.86%,
  Confirm 25.82%.

## All-model comparison

| Model | N | Wins | Losses | Win % | Avg R | Total R | PF | Max DD R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Control | 2,730 | 1,122 | 1,604 | 41.10 | -0.0095 | -25.86 | 0.982 | 51.00 |
| BOS | 1,867 | 779 | 1,087 | 41.72 | 0.0034 | 6.29 | 1.006 | 39.73 |
| Retest | 1,061 | 429 | 629 | 40.43 | -0.0300 | -31.83 | 0.942 | 39.52 |
| Confirm | 705 | 289 | 415 | 40.99 | -0.0363 | -25.62 | 0.930 | 42.44 |

Three Retest trades finished exactly flat, so wins plus losses is three below
N. The candidate's largest win was +2R, largest loss -1R, maximum winning
streak 7, and maximum losing streak 10.

## Retest stability

- Positive months: 12 of 30; negative months: 18 of 30.
- Positive quarters: 4 of 10; negative quarters: 6 of 10.
- 2024: -23.96R.
- 2025: -6.66R.
- 2026 through June 26: -1.21R.
- Best month: 2024-03, +12.93R.
- Worst month: 2025-12, -10.90R.

Context totals show the weakness was broad rather than one isolated period:

- Direction: Long -30.52R; Short -1.32R.
- HTF regime: Bull +10.81R; Bear -38.66R; Neutral -3.99R.
- Session: Premarket +2.95R; all other session buckets were negative.
- Score: only 90-94 was positive (+1.47R); 95+ was -20.10R.

These are measurements only. No subgroup was removed and no threshold was
changed after observing OOS.

## Deliverables

- Raw data: `phase16/data/raw/`.
- Processed data: `phase16/data/processed/nq_5m.csv`.
- Data validation: `phase16/results/oos/data_validation/`.
- All-model summary: `model_comparison.csv`.
- Frozen Retest summary: `oos_summary.csv`.
- Monthly/quarterly results: `monthly_results.csv`, `quarterly_results.csv`.
- Direction, score, session, and HTF breakdowns: `breakdowns.csv`.
- Trade/event audit: `trades.csv`, `event_debug.csv`.
- Equity/drawdown data and charts: `equity_curve.csv`, `equity_curve.png`,
  `drawdown_curve.png`.

## Conclusion

The requested historical data was acquired, normalized, roll-adjusted,
validated, and tested. The frozen Retest model **fails Phase 16 OOS** because
Total R and Avg R are negative, PF is below 1, and the drawdown is materially
larger than the absolute return. Phase 16 execution is complete; the research
result is a failure, not a basis for post-OOS optimization.
