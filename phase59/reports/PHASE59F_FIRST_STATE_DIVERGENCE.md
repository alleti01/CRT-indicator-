# PHASE59F — FIRST STATE DIVERGENCE

**Date:** 2026-08-31  
**Scope:** Implementation parity only — no strategy/threshold changes.

---

## Executive Summary

TradingView OHLC at **14:26** and **14:31 NY** matches frozen Python/Databento **exactly**. The spurious **LONG / TAKE LONG** at **14:31 NY** is **not** a data mismatch. It is caused by a **Pine Phase58 internal-trade lifecycle bug**: stop/target were initialized with **entry-bar open + entry-bar ATR** instead of **entry-bar close (Python `cl[i+1]` proxy) + signal-bar ATR**.

That tightened the SHORT internal stop by **~2.89 points** (29283.25 vs 29286.15), causing a **premature internal STOP at 13:29 Chicago** while Python remains **IN_SHORT** until **13:32**.

---

## PHASE59F — FIRST STATE DIVERGENCE

```
14:26 OHLC TV/PYTHON: MATCH
14:31 OHLC TV/PYTHON: MATCH

FIRST DIVERGENCE BAR:        2026-08-26 13:27:00 Chicago (14:27 NY)
FIRST DIVERGENT VARIABLE:    internal_stop (p58Stop)
PYTHON VALUE:                29286.147321428572
PINE VALUE (pre-fix):        29283.254464285714

FIRST STATE DIVERGENCE BAR:  2026-08-26 13:29:00 Chicago (14:29 NY)
FIRST STATE VARIABLE:        p58InTrade
PYTHON VALUE:                True (IN_SHORT)
PINE VALUE (pre-fix):        False (premature EXIT_STOP → COOLDOWN)

ROOT CAUSE:
  Pine recalculated Phase58 internal stop on entry bar using open and
  entry-bar ATR. Frozen Python TraderEngine._take_trade() uses
  m.cl[entry_i] (entry-bar close as open proxy) and atr[signal_i].

CODE LOCATION:
  TV_REVIEW/phase59_canonical_live.pine
  - TAKE block ~1066–1075 (pre-fix: ep58=close provisional stop)
  - Entry-bar finalize ~1089–1094 (pre-fix: p58Entry:=open, atrUse entry bar)

PINE IMPLEMENTATION BUG PROVEN: YES

MINIMAL FIX:
  Store signal-bar ATR at TAKE (p58SignalAtr).
  On entry bar (T+1): p58Entry := close; stop/target from p58SignalAtr.
  Matches trader_engine.py lines 196–205 and 229–230 (entry bar excluded).

STRATEGY LOGIC CHANGED: NO
PARAMETERS CHANGED: NO
```

---

## Bar-by-Bar Timeline (Chicago / NY)

| Chi | NY | Event | Python p58InTrade | Pine (pre-fix) | Notes |
|-----|-----|-------|-------------------|----------------|-------|
| 13:26 | 14:26 | TAKE_SHORT | 1 | 1 (after close) | OHLC match ✓ |
| 13:27 | 14:27 | Internal entry finalize | 1 | 1 | **Stop diverges** (29286.15 vs 29283.25) |
| 13:28 | 14:28 | HOLD | 1 | 1 | H=29282.25 < both stops |
| 13:29 | 14:29 | HOLD | 1 | **0 EXIT** | H=29285.0 ≥ Pine stop 29283.25 |
| 13:30 | 14:30 | HOLD | 1 | 0 COOLDOWN | Python still in SHORT |
| 13:31 | 14:31 | HOLD (reactL=3) | 1 | 0 WATCH | **Pine can arm LONG** → spurious TAKE |
| 13:32 | 14:32 | EXIT_STOP | 0 | 0 | Python stop hit (H=29289.5) |
| 13:36 | 14:36 | ARMED_LONG | 0 | varies | Canonical path |
| 13:40 | 14:40 | TAKE_LONG | 1 | — | LW-063138 signal |
| 13:41 | 14:41 | ENTRY | 1 | — | LW-063138 @ 29293.25 |

---

## Execution Semantics Audit

| Rule | Python | Pine pre-fix | Pine post-fix |
|------|--------|--------------|---------------|
| TAKE on signal bar T | ✓ | ✓ | ✓ |
| Internal entry T+1 | cl[i+1] proxy | open | **close** (matches Python) |
| Stop ATR source | atr[signal_i] | atr[entry_i] | **p58SignalAtr** |
| Entry bar excluded from stop eval | i > entry_i | bar_index > p58EntryBar | unchanged ✓ |
| Signals blocked while p58InTrade | ✓ | ✓ (when in trade) | ✓ (stays in through 13:31) |
| Opposite arm while IN_SHORT | blocked | blocked when in trade | blocked |

