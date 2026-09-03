# Phase59 / 59B No-Repaint Audit

## Layer A — Automatic Engine

| Component | Causal rule | Status |
|-----------|-------------|--------|
| 1M decisions | `barstate.isconfirmed` only | PASS |
| Phase58 trader | Closed bar state machine | PASS |
| Phase58D evidence | Computed at signal bar only | PASS |
| P4 / H1 | At signal bar only | PASS |
| Canonical TAKE | Finalized on bar T close | PASS |
| Pending entry | Executes at T+1 open | PASS |
| 5M / 15M HTF | `request.security(..., lookahead=barmerge.lookahead_off)` | PASS |
| Opportunity memory | Online `match_or_create`, no future swings | PASS |
| M1 management | Entry bar excluded; stop before target | PASS |
| Realtime | No intrabar TAKE; label on bar close | PASS |

## Layer B — Reference Debug (isolated)

| Rule | Status |
|------|--------|
| `debugParityMarkers` default **false** | PASS |
| Reference `input.time` unix ms used ONLY when debug ON | PASS |
| Layer B does not set `pendingTake`, `phase58d_decision`, or trade arrays | PASS |
| Parity harness: mirror runs without reference CSV | PASS |

## Prohibited (absent)

- No `lookahead_on`
- No CSV timestamps in signal path
- No centered pivot decisions
- No Phase58K veto filters
- No reference markers affecting automatic count (verified in phase59b_parity.py)

## Actual TradingView

Manual chart inspection required after loading `TV_REVIEW/phase59_canonical_live.pine` on NQ1! 1M.
