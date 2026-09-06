# Phase78 README

Independent causal ICT Silver Bullet validation on NQ 1-minute data.

## Run

```bash
python3 phase78/diagnostics/run_phase78.py
```

Recompute gates from cached entries (~15s):

```bash
python3 phase78/diagnostics/run_analysis_only.py
```

## Primary outputs

- `phase78/reports/PHASE78_FINAL_REPORT.md`
- `phase78/reports/PHASE78_CAUSALITY_AUDIT.md`
- `phase78/reports/PHASE78_FUNNEL.md`
- `phase78/reports/phase78_entries.parquet`
- `phase78/examples/forensic_*.csv`

## Frozen primary config (P78-001)

- Windows: SB1 03–04, SB2 10–11, SB3 14–15 ET (tested separately, not optimized)
- Liquidity: prior session H/L, overnight H/L, session pre-window H/L, causal swings, equal H/L (0.10 ATR)
- Sequence: sweep → displacement (0.75 ATR) → MSS (5-bar) → FVG → retrace touch → T+1 entry
- Stop: structural beyond sweep extreme
- Target diagnostic: 2R, 60m max hold, stop-first
