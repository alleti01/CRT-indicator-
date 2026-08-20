# Phase 18 — sacred unseen NQ validation

This directory permanently records the one-time 2021–2023 validation of the exact frozen Phase 17 C1/C2 candidates.

- C1: **D — OOS FAIL**
- C2: **D — OOS FAIL**
- Evaluation: 2021-01-01 through 2023-12-28 inclusive, America/Chicago
- Data: Databento `GLBX.MDP3` continuous `NQ.v.0`, 212,019 evaluated five-minute bars
- Cost estimate: $3.9816

Read `data_validation.md` before `PHASE18_OOS_REPORT.md`. Phase 18 data is now observed and may not be reused as unseen OOS after any strategy change.

Reproduction requires the already frozen Phase 16 environment and the exact hashes in `results/reproducibility_manifest.json`. The backtest command was:

```bash
phase16/.venv312/bin/python phase16/run_backtest.py \
  --data phase18/data/processed/nq_5m.csv \
  --start 2021-01-01 --end 2023-12-28 \
  --mode oos --contracts prepared \
  --parity-report phase16/results/parity/parity_summary.csv \
  --debug-events --output phase18/results/base_run
```
