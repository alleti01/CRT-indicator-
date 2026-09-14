# Phase84 Methodology

## Research question

Given a frozen Phase72A LONG or SHORT signal, does causal 1-minute price action
at and immediately after the signal support better execution (TAKE / WAIT / PASS)
without changing direction?

## Signal authority

Phase72A Pine remains the sole signal source. Phase72B mirror is disabled by default.

Priority: TV export → ledger export → webhook log → mirror (provisional only).

## Execution baseline (E0)

- Signal at bar T close
- Entry at bar T+1 open (Phase72A executable semantics)
- M0 via `phase73/trader/management.py`: STOP 1.0R, TARGET 2.5R, MAX HOLD 60m, STOP_FIRST
- NQ costs via `phase58/research/instrument.NQ` (14.50 USD RT baseline)

## Variants

| ID | Hypothesis |
|----|------------|
| E0 | Baseline — no price-action filter |
| E1 | Mid-range location (0.40–0.60 on 20-bar range) |
| E2 | Breakout close acceptance required |
| E3 | Failed break / rejection invalidation |
| E4 | Extension / chase pass |
| E5 | WAIT → RESET (1–3 bar causal recheck) |
| E6 | Immediate commitment (body fraction) |
| E7 | Retest + hold after impulse |
| E8 | Simple combination (only if ≥2 components validate independently) |

## Controls

- Random PASS at identical retention
- Random WAIT delay (E5/E7)
- Chronological train 60% / validation 20% / test 20%
- Rejected-trade shadow scoring (baseline E0 on every PASS)

## Causality

Truncation invariance: features and decisions at T identical with full vs truncated history.

## Pass standard

Final PASS requires ≥500 genuine Phase72A events, validation + test improvement over E0 and controls,
cost robustness, and acceptable LONG/SHORT behavior. **No production promotion from Phase84 alone.**
