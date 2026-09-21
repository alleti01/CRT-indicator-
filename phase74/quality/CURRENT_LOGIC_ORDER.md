# Current quality-gate evaluation order

Inspected from `phase74/runtime/live_stack.py` (`on_webhook_signal`) and
`phase74/quality/gates.py` (`evaluate_quality_gates`). Names below are the
actual identifiers in code.

Production has **not** been modified for the sideways overlay. This file is the
pre-change snapshot.

## Live stack (before `evaluate_quality_gates`)

1. Webhook validity + `pine_hash` match.
2. **`new_entries_blocked_session`** (`day_halt.py`) — if
   `allow_globex_entries` is false and session is not RTH 09:30–16:00
   America/New_York → **`SKIP_GLOBEX`**. This is a session ban, not a
   sideways detector. Live paper is currently in this state.
3. `evaluate_quality_gates(recent_bars(lookback), direction, live_atr)`.
4. **`PropDayHalt.should_halt_new_entries`** (2-loser / dollar / winner caps).
5. Frozen Phase73 `TraderEngine.on_webhook_signal` (M0 entry / stop / target).

## `evaluate_quality_gates` (exact order)

1. **`SKIP_DATA`** — fewer than `lookback_bars` (20) or `atr <= 0`.
2. Build the last-20 window. Compute:
   - `box` / `box_atr` from **window including the decision bar**
     (`max(high) - min(low)`).
   - Signed `progress` (LONG: last close − first close; SHORT: first − last).
   - `percentile_in_box`.
   - **`close_through`**: LONG `close > max(high of prior 19)`; SHORT
     `close < min(low of prior 19)`. Wick-only does not qualify.
   - **`pa_agree`** (`_recent_bodies_agree`): ≥ `pa_min_bodies` (3) of the last
     `pa_lookback_bars` (4) bodies in trade direction.
3. **`SKIP_CHOP`** — `box <= 0` or `box < chop_box_atr * atr` (default 2.0 ATR).
   Fires even if `close_through` or `pa_agree`. Tight compression only.
4. **Hidden continuation bypass** — the entire next block is skipped when
   `close_through or pa_agree`:

   ```python
   if not close_through and not pa_agree:
       # SKIP_NO_TREND / SKIP_FALSE_BREAK / SKIP_LATE_MOVE
   ```

5. **`SKIP_NO_TREND`** — `abs(progress) < no_trend_atr * atr` (0.5 ATR).
   **Bypassed by `pa_agree` (3-of-4) and by `close_through`.**
6. **`SKIP_FALSE_BREAK`** — close near the *including-current-bar* box edge
   (`false_break_percentile` 0.15 or `false_break_edge_atr` 0.25) without
   `close_through`. **Bypassed by `pa_agree`.**
7. **`SKIP_LATE_MOVE`** — signed `progress > late_move_atr * atr` (1.0 ATR).
   **Bypassed by `pa_agree` and by `close_through`.**
8. **`SKIP_ATR_CAP`** — `atr > max_atr_points` (config 18.0; class default 15.0).
   Not bypassed by continuation.
9. **`TAKE` / `TAKE`**.

## Bug / bypass location

`phase74/quality/gates.py` lines 102–117:

```
if not close_through and not pa_agree:
    SKIP_NO_TREND / SKIP_FALSE_BREAK / SKIP_LATE_MOVE
```

**3-of-4 (`pa_agree`) is evaluated before no-trend / false-break / late-move
and short-circuits all three.** That is the failure mode: three same-color
bodies inside a 3–6 ATR overlapping box with ~0 net progress still `TAKE`.

`close_through` is a separate, legitimate bypass (strict close vs prior-19
high/low). It is not the 3-of-4 bug.

## Session classification (actual)

`session_key_ny` in `day_halt.py`:

- 09:30 ≤ t < 16:00 ET → `rth`
- t ≥ 16:00 ET → `globex` (same calendar date)
- t < 09:30 ET → `globex` (previous calendar date)

There is no Asia / London / Tokyo label in production.

## What SKIP_CHOP does and does not catch

- Catches: 20-bar box **< 2 ATR** (`TIGHT_CHOP`).
- Does not catch: box **3–6 ATR** with low efficiency (wide overlapping range).
  Last-week Globex losers sat in that second bucket.

## Overlay (not in production)

`evaluate_quality_with_sideways` in `sideways_overlay.py` is replay-only.
`LiveStack` does not call it. `quality_gates.allow_globex_entries` stays false
until a later promotion decision.