**Stop-first:** Both use stop-before-target on same bar (Pine lines 912–914; Python 239–248).

---

## ATR Check (focus bars)

| Chi | Python ATR | OHLC TV=PY |
|-----|-------------|------------|
| 13:26 | 7.196 | MATCH |
| 13:31 | 6.982 | MATCH |
| 13:32 | 6.946 | MATCH |
| 13:33 | 7.536 | MATCH |
| 13:40 | 6.875 | MATCH |
| 13:41 | 6.678571428571429 | MATCH |

ATR is not the root cause at focus bars; stop **initialization** used wrong ATR bar.

---

## Fix Applied (Phase59F)

**File:** `TV_REVIEW/phase59_canonical_live.pine` (synced to `phase59/pine/`)

```pine
var float p58SignalAtr = na

// At TAKE:
p58SignalAtr := atrUse
p58Entry := na  // finalized next bar

// On entry bar:
p58Entry := close
risk58 = p58StopAtr * p58SignalAtr
p58Stop / p58Target from p58Entry + risk58
```

Indicator title bumped to **Phase59F Canonical Live**. Layer B forensic inputs unchanged (default off).

---

## Post-Fix Expected Sequence (simulated vs Python)

```
POST-FIX 13:26 SHORT:           YES (TAKE_SHORT unchanged)
POST-FIX 13:31 LONG BLOCKED:    YES (p58InTrade=1 through 13:31)
POST-FIX 13:40 TAKE LONG:       YES (unchanged canonical path)
POST-FIX 13:41 LW-063138 ENTRY: YES (29293.25, ATR 6.679)

Simulated internal stop @ 13:27: 29286.147 (exact Python match)
Simulated p58InTrade @ 13:31:    True (matches Python)
Simulated exit @ 13:32:          STOP (matches Python)
```

---

## Parity Regression

| Test | Status |
|------|--------|
| LAST-WEEK 126/126 (Python mirror) | **PASS** — `phase59b_parity.py` FINAL VERDICT PASS (874s, exit 0) |
| OUTSIDE-WEEK PARITY | **PASS** (included in same run) |
| M1 OUTCOME PARITY | **PASS** (included in same run) |
| LW-063138 regression | **PASS** (included in same run) |

Run: `python3 phase59/tools/phase59b_parity.py`

---

## Artifacts

| File | Description |
|------|-------------|
| `phase59/reports/phase59f_bar_by_bar_diff.csv` | Full 13:20–13:45 Python vs broken/fixed Pine internal state |
| `phase59/reports/phase59f_state_transition_diff.csv` | State transition log |
| `phase59/tools/phase59f_trace.py` | Repro script |

---

## Final Verdict Block

```
PHASE59F — FIRST STATE DIVERGENCE

14:26 OHLC TV/PYTHON: MATCH
14:31 OHLC TV/PYTHON: MATCH

FIRST DIVERGENCE BAR: 13:27 Chicago (internal_stop)
FIRST DIVERGENT VARIABLE: internal_stop / p58Stop
PYTHON VALUE: 29286.147321428572
PINE VALUE: 29283.254464285714 (pre-fix)

ROOT CAUSE: Entry-bar open+ATR stop init vs Python close[i+1]+signal ATR
CODE LOCATION: phase59_canonical_live.pine TAKE + entry-bar finalize

PINE IMPLEMENTATION BUG PROVEN: YES

MINIMAL FIX: p58SignalAtr + entry-bar close stop finalize
STRATEGY LOGIC CHANGED: NO
PARAMETERS CHANGED: NO

POST-FIX 13:26 SHORT: YES
POST-FIX 13:31 LONG BLOCKED: YES (simulated)
POST-FIX 13:40 TAKE LONG: YES (unchanged)
POST-FIX 13:41 LW-063138 ENTRY: YES (unchanged)

LAST-WEEK 126/126 PARITY: PASS (phase59b_parity.py)
OUTSIDE-WEEK PARITY: PASS
M1 OUTCOME PARITY: PASS

ACTUAL TV RECHECK REQUIRED: YES
SAFE TO CONTINUE: YES (after TV confirms canonical sequence)
```

---

## TradingView Recheck Procedure

1. Paste full updated `phase59_canonical_live.pine` (~1300 lines).
2. Confirm title **Phase59F Canonical Live** compiles with zero errors.
3. NQ1! 1M Aug 26 2026 — verify:
   - 14:26 TAKE SHORT
   - **No** LONG 14:31–14:33
   - 14:32 SHORT stop (internal)
   - 14:36 ARMED LONG
   - 14:40 TAKE LONG
   - 14:41 ENTRY LW-063138
4. Optional: enable `phase59eForensic=true` and confirm table shows `p58InTrade=1` at 14:31 NY.
