# Phase86 — current production evaluation order

Inspected from `phase74/runtime/live_stack.py` and `phase74/quality/gates.py`.
This file is the pre-promotion snapshot. Production was not modified for Phase86.

## Live stack

1. Webhook validity + `pine_hash`.
2. **`new_entries_blocked_session`** — `SKIP_GLOBEX` outside 09:30–16:00 ET
   when `allow_globex_entries` is false. **Session is applied before quality
   gates and before continuation.** Live paper is currently in this state.
3. `evaluate_quality_gates(recent_bars(20), direction, live_atr)`.
4. `PropDayHalt` (2-loser / dollar / winner caps).
5. Frozen Phase73 `TraderEngine` (M0). No overlay state is persisted across bars.

## `evaluate_quality_gates`

1. `SKIP_DATA` — <20 bars or `atr <= 0`.
2. Window metrics (box including decision bar; `close_through` vs prior 19;
   `pa_agree` = 3-of-4 bodies).
3. **`SKIP_CHOP`** — box < 2 ATR. Always, even if `close_through` / `pa_agree`.
4. **Bypass branch:** `if not close_through and not pa_agree:`
   - `SKIP_NO_TREND` (|progress| < 0.5 ATR)
   - `SKIP_FALSE_BREAK` (near box edge)
   - `SKIP_LATE_MOVE` (progress > 1 ATR)
5. `SKIP_ATR_CAP` — ATR > 18 (config).
6. `TAKE`.

## Answers required by the spec

1. **Where is SKIP_CHOP evaluated?** `gates.py` after window build, before
   no-trend. Line ~99.
2. **Where is SKIP_NO_TREND evaluated?** Same function, inside the
   `not close_through and not pa_agree` block. Line ~103.
3. **Where is 3-of-4 evaluated?** `_recent_bodies_agree` at line ~84, stored as
   `pa_agree`, **before** the skip block.
4. **Can continuation return TAKE before no-trend?** Yes. If `pa_agree`, the
   no-trend / false-break / late-move block is skipped and the function falls
   through to TAKE (unless chop or ATR cap).
5. **Can continuation bypass a false break?** Yes. Same `pa_agree` short-circuit.
6. **Exact branch:** `if not close_through and not pa_agree:` at
   `phase74/quality/gates.py` lines 102–117, function `evaluate_quality_gates`.
7. **State persist across bars?** Quality gates are stateless per signal.
   `TrailOverlay` and `PropDayHalt` persist for management / day halt only.
   No sideways state machine is live.
8. **Session vs continuation?** Session (`SKIP_GLOBEX`) runs in `LiveStack`
   **before** `evaluate_quality_gates`. Continuation is inside the gate function.

## Overlay (research only)

`evaluate_quality_with_sideways` in `phase74/quality/sideways_overlay.py` is
**not** called by `LiveStack`. See `EVALUATION_ORDER.md`.
