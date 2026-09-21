# SIDEWAYS_FIX report

Replay-only framework. `LiveStack` still uses `evaluate_quality_gates` only.
`allow_globex_entries` remains false. Asia is not banned by this patch.

## VERDICT

**SIDEWAYS_FIX_FRAMEWORK_READY**

and

**SIDEWAYS_FIX_NO_INCREMENTAL_VALUE** (default grid cell 0.25 / 0.45 / 0 ATR)

Loosening overlap to 0.35 to catch the 3-of-4 losers is **SIDEWAYS_FIX_OVERFILTER**
(also kills Wed 12:27 and 1:55 winners).

**PRODUCTION MODIFIED: NO**

**RECOMMENDATION: KEEP CURRENT** (NY-only + existing gates). Do not promote.
Do not turn Globex on with this overlay.

## CURRENT SKIP_CHOP

`box < 2.0 * ATR` on the last-20 window including the decision bar.
Unchanged. Still the tight-compression gate.

## CURRENT SKIP_NO_TREND

`abs(progress) < 0.5 * ATR`, but only when
`not close_through and not pa_agree`.

## CURRENT 3-OF-4 BYPASS

`_recent_bodies_agree` (≥3 of last 4 bodies with the trade) sets `pa_agree`.
That flag short-circuits no-trend, false-break, and late-move.

## BUG / BYPASS LOCATION

`phase74/quality/gates.py` lines 102–117:

```
if not close_through and not pa_agree:
    SKIP_NO_TREND / SKIP_FALSE_BREAK / SKIP_LATE_MOVE
```

Documented in `phase74/quality/CURRENT_LOGIC_ORDER.md`.

## NEW SIDEWAYS DEFINITION

`SIDEWAYS_WIDE_RANGE` requires all of:

- `range_atr_20 >= 2.0` (not tight chop)
- `directional_efficiency_20 <= 0.25`
- `adjacent_overlap_ratio >= 0.45`
- no mixed-candle term

Escape is a **release**, not part of the predicate.

## RANGE WIDTH METRIC

`range_width_20 = max(high) - min(low)` over last 20 completed bars.
`range_atr_20 = range_width_20 / ATR`.
known_at: close of decision bar.

## DIRECTIONAL EFFICIENCY

`net_progress_20 = abs(close_now - close_20_ago)`
`total_path_20 = sum(abs(close[i] - close[i-1]))`
`directional_efficiency_20 = net_progress / total_path` (0 if path is 0).
known_at: close of decision bar.

## OVERLAP METRIC

Mean adjacent range overlap:
`inter / union` of consecutive `[low, high]` pairs in the 20-bar window.
known_at: close of decision bar.

## STRUCTURAL PROGRESS

Frozen **pre-break** wall: max high / min low of bars **before** the decision bar
(`range_upper_prebreak` / `range_lower_prebreak`). The decision bar cannot
raise its own escape wall.

## FALSE BREAK

LONG: high > pre-break upper and close ≤ upper.
SHORT: low < pre-break lower and close ≥ lower.
Wick only. Reason: `PASS_FALSE_BREAK`.

## ESCAPE RULE A

Close through the frozen pre-break wall ± buffer ATR (grid 0 / 0.05 / 0.10).
Reason: `TAKE_RANGE_ESCAPE`.

## ESCAPE RULE B

Prior bar closed through a wall frozen *before that bar*, later bar tags the
wall, all subsequent closes hold outside, last close still outside.
Reason: `TAKE_RANGE_ESCAPE_RETEST`. Failed hold → `PASS_FALSE_BREAK`.

## EVALUATION ORDER (overlay, Globex only)

1. Session (`session_key_ny`)
2. Existing `SKIP_DATA`
3. Causal 20-bar metrics
4. Existing `SKIP_CHOP`
5. Existing `SKIP_ATR_CAP`
6. `detect_sideways_state`
7. `detect_structural_escape`
8. `detect_false_break`
9. If sideways + false break → `PASS_FALSE_BREAK`
   If sideways + no escape → `PASS_SIDEWAYS_WIDE_RANGE`
10. Only then existing 3-of-4 / TAKE / remaining skips

RTH or `enabled=False`: return existing `evaluate_quality_gates` unchanged.

## 18-TRADE REPLAY

Sample: paper fills Mon 2026-09-14 – Fri 2026-09-18.
Default overlay: efficiency 0.25, overlap 0.45, buffer 0.

