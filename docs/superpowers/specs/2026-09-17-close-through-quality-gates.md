# Close-through quality-gate exception — design

**Date:** 2026-09-17  
**Status:** Approved in conversation; implemented in Phase74 quality gates.  
**Amends:** `docs/superpowers/specs/2026-09-10-prop-quality-gates-trail-design.md` §4.2  
**Mode:** Phase74 local paper only. Frozen Pine and Phase73 engine stay unchanged.

---

## 1. Problem

`SKIP_FALSE_BREAK` and `SKIP_LATE_MOVE` measure the last **20** 1m bars **including the signal bar**. A one-minute expansion that prints a new high is always “at the high” and often “already ran > 1 ATR.”

Live example: Thu 17 Sep **3:32 PM ET** LONG. The 15:31 bar opened 29732 and closed **29746.50** (high **29747**). That close was **0.5 pts** under the 20-bar high the same bar just made (`SKIP_FALSE_BREAK`). Progress was **+1.6 ATR**, so `SKIP_LATE_MOVE` would have blocked it next. Chart A longed; paper stayed flat. Price then ran toward 29760.

The 9:34 AM ET continuation short is **not** this exception on the live closed-bar window: close **29675.75** vs prior 19-bar low **29673.00** (still inside). Close-through is the 3:32 class (close **on or through** the prior extreme), not every continuation at the box edge.

Loosening `late_move_atr` globally is out of scope (prior replay: 5W / 20L, about −$1,811).

---

## 2. Rule

On each webhook, after the existing 20-bar window is built:

1. `SKIP_CHOP` still uses the **full 20-bar** high–low vs ATR.
2. Let `prior` = the first 19 bars.  
   - LONG **close-through** iff `close >= max(prior highs)`  
   - SHORT **close-through** iff `close <= min(prior lows)`  
   Equality counts (3:32 closed **on** the prior high 29746.50).
3. If close-through: **do not** apply `SKIP_FALSE_BREAK` or `SKIP_LATE_MOVE`.
4. `SKIP_ATR_CAP` still applies (live cap 18 NQ points).
5. If **not** close-through: false-break and late-move are unchanged (still the full 20-bar box and 20-bar close-to-close progress).

A chase that never leaves the old box still skips. A bar that **closes through** that box is treated as expansion.

---

## 3. Out of scope

- Impulse-bar extra filter (≥1.5 ATR signal bar). Rejected in favor of close-through.
- Changing `late_move_atr` / false-break percentile.
- Pine TAKE logic, Chart B ledger, Phase73 freeze.
- New log columns. Decision reason stays `TAKE` when the exception fires.

---

## 4. Tests

`phase74/tests/test_quality_gates.py`:

- LONG close ≥ prior 19-bar high → `TAKE` (even at the 20-bar high / >1 ATR progress).
- SHORT close ≤ prior 19-bar low → `TAKE`.
- LONG near the high but **not** through prior high → still `SKIP_FALSE_BREAK`.
- SHORT in the bottom 15% but **above** prior low → still `SKIP_FALSE_BREAK`.
- Close-through + tight box → still `SKIP_CHOP`.
- Close-through + ATR above cap → still `SKIP_ATR_CAP`.

---

## 5. Replay note (Sep 11–17 skips)

On the **same last-closed-bar window live used**:

- 3:32 PM ET LONG → `TAKE` (close 29746.50 ≥ prior high 29746.50).
- 3:25 PM ET SHORT → still `TAKE`.
- 9:34 AM ET SHORT → still `SKIP_FALSE_BREAK` (close 29675.75 > prior low 29673.00).
- 1:47 PM ET LONG → still `SKIP_FALSE_BREAK`.

Paper must be **restarted** to load the gate change.
