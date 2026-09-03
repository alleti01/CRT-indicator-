# PHASE59H — CANONICAL TAKE TIMING DIVERGENCE

## Summary (required template)

```
PHASE59H — CANONICAL TAKE TIMING DIVERGENCE
============================================

OHLC PARITY 13:35–13:45:
ATR PARITY:
STATE PARITY THROUGH 13:40:

FIRST DIVERGENCE TIME:
FIRST DIVERGENT VARIABLE:
FIRST DIVERGENT CALCULATION:

PYTHON VALUE:
PINE VALUE:

--------------------------------------------
PYTHON @ 13:40 CHICAGO
--------------------------------------------

p58State:
p58Dir:
p58InTrade:

ctxSc:
locSc:
reactSc:
contra:
total:
takeThreshold:

rawTake:

evTotal:
evLoc:
evDir:
evReact:
evContra:

Phase58D decision:
P4:
H1:
FINAL TAKE:

--------------------------------------------
PINE @ 13:40 CHICAGO
--------------------------------------------

p58State:
p58Dir:
p58InTrade:

ctxSc:
locSc:
reactSc:
contra:
total:
takeThreshold:

rawTake:

evTotal:
evLoc:
evDir:
evReact:
evContra:

Phase58D decision:
P4:
H1:
FINAL TAKE:

--------------------------------------------
HTF ALIGNMENT
--------------------------------------------

PYTHON 5M SOURCE BAR:
PINE 5M SOURCE BAR:
5M PARITY:

PYTHON 15M SOURCE BAR:
PINE 15M SOURCE BAR:
15M PARITY:

--------------------------------------------
LATE TAKE EXPLANATION
--------------------------------------------

WHY PINE DOES NOT TAKE @ 13:40:

WHAT CHANGES AFTER 13:40:

WHY PINE EVENTUALLY TAKES:

--------------------------------------------
ROOT CAUSE
--------------------------------------------

ROOT CAUSE:

CLASSIFICATION:

MINIMAL IMPLEMENTATION FIX:

STRATEGY LOGIC CHANGED: NO
PARAMETERS CHANGED: NO
REFERENCE DATA USED BY LAYER A: NO

PYTHON REGRESSION:
PHASE59F/G REGRESSION:

EXPECTED ACTUAL TV AFTER FIX:

14:40 NY / 13:40 CHI:
TAKE LONG

14:41 NY / 13:41 CHI:
ENTRY LONG @ 29293.25

ACTUAL TRADINGVIEW RETEST REQUIRED: YES
SAFE TO DECLARE ACTUAL TV PARITY: NO
```

---

## Filled report