Replay of **current gates** already SKIPs 3 live fills (bar-window vs webhook
clock): Thu 9:17 long, Thu 6:52 short, Thu 8:20 short. Incremental stats below
count only TAKEs the current gate function would still TAKE.

### ORIGINAL TAKES

15 of 18 (replay of current `evaluate_quality_gates`).

### NEW TAKES

14 (default cell).

### LOSERS BLOCKED

0 incremental. The 3-of-4 losers stay TAKE.

### WINNERS BLOCKED

1 incremental: Fri 08:56 ET SHORT, trail +2.00R / +$226.
`PASS_SIDEWAYS_WIDE_RANGE` (eff 0.14, overlap 0.53, 3-of-4, no close-through).

### WINNER RETENTION

87.5% of current-gate winners (7/8). Live-book winners include the 8:20
mixed short, which current-gate replay already SKIPs (`SKIP_NO_TREND`).

### NET R DELTA

**−2.00R** vs current-gate TAKEs on this sample (blocks a winner, no losers).

### 3-OF-4 LOSERS

Still TAKE under the default combo. Overlap sits **0.34–0.43** (below 0.45)
while efficiency is already very low (0.01–0.07):

| Time ET | Side | Eff | Overlap | Result |
|---|---|---|---|---|
| Tue 20:15 | LONG | 0.040 | 0.429 | TAKE (3-of-4) |
| Wed 00:50 | LONG | 0.058 | 0.345 | TAKE (3-of-4) |
| Thu 19:22 | LONG | 0.010 | 0.387 | TAKE (3-of-4) |
| Thu 20:00 | SHORT | 0.054 | 0.421 | TAKE (3-of-4), 1-bar wick |
| Fri 04:46 | LONG | 0.074 | 0.396 | TAKE (3-of-4), wick false-break but not sideways |

### MIXED LOSERS

Thu 01:00 (agree 1) and Thu 09:17 / 18:52: not classified sideways at 0.45
overlap. 09:17 / 18:52 are already `SKIP_NO_TREND` in current-gate replay.

### KNOWN MIXED WINNERS

Thu 20:20 SHORT +2.43R / +$457: `continuation_3_of_4=false`, overlay does
**not** add a mixed veto. Current-gate replay is `SKIP_NO_TREND` (live filled).

Fri 14:18 RTH LONG +2R is mixed and **unchanged** (RTH freeze).

## RTH REGRESSION

**PASS.** Overlay `apply_outside_rth_only` leaves RTH reasons bit-for-bit
equal to `evaluate_quality_gates`. Test:
`test_rth_3of4_matches_existing_gates`. Existing `test_quality_gates` suite
still green.

## CAUSALITY

**PASS.** 500 as-of samples: `full[:T+1]` vs `(full+future)[:T+1]` match
decision, sideways flag, and false-break.
`test_500_asof_ignores_future_bars`.

## LARGER SAMPLE

58 paper fills (Sep 9–21). Incremental vs current-gate TAKEs:

- losers blocked: 2 (−2.0R)
- winners blocked: 3 (+7.0R)
- net R delta: **−5.0R**
- winner retention: 80%

No expectancy improvement.

## LONG / SHORT

Both sides exercised in unit tests (green 3-of-4 block, red 3-of-4 block,
long close-through escape, mixed + close-through TAKE). Replay 3-of-4 losers
are mostly longs; the one incremental default-cell skip is a short winner.

## COSTS

Replay uses booked `net_R` (paper, estimated_costs 0). No extra cost model.

## PARAMETER STABILITY

Predeclared grid only. Buffer 0 / 0.05 / 0.10 does not change the week
incremental table. Overlap is the cliff:

- 0.55: zero incremental change
- 0.45: skip Fri 8:56 winner only
- 0.35: also skip Wed 00:27 / 01:55 winners and several 3-of-4 losers
  (net still negative or flat; overfilter)

No cell both blocks the 3-of-4 loser cluster and keeps the overnight winners.

## PRODUCTION MODIFIED

**NO.** `gates.py` and `live_stack.py` are unchanged. Overlay lives in
`sideways.py` / `sideways_overlay.py` and is called only from tests and
`phase74/tools/replay_sideways_fix.py`.

## RECOMMENDATION

**KEEP CURRENT.** Framework is in place for a later sample. Do not enable
Globex and do not wire the overlay until a larger causal dataset shows
loser rejection without eating +2R overnight trails.
