# Phase75 — Chop / Regime Research

**Mode:** Observational only — no strategy or shadow behavior changes.

## Summary

- Canonical TAKE trades analyzed: **126**
- Event stream decisions: **131** TAKE, **53** PASS/WAIT
- Overall mean M0 net R: **0.606**

### M0 net R by bar regime (30m efficiency classifier)

| Regime | n | mean net R | win rate |
|--------|---|------------|----------|
| CHOP | 101 | 0.581 | 48.5% |
| UNCERTAIN | 25 | 0.705 | 52.0% |

### M0 net R by Pine `market_state`

| market_state | n | mean net R | win rate |
|--------------|---|------------|----------|
| UNCERTAIN | 93 | 0.504 | 46.2% |
| REVERSAL_TRANSITION | 21 | 1.200 | 66.7% |
| PULLBACK | 10 | 0.298 | 40.0% |
| CONTINUATION | 2 | 0.639 | 50.0% |

### TAKE events by bar regime

| Regime | events | TAKE % |
|--------|--------|--------|
| CHOP | 110 | 69.6% |
| UNCERTAIN | 21 | 80.8% |

- TAKE with 15m NEUTRAL: **21** / 131 (mean M0 net R **0.06**, win rate **33%**)

## Findings (auto)

1. **15m NEUTRAL is the strongest loss cluster** — 21 trades, mean R 0.06, win rate 33%. Best candidate for a future `PASS_REGIME` gate (not bar-level CHOP).
2. **Bar-level CHOP does not explain bad R** — CHOP trades still average **0.58R** (n=101). Filtering CHOP alone would remove most trades without clear edge improvement on this sample.
3. **REVERSAL_TRANSITION is the best Pine `market_state`** — 21 trades, mean R **1.20**, win rate 67%.
4. **Pine `market_state=UNCERTAIN`** is common (93 trades) but still positive at mean R 0.50 — not a chop filter by itself.
5. **Recent bar sample is mostly CHOP** (81%) with almost no TREND bars — classifier may be strict on this window, or the period was genuinely range-bound.

## Recommendation (post-shadow)

- **Do not** gate on bar CHOP alone — research does not support it.
- **Do** shadow-log `15m_state` and `regime_observed` on live signals; test hypothetical `PASS_REGIME` when `15m_state == NEUTRAL`.
- Keep Pine Layer A frozen until `FORWARD_SHADOW_PASS`.

## Artifacts

- `phase75/reports/chop_regime_trades.csv`
- `phase75/reports/chop_regime_events.csv`
- `phase75/reports/chop_regime_summary.json`
