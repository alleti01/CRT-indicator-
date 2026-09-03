# Phase59B — Pine Port Variable Checklist

Status key: **IN PINE** | **MISSING** | **PARTIAL**

| Variable / Component | Python Source | Pine Mirror | TV Pine |
|---------------------|---------------|-------------|---------|
| ATR SMA14 range | `lw_data.py` | IN PINE | IN PINE |
| HTF 5M/15M lookahead_off | `align_htf_to_1m` | IN PINE | IN PINE |
| Causal swings sh/sl | `phase52/swings.py` | via MTF arrays | IN PINE (pivot lag) |
| Phase58 context | `context.py` | IN PINE | IN PINE |
| Phase58 location | `location.py` | IN PINE | IN PINE |
| 6 reaction components | `reaction.py` | IN PINE | IN PINE |
| Phase58 trader FSM | `trader_engine.py` | IN PINE | IN PINE |
| Opportunity memory | `opportunity_memory.py` | IN PINE | IN PINE |
| Evidence variant E | `evidence.py` | IN PINE | IN PINE |
| decide() E branches | `evidence.py` | IN PINE | IN PINE |
| active_move | `active_move.py` | IN PINE | IN PINE |
| structural_features | `structure.py` | IN PINE | IN PINE |
| compute_confidence | `confidence.py` | IN PINE | IN PINE |
| enrich / HIGH_CONFLICTED | `forensics.py` | IN PINE | IN PINE |
| P4 policy | `policies.py` | IN PINE | IN PINE |
| H1 filter | `filters.py` | IN PINE | IN PINE |
| T+1 entry convention | `engine.py` | IN PINE | IN PINE |
| M1 1.0 ATR / 2.5R / 60m | `management.py` | IN PINE | IN PINE |
| Overlapping M1 trades | `management.py` | IN PINE | IN PINE (8 max) |
| Reference debug Layer B | N/A | N/A | IN PINE (isolated) |
| Phase58K veto filters | N/A | NO | NO |

## Layer isolation

| Test | Requirement |
|------|-------------|
| Reference markers OFF | Automatic signal count unchanged |
| No CSV in Layer A | Mirror does not read reference CSV |
| barstate.isconfirmed | Decisions on closed bar only |

## Pine state ↔ Mirror map

See `phase59/research/pine_mirror_engine.py` → `PINE_STATE_MAP`
