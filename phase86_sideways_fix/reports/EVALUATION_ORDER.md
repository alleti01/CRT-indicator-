# Phase86 candidate evaluation order

Used only when `SidewaysOverlayConfig.enabled` and session is Globex
(09:30–16:00 ET is identity with `evaluate_quality_gates`).

1. SESSION CLASSIFICATION — `session_key_ny` (`rth` / `globex`).
2. DATA HEALTH — existing `SKIP_DATA`.
3. EXISTING HARD GATES — `SKIP_CHOP`, `SKIP_ATR_CAP`.
4. CAUSAL 20-BAR STATE — `compute_window_metrics`.
5. EXISTING TIGHT SKIP_CHOP — already returned if box < 2 ATR.
6. SIDEWAYS_WIDE_RANGE — `detect_sideways_state` (efficiency + overlap + wide).
7. PRE-BREAK RANGE BOUNDARY — `range_upper_prebreak` / `range_lower_prebreak`
   from bars before T.
8. STRUCTURAL ESCAPE — Route A close-through, Route B retest-hold.
9. FALSE-BREAK CHECK — wick beyond frozen wall, close back inside.
10. OUTSIDE RTH:
    - sideways + false break → `PASS_FALSE_BREAK`
    - sideways + no valid escape → `PASS_SIDEWAYS_WIDE_RANGE`
11. ONLY NOW: existing `evaluate_quality_gates` continuation / TAKE
    (`TAKE_EXISTING_CONTINUATION` if 3-of-4 and not sideways-blocked).
12. EXISTING TAKE/PASS FLOW for remaining reasons (`SKIP_NO_TREND`, etc.).

3-of-4 cannot return TAKE before steps 6–10.

RTH: overlay not applied. Decision and reason match production gates
bit-for-bit.

Forbidden: `if Asia: PASS`, `if mixed_last_4: PASS`, `if sideways: PASS forever`.
