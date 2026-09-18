# SKIP_NO_TREND — design

**Date:** 2026-09-17  
**Status:** Implemented in Phase74 quality gates.  
**Amends:** `docs/superpowers/specs/2026-09-10-prop-quality-gates-trail-design.md` §4.2  
**Mode:** Phase74 local paper only.

---

## 1. Problem

`SKIP_CHOP` only blocks a **tight** 20-bar box (`< 2.0 ATR`). Evening Sep 17 fills sat in **3–5 ATR** boxes, mid-range, with ~0 net progress. Chart A flipped short/long/stop in sideways tape. Paper took them.

## 2. Rule

After chop, if the signal is **not** close-through and `|20-bar close-to-close progress| < 0.5 ATR` → `SKIP_NO_TREND`.

- Close-through still bypasses no-trend, false-break, and late-move.
- `|progress| == 0.5 ATR` is a TAKE (strict `<`).
- Config: `quality_gates.no_trend_atr` (default **0.5**).

Order: chop → (if not through: no-trend → false-break → late-move) → ATR cap.

## 3. Replay (paper fills, live logged progress, 1 NQ $20/pt)

At 0.50 ATR the rule would have removed 8 fills: 3W / 5L, net **+$204** (includes Thu 6:05 AM +$263 and tonight’s three evening stops −$268). 3:25 PM short stays (`−1.19 ATR`).

Paper must be restarted to load the change. Do not restart while a trade is open.
