# First real parity report

Prior package verdict (preserved): `CDX_RE_INSUFFICIENT_INFORMATION`

## Run 2026-09-21 data alignment

Verdict: `CDX_RE_DATA_EXTENSION_FAIL`  
Trusted Databento series still ended 2026-09-02 10:48 CT. 10/10 MEDIUM unmatched. V1 not scored.

## Run 2026-09-21 Windows recovery (this machine)

Verdict: `CDX_RE_DATA_EXTENSION_FAIL`

- DATABENTO_API_KEY_PRESENT: false
- DATABENTO_AUTH: NOT ATTEMPTED
- NinjaTrader CSV: absent on this Mac
- Official MEDIUM exact / ±1: 0 / 10
- Candidate V1 scored: NO (frozen, not retuned)
- Feature / transition / state analysis: NOT RUN
- Canonical Databento series modified: NO

A local TradingView `NQ1!` 1-minute export (883 bars, Sep 21 07:18–23:00 ET, no volume) was **not** used. It is not Databento and not NinjaTrader, and it cannot satisfy the 7/10 gate.

See `cdx_research/reports/WINDOWS_DATA_RECOVERY.md` and `cdx_research/runs/2026-09-21_windows_recovery/`.
