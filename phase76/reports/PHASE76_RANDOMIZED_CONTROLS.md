# Phase76 — Randomized Direction Controls

Gate: 100 deterministic seeds (76001–76100). Fixed entry T+1 open.

## Summary table

| Family | N | Real +1/-1 | Rand +1/-1 | Real +2/-1 | Rand +2/-1 | Real MFE/MAE15 | Flip +2/-1 | Train +2/-1 | Val +2/-1 | Hist +2/-1 | Verdict |
|--------|---|------------|------------|------------|------------|----------------|------------|-------------|-----------|------------|---------|
| A | 17752 | 0.498 | 0.500 | 0.333 | 0.336 | 1.032 | 0.338 | 0.328 | 0.340 | 0.342 | NO_DIRECTIONAL_INFORMATION |
| B | 16662 | 0.497 | 0.500 | 0.326 | 0.332 | 0.925 | 0.339 | 0.326 | 0.324 | 0.329 | NO_DIRECTIONAL_INFORMATION |
| C | 0 | — | — | — | — | — | — | — | — | — | DATA_INSUFFICIENT |
| D | 31864 | 0.496 | 0.500 | 0.329 | 0.334 | 0.979 | 0.338 | 0.330 | 0.323 | 0.332 | NO_DIRECTIONAL_INFORMATION |
| E | 38696 | 0.501 | 0.501 | 0.335 | 0.333 | 1.016 | 0.330 | 0.342 | 0.335 | 0.313 | NO_DIRECTIONAL_INFORMATION |
| F | 43067 | 0.496 | 0.500 | 0.327 | 0.334 | 0.971 | 0.340 | 0.324 | 0.331 | 0.332 | NO_DIRECTIONAL_INFORMATION |

## Gate outcomes

- **Survivors (pass to matched S/R):** none
- **Rejected (NO_DIRECTIONAL_INFORMATION):** A, B, D, E, F
- **Inverse flagged:** none

## Per-family detail

### Family A — UPPER_VALUE_REJECTION
- N: 17752
- Verdict: **NO_DIRECTIONAL_INFORMATION**
- +1/-1: real=0.498 rand_mean=0.500 percentile=23.0 delta=-0.0027508309391020003
- +2/-1: real=0.333 rand_mean=0.336 percentile=17.0 delta=-0.0027416854750871855
- Flip +2/-1: 0.338

### Family B — LOWER_VALUE_REJECTION
- N: 16662
- Verdict: **NO_DIRECTIONAL_INFORMATION**
- +1/-1: real=0.497 rand_mean=0.500 percentile=26.0 delta=-0.0025690276110443833
- +2/-1: real=0.326 rand_mean=0.332 percentile=6.0 delta=-0.005836615144137358
- Flip +2/-1: 0.339

### Family C — INITIATIVE_ACCEPTANCE
- N: 0
- Verdict: **DATA_INSUFFICIENT**
- +1/-1: real=— rand_mean=— percentile=— delta=—
- +2/-1: real=— rand_mean=— percentile=— delta=—
- Flip +2/-1: —

### Family D — FAILED_ACCEPTANCE
- N: 31864
- Verdict: **NO_DIRECTIONAL_INFORMATION**
- +1/-1: real=0.496 rand_mean=0.500 percentile=7.000000000000001 delta=-0.0038462504316162383
- +2/-1: real=0.329 rand_mean=0.334 percentile=2.0 delta=-0.0047872547489623
- Flip +2/-1: 0.338

### Family E — LVN_TRAVERSAL
- N: 38696
- Verdict: **NO_DIRECTIONAL_INFORMATION**
- +1/-1: real=0.501 rand_mean=0.501 percentile=61.0 delta=0.0006438522577476569
- +2/-1: real=0.335 rand_mean=0.333 percentile=88.0 delta=0.002249903481366111
- Flip +2/-1: 0.330

### Family F — VALUE_ROTATION
- N: 43067
- Verdict: **NO_DIRECTIONAL_INFORMATION**
- +1/-1: real=0.496 rand_mean=0.500 percentile=7.000000000000001 delta=-0.0033413835543273374
- +2/-1: real=0.327 rand_mean=0.334 percentile=0.0 delta=-0.006366349086001921
- Flip +2/-1: 0.340

