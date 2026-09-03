# Phase69A — 73.2% Reconciliation

## Phase69 claimed
- **26,481 / 36,174 = 73.2%**
- Label in narrative: *reaching +2.5R MFE (stop held)*

## Actual M0 target exits
- **10,432 = 28.8%**

## ROOT CAUSE
phase69/python/path_audit.py counterfactual_after_r() computed UNCONDITIONAL cumulative MFE from entry bar without stop ordering. 'Stop held' was never implemented — any trade whose price eventually touched +2.5R counted, even if -1R stop occurred first.

## Evidence

| Metric | Value |
|--------|-------|
| Buggy Phase69 count (exact repro) | 26,481 (73.2%) |
| TRUE +2.5R before stop | 10,432 (28.8%) |
| Post-stop fake MFE trades | 15,894 (60.0% of buggy cohort) |
| MFE_A ≥2.5R (unconditional) | 73.2% |
| MFE_B ≥2.5R (pre-M0 exit) | 29.1% |

## Answers
- **Did MFE continue after original stop?** YES — 15,894 trades
- **Was stop actually enforced?** NO in Phase69 path_audit
- **Was 'stop held' implemented?** NO — label only
- **Was MFE over fixed horizon regardless of stop?** YES (121 bars from entry bar)
- **Code:** `phase69/python/path_audit.py` → `counterfactual_after_r()`