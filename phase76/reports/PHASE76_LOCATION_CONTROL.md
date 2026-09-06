# Phase76 — S/R Location Control

**Verdict:** `PHASE76_LOCATION_INFORMATION_ONLY`

## Scope

- Non-directional path/activity test at auction vs simple S/R vs matched non-level controls
- Distance bands (frozen): 0.1, 0.25, 0.5 ATR
- Primary band for matching: 0.25 ATR
- Directional families A–F **permanently rejected** (checkpoint 14)

Non-level control pool: **275,358** RTH bars

## Level results (primary band vs matched non-level)

| Level | Category | n | Match | max SMD | 2-sided 15m lift | Clean exp lift | Sweep diff | Verdict |
|-------|----------|---|-------|---------|------------------|----------------|------------|---------|
| DEV_POC | auction | 44,560 | CONTROL_MATCH_FAIL | 0.1921 | — | — | — | **CONTROL_MATCH_FAIL** |
| DEV_VAH | auction | 30,196 | CONTROL_MATCH_FAIL | 0.6650 | — | — | — | **CONTROL_MATCH_FAIL** |
| DEV_VAL | auction | 26,801 | CONTROL_MATCH_FAIL | 0.4528 | — | — | — | **CONTROL_MATCH_FAIL** |
| HVN_ZONE | auction | 77,134 | ACCEPT | 0.0715 | 0.2076 | -0.0127 | 0.0238 | **MODERATE_LOCATION_INFORMATION** |
| LVN_ZONE | auction | 43,944 | CONTROL_MATCH_FAIL | 0.5101 | — | — | — | **CONTROL_MATCH_FAIL** |
| OR_HIGH | simple | 19,535 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| OR_LOW | simple | 17,633 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| OVERNIGHT_HIGH | simple | 11,457 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| OVERNIGHT_LOW | simple | 10,417 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| PRIOR_POC | auction | 9,660 | CONTROL_MATCH_FAIL | 0.4486 | — | — | — | **CONTROL_MATCH_FAIL** |
| PRIOR_SESSION_HIGH | simple | 8,930 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| PRIOR_SESSION_LOW | simple | 7,084 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| PRIOR_VAH | auction | 10,174 | CONTROL_MATCH_FAIL | 0.3762 | — | — | — | **CONTROL_MATCH_FAIL** |
| PRIOR_VAL | auction | 8,721 | CONTROL_MATCH_FAIL | 0.4802 | — | — | — | **CONTROL_MATCH_FAIL** |
| ROLL_10M_HIGH | simple | 78,990 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| ROLL_10M_LOW | simple | 75,733 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| ROLL_20M_HIGH | simple | 56,740 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| ROLL_20M_LOW | simple | 51,527 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| ROLL_30M_HIGH | simple | 46,826 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| ROLL_30M_LOW | simple | 41,181 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| ROLL_5M_HIGH | simple | 110,568 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| ROLL_5M_LOW | simple | 110,544 | N/A_SIMPLE | — | — | — | — | **N/A_SIMPLE_BASELINE** |
| VWAP | auction | 30,185 | CONTROL_MATCH_FAIL | 0.3362 | — | — | — | **CONTROL_MATCH_FAIL** |

## Head-to-head (profile vs simple S/R)

| A | B | lift 15m (A−B) | profile beats simple |
|---|----|----------------|----------------------|
| PRIOR_VAH | PRIOR_SESSION_HIGH | -0.0370 | no |
| PRIOR_VAL | PRIOR_SESSION_LOW | -0.0060 | no |
| DEV_VAH | PRIOR_SESSION_HIGH | 0.1857 | yes |
| DEV_VAL | PRIOR_SESSION_LOW | 0.3695 | yes |
| DEV_POC | VWAP | -0.1788 | no |
| PRIOR_POC | VWAP | -0.2277 | no |
| DEV_VAH | ROLL_30M_HIGH | 0.2894 | yes |
| DEV_VAL | ROLL_30M_LOW | 0.1579 | yes |
| DEV_VAH | ROLL_20M_HIGH | 0.3121 | yes |
| DEV_VAL | ROLL_20M_LOW | 0.1618 | yes |
| PRIOR_VAH | ROLL_20M_HIGH | 0.0895 | yes |
| PRIOR_VAL | ROLL_20M_LOW | -0.2138 | no |

## Answers

1. **Do auction locations produce different path behavior from matched non-level controls?** — Yes only if match ACCEPT and lift exceeds preregistered gates; see table.

2. **Is the difference practically meaningful?** — See lift/clean-expansion columns; gate requires ≥0.08 ATR two-sided lift or equivalent.

3. **Do VAH/VAL outperform prior highs/lows?** — no

4. **Does POC outperform VWAP?** — no

5. **Do profile levels outperform ordinary rolling S/R?** — 7/12 head-to-head pairs favor profile.

6. **Are reactions cleaner, more volatile, or simply more two-sided?** — Compare clean_expansion_lift vs sweep_diff in CSV.

7. **Is the effect stable chronologically?** — See split_means and year_means in checkpoint JSON.

8. **Does any location deserve use as NON-DIRECTIONAL CONTEXT?** — Only WEAK/MODERATE/STRONG verdicts; none imply directional entry.

9. **Is Phase72A context comparison justified?** — Only if PHASE76_CONTEXT_FOLLOWUP_JUSTIFIED — not if NO_AUCTION_INFORMATION.

10. **Final Phase76 verdict** — `PHASE76_LOCATION_INFORMATION_ONLY`
