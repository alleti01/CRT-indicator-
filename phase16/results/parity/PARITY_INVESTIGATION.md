# Phase 16 Pine-to-Python parity validation

## Status

**PARITY PASS — Pine-to-Python validation complete.**

The authoritative TradingView reference is the Phase 14 screenshot with the
inclusive exchange-date window 2026-06-29 through 2026-08-18. No frozen
strategy parameter or rule was changed to obtain this result. OOS was not run.

## Window and bar reconciliation

- Exchange timezone: America/Chicago.
- Inclusive start: 2026-06-29 00:00:00 CT.
- Inclusive end date: 2026-08-18.
- End-exclusive execution boundary: 2026-08-19 00:00:00 CT.
- Python five-minute bars in the window: 10,164.
- First evaluated Python bar: 2026-06-29 00:00:00 CT.
- Last evaluated Python bar: 2026-08-18 23:55:00 CT.
- Coverage: FULL DATA.

The corrected Pine screenshot shows the same start/end dates, inclusive date
handling, America/Chicago timezone, FULL DATA, Start OK, and End OK. Its
visible model and breakdown results remove exactly the August 19 activity that
caused the earlier 10,328-versus-10,164 failure. The removed 164 bars equal the
entire prior bar-count residual. The corrected event totals and all result
strata now match the 10,164-bar Python run.

## Main model comparison

| Model | Pine N/W/L | Python N/W/L | Pine Total R | Python Total R | Pine PF | Python PF | Pine DD | Python DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Control | 133/54/79 | 133/54/79 | 2.48 | 2.482752 | 1.0 | 1.035893 | 9.00 | 9.000000 |
| BOS | 97/38/59 | 97/38/59 | -2.00 | -1.998909 | 1.0 | 0.961479 | 11.92 | 11.916787 |
| Retest | 59/27/32 | 59/27/32 | 5.68 | 5.675306 | 1.2 | 1.200653 | 7.16 | 7.163578 |
| Confirm | 42/17/25 | 42/17/25 | 0.46 | 0.457088 | 1.0 | 1.021520 | 8.04 | 8.035309 |

The Pine values are displayed/rounded values. All counts are exact. Total R,
PF, Avg R, Win%, and drawdown agree at Pine's displayed precision.

## Funnel and event trace

- Raw Long: 136.
- Raw Short: 120.
- Raw total: 256.
- Canonical / Variant-C qualified: 160.
- Control attempts / accepted / already active: 160 / 133 / 27.
- BOS attempts / accepted / already active: 104 / 97 / 7.
- Retest attempts / accepted / already active: 60 / 59 / 1.
- Confirm attempts / accepted / already active: 42 / 42 / 0.

`event_debug.csv` contains one causally evaluated row for each of the 10,164
five-minute bars. `trades.csv` contains exactly 133 Control, 97 BOS, 59 Retest,
and 42 Confirm outcomes. With the corrected end boundary, no divergent setup
or trade remains to trace. The earlier first difference was an August 19 event
outside the requested window, not a Pine/Python strategy semantic difference.

## Breakdown validation

All 84 available TradingView breakdown rows pass:

- 8 direction rows.
- 12 HTF-regime rows.
- 28 session rows.
- 24 score-band rows.
- 12 date-third rows.

Each row was compared on N, Win%, Avg R, Total R, and PF at Pine's displayed
precision. Remaining mismatches: **none**. The complete row-by-row evidence is
in `breakdown_parity.csv`; the 32 main-metric comparisons are in
`parity_summary.csv`.

## Verification and next gate

- Python compilation: pass.
- Mechanics/regression tests: 13/13 pass.
- Main parity metrics: 32/32 pass.
- Breakdown rows: 84/84 pass.
- OOS gate: unlocked by `parity_summary.csv`.
- OOS execution: deliberately not started.

The project is ready for a separately selected, non-overlapping larger-history
run. The frozen settings remain unchanged, and the runner will reject any OOS
window overlapping the development parity window.
