# Phase 19 — original BOS robustness

Phase 19 reproduces and stress-tests the untouched original BOS model across
2021-01-01 through 2026-06-26. All observations are development research.

- Baseline reproduction: PASS, byte-for-byte for both periods.
- Paid downloads: none.
- Phase 17 C1/C2: permanently rejected and not reconsidered.
- Frozen Phase 19 candidates: 0.

Start with `PHASE19_BOS_REPORT.md`, then inspect `WALK_FORWARD_PLAN.md` and
`FROZEN_PHASE19_CANDIDATES.md`. The charts and all machine-readable evidence are
in this directory. Reproduce with:

```bash
phase16/.venv312/bin/python phase19/analyze_bos.py
```
