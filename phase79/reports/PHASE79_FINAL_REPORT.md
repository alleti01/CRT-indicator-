# Phase79 — ATM Management Model Test

**Verdict:** `PHASE79_ATM_REJECT`

## Signal authority
- Pine SHA256: `d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f`
- Signal stream hash: `0da41f282174679f`
- Source: `phase60/diagnostics/cache/canon_full_phase60.parquet`
- Date range: 2017-10-01 19:03:00-05:00 → 2026-08-28 14:18:00-05:00
- Executed (one-position, current market data): 35,845 (skipped 329)
- Independent M0 anchor: N=36,174 AvgR=0.015992 (reproduced exactly)
- Note: Phase72 one-position N was 35,902; drift from extended OHLCV is documented, not a management change

## Collision / causality policy
- STOP_FIRST when stop and target on same bar (Phase73 M0 frozen policy)
- BE trigger + BE stop same bar: activate BE if trigger reached without initial stop; then BE stop if low/high touches offset stop on same bar
- No trailing before +1R; no partials; no future MFE/MAE for decisions

## Comparison (net R, $14.50 RT cost)

| Metric | BASELINE | ATM-A | Delta |
|--------|----------|-------|-------|
| Trades | 35,845 | 35,845 | — |
| Win Rate | 0.291 | 0.190 | -0.101 |
| AvgR | 0.0157 | -0.3580 | -0.3736 |
| PF | 1.022 | 0.510 | -0.512 |
| TotalR | 561.0 | -12831.5 | -13392.5 |
| MaxDD | 180.2 | 12829.3 | +12649.0 |
| Median R | -1.000 | -1.040 | -0.040 |
| Initial stops | 25,359 | 18,369 | — |
| BE stops | 0 | 11,446 | — |
| Targets | 10,333 | 5,987 | — |
| Time exits | 153 | 43 | — |
| Avg hold (min) | 6.1 | 3.9 | — |
| Median hold | 3.0 | 2.0 | — |

**BE activation rate:** 44.4%

## Breakeven attribution
- **ATM_SAVED_LOSERS:** N=6,787 (26.8% of baseline stops), R saved=5565.6
- **ATM_KILLED_WINNERS:** N=4,346 (42.1% of baseline targets), R damage=11865.1
- **Path forensics (target trades hitting +1R then BE before 2.5R):** N=4,308 (41.7%)
- **Net R from BE rule:** saved − damage = **-6299.4**

## Gross R
- Baseline gross AvgR: 0.0157 | ATM-A: -0.0779 | Δ -0.0936

## Pass gate failures
- AvgR did not improve
- TotalR did not improve
- PF materially deteriorated (>5%)
- MaxDD materially worse (>10%)
- LONG AvgR did not improve
- SHORT AvgR did not improve

Completed in 175.5s
