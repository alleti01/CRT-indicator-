# Phase72A Event Marker Audit

**File:** `TV_REVIEW/phase72a_autonomous_trader.pine`  
**Audit date:** 2026-09-02

## Verdict (after fix)

| Event | Plots marker? | Label text | Gated by |
|-------|---------------|------------|----------|
| SIGNAL_LONG | YES | `SIGNAL_LONG` | `showTake` + canonical TAKE |
| SIGNAL_SHORT | YES | `SIGNAL_SHORT` | `showTake` + canonical TAKE |
| ENTER_LONG | YES | `ENTER_LONG` | `showEntry` + pending entry T+1 |
| ENTER_SHORT | YES | `ENTER_SHORT` | `showEntry` + pending entry T+1 |
| EXIT_STOP | YES | `EXIT_STOP` | `showExits` + stop hit (STOP_FIRST) |
| EXIT_TARGET | YES | `EXIT_TARGET` | `showExits` + target hit |
| EXIT_TIME_PROGRESS | YES | `EXIT_TIME_PROGRESS` | `showExits` + T5 fail |
| EXIT_MAX_HOLD | YES | `EXIT_MAX_HOLD` | `showExits` + 60m timeout |

State variables `lastAction` / `lastReason` mirror these on each event.

## Pre-fix findings (FAIL)

Before this patch:

- **SIGNAL_*** used `TAKE LONG` / `TAKE SHORT` (wrong name)
- **ENTER_*** not plotted — `f_addM1Trade` removed but Phase71 entry block missing
- **EXIT_TIME_PROGRESS** not implemented (no T5 in active path)
- **EXIT_MAX_HOLD** used legacy `TIME LONG` from overlapping array trades
- Phase71 `posState` stuck at `PENDING_*` without entry/management loop

## Notes

- Markers only appear when the **autonomous signal engine fires** — not on every Python frozen signal
- Use `phase72a_python_review_ghosts.pine` for Python-expected locations regardless of autonomous fires
- Default display inputs: `showTake=true`, `showEntry=true`, `showExits=true`