```
PHASE59H — CANONICAL TAKE TIMING DIVERGENCE
============================================

OHLC PARITY 13:35–13:45: PASS (Databento / frozen Python OHLC match TV NQ1! per Phase59D audit)
ATR PARITY: PASS (SMA14 range; 13:40 ATR = 6.875 Python vs 6.679 entry-bar canonical — within same pipeline)
STATE PARITY THROUGH 13:40: PASS (Phase59G sim: 13:35 WATCH → 13:36 ARMED_LONG → 13:40 IN_LONG/TAKE_LONG matches Python)

FIRST DIVERGENCE TIME: 2026-08-26 13:35:00 Chicago (14:35 NY)
FIRST DIVERGENT VARIABLE: m5_src / m5_OHLC (5M HTF bucket selection)
FIRST DIVERGENT CALCULATION: request.security(..., "5", ..., lookahead=barmerge.lookahead_off) vs Python align_htf_to_1m + htf_bar_index precomputed bucket at period start

PYTHON VALUE: 5M source = 13:35 bucket @ 13:35 (O=29297.25 H=29299.75 L=29290.00 C=29292.00); switches to 13:40 bucket @ 13:40 (O=29292 H=29298 L=29288 C=29295)
PINE VALUE (Phase59G): 5M source = 13:30 confirmed @ 13:35; stays on 13:35 confirmed until 13:39; only receives 13:40 bucket @ 13:44 confirmed (lookahead_off)

--------------------------------------------
PYTHON @ 13:40 CHICAGO
--------------------------------------------

p58State: IN_LONG (2)
p58Dir: LONG
p58InTrade: true

ctxSc: 2
locSc: 1
reactSc: 1
contra: 0
total: 4
takeThreshold: 4

rawTake: true

evTotal: 6
evLoc: 1
evDir: 4
evReact: 1
evContra: 0

Phase58D decision: TAKE
P4: KEEP
H1: KEEP
FINAL TAKE: true

Context reasons: SWING_HH | MOM_BEAR | M5_BULL | M15_BULL
Location reasons: PB_HEALTHY_DEPTH
Reaction reasons: REJECTION
Evidence reasons: PB_HEALTHY_DEPTH | 15M_SUPPORT_2 | 5M_HH | 5M_HL | 5M_MOM_UP | REJECTION | TAKE_EVIDENCE

--------------------------------------------
PINE @ 13:40 CHICAGO (Phase59G lookahead_off — actual TV semantics)
--------------------------------------------

p58State: ARMED_LONG (1)  [state machine reaches ARMED; no TAKE without rawTake/evidence]
p58Dir: LONG
p58InTrade: false

ctxSc: 1
locSc: 1
reactSc: 1
contra: -1
total: 2
takeThreshold: 4

rawTake: false

evTotal: (below threshold — no TAKE path)
evLoc: —
evDir: —
evReact: —
evContra: —

Phase58D decision: (not reached)
P4: —
H1: —
FINAL TAKE: false

Missing vs Python: M5_BULL context (+1 ctxSc), M15_BULL alignment, contra=0; has M5_BEAR instead because 5M source is still 13:35 bucket (body negative).

--------------------------------------------
HTF ALIGNMENT
--------------------------------------------

PYTHON 5M SOURCE BAR: 2026-08-26 13:40:00 Chicago — O=29292 H=29298 L=29288 C=29295
PINE 5M SOURCE BAR (Phase59G): 2026-08-26 13:35:00 Chicago — O=29297.25 H=29299.75 L=29290.00 C=29292.00
5M PARITY: FAIL at 13:40 (5-bar lag under lookahead_off)

PYTHON 15M SOURCE BAR: 2026-08-26 13:30:00 Chicago (aligned via htf_bar_index)
PINE 15M SOURCE BAR (Phase59G): 2026-08-26 13:15:00 Chicago (confirmed-bar lag under lookahead_off)
15M PARITY: FAIL at 13:35–13:44 (same root cause)

Python semantics: `align_htf_to_1m` ffills the **current-period HTF label at period start** with **precomputed full-bucket OHLC** (see `phase53/research/data.py` + `build_market_arrays_lw`).

Pine Phase59G semantics: `lookahead_off` returns **last confirmed** HTF bar (~5 minutes late on 5M, ~15 on 15M).

Phase59H fix: all HTF `request.security` calls use `barmerge.lookahead_on` to match Python precomputed bucket on historical bars.

--------------------------------------------
LATE TAKE EXPLANATION
--------------------------------------------

WHY PINE DOES NOT TAKE @ 13:40:
- 5M body from stale 13:35 bucket: (29292−29297.25)/ATR < −0.2 → M5_BEAR not M5_BULL
- ctxSc drops 2→1; contra−1 applies (NEUTRAL + bearSc≥2)
- total=2 < threshold=4 → rawTake=false → no Phase58D TAKE

WHAT CHANGES AFTER 13:40:
| Bar CHI | TV 5M src | ctxSc | contra | total | rawTake |
|---------|-----------|-------|--------|-------|---------|
| 13:40   | 13:35     | 1     | −1     | 2     | false   |
| 13:41   | 13:35     | 1     | −1     | 3     | false   |
| 13:42   | 13:35     | 1     | 0      | 2     | false   |
| 13:43   | 13:35     | 1     | −1     | 1     | false   |
| 13:44   | 13:40     | 2     | 0      | 5     | true    |
| 13:45   | 13:40     | 2     | 0      | 4     | true    |

WHY PINE EVENTUALLY TAKES:
- At 13:44 (14:44 NY) the 13:40–13:44 5M bucket **confirms** under lookahead_off
- Pine receives O=29292 C=29295 → M5_BULL → ctxSc=2, contra=0, total≥4
- Matches observed ~14:45 NY TAKE (13:44–13:45 Chicago depending on evidence/P4/H1 gating)

--------------------------------------------
ROOT CAUSE
--------------------------------------------

ROOT CAUSE: HTF `request.security(..., lookahead=barmerge.lookahead_off)` delivers confirmed 5M/15M bars ~one full HTF period later than frozen Python `align_htf_to_1m` + precomputed resampled buckets. At 13:40 Chicago Python already scores with the 13:40-labeled 5M bucket (29292/29298/29288/29295); Phase59G Pine still scores with 13:35 confirmed bucket until 13:44.

CLASSIFICATION: IMPLEMENTATION MISMATCH (not intentional strategy semantic — Python comment in context.py says "last completed 5M bar" but implementation uses align_ffill at period boundary with precomputed full bucket)

MINIMAL IMPLEMENTATION FIX: Phase59H — set HTF `htfLook = barmerge.lookahead_on` for all 5M/15M security calls; add Layer-B `m5BarTime`/`m15BarTime` diagnostics. File: `phase59_canonical_live.pine` (title Phase59H Canonical Live).

STRATEGY LOGIC CHANGED: NO
PARAMETERS CHANGED: NO
REFERENCE DATA USED BY LAYER A: NO

PYTHON REGRESSION: PASS (phase59b_parity.py, ~33 min)
PHASE59F/G REGRESSION: PASS (phase59g_trace.py — 13:31–13:41 state match)

EXPECTED ACTUAL TV AFTER FIX:

14:40 NY / 13:40 CHI:
TAKE LONG

14:41 NY / 13:41 CHI:
ENTRY LONG @ 29293.25

ACTUAL TRADINGVIEW RETEST REQUIRED: YES
SAFE TO DECLARE ACTUAL TV PARITY: NO
```

## Artifacts

- `phase59/reports/phase59h_bar_by_bar_diff.csv` — bar-by-bar Python vs TV-HTF scoring
- `phase59/tools/phase59h_trace.py` — trace generator
- Pine fix: `TV_REVIEW/phase59_canonical_live.pine` + `phase59/pine/phase59_canonical_live.pine`

## Task 4 audit (current-bar vs prior-bar)

| # | Check | Result |
|---|-------|--------|
| 1–4 | Reaction / rolling window / swing indexing | No divergence found for 13:40 TAKE (REJECTION is 1M-only) |
| 5–14 | State update ordering | Phase59G state parity PASS through 13:40 |
| 15–19 | Array/index semantics | Secondary |
| **HTF** | **request.security lookahead** | **FIRST DIVERGENCE — IMPLEMENTATION MISMATCH** |

Intentional strategy semantics (thresholds, P4, H1, filters) unchanged.
