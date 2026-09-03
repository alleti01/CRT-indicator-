# Phase 50 — Repaint Audit

## request.security (15M Phase44)

| Check | Result |
|-------|--------|
| `lookahead` | `barmerge.lookahead_off` — **PASS** |
| `gaps` | `barmerge.gaps_off` — **PASS** |
| Partial 15M bar values | Not used; bundle runs on confirmed 15M bars only — **PASS** |

## Phase44 timing

| Check | Result |
|-------|--------|
| Signal on 15M bar close | Yes — fill events emitted on confirmed 15M bar — **PASS** |
| Actionable = marker + 15 min | Matches Python `CHART_15M=15` — **PASS** |

## B1 timing

| Check | Result |
|-------|--------|
| Causal swing pivots | Only bars ≤ current 1M bar — **PASS** |
| Window inclusive [actionable, actionable+10m] | Matches Python `_window_indices` — **PASS** |
| Entry at confirming bar close | Matches Python — **PASS** |

## M0 timing

| Check | Result |
|-------|--------|
| Management from bar after entry | `p50PosHeld >= 1` before exit checks — **PASS** |
| Stop before target same bar | Stop checked first — **PASS** |

## Answers

| Question | Answer |
|----------|--------|
| CAN PHASE44 REPAINT? | **NO** (with lookahead_off + confirmed 15M) |
| CAN B1 REPAINT? | **NO** (causal swings, confirmed 1M close) |
| CAN LONG/SHORT SIGNALS DISAPPEAR? | **NO** (one-shot confirmation flags per bar) |

## Residual platform risk

- TradingView 15M bar timestamps may differ from Databento aggregation at session boundaries → **DATA/PLATFORM**, not logic
- Continuous contract roll vs Python NQ.v.0 — document symbol config
