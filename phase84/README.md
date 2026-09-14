# Phase84 — Phase72A Price-Action Execution Quality

**Hypothesis:** Given a frozen Phase72A LONG/SHORT signal, causal 1M price action
at and after the signal can improve execution (TAKE / WAIT / PASS) without
changing signal direction.

**Not in scope:** Signal discovery, direction prediction, production changes.

## Signal provenance (strict)

1. `phase84/data/phase72a_tv_export.csv` — REAL_TV_EXPORT
2. `phase84/data/phase72a_ledger_export.csv` — REAL_LEDGER_EXPORT
3. `forward_rehearsal/reports/WEBHOOK_ALERTS_FULL.csv` — REAL_WEBHOOK_LOG
4. Mirror streams — disabled (`PROVISIONAL_MIRROR_FLAG=False`)

Final PASS requires **≥500 genuine Phase72A events**. Phase72B is not ground truth.

## M0 authority

- Path: `phase73/trader/management.py`
- Functions: `build_management`, `evaluate_exit`
- STOP 1.0R, TARGET 2.5R, MAX HOLD 60m, STOP_FIRST

## Run

```bash
python3 phase84/diagnostics/run_phase84.py
```

## Isolation

- No imports from Phase83
- Does not modify Phase72A Pine, Phase73, Phase74
