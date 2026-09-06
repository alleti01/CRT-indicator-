# Phase76 — Causality / Prefix Audit

**Verdict:** `CAUSALITY_PASS`

Profile type: **BAR_APPROX_PROFILE**

## Prefix invariance tests

| Cutoff | Compared bars | Pass | Mismatches |
|--------|---------------|------|------------|
| 25% (2020-01-02) | 785,193 | PASS | 0 |
| 50% (2022-03-27) | 1,570,387 | PASS | 0 |
| 75% (2024-06-13) | 2,355,581 | PASS | 0 |
| 90% (2025-10-13) | 2,826,697 | PASS | 0 |

## Audited fields

`prior_vah`, `prior_val`, `prior_poc`, `prior_vwap`, `dev_vah`, `dev_val`, `dev_poc`, `dev_vwap`, `dev_high`, `dev_low`, `or_high`, `or_low`, `overnight_high`, `overnight_low`, `roll_high_5`, `roll_low_30`, `in_hvn`, `in_lvn`

No signal research until CAUSALITY_PASS.
