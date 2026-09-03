# PHASE59G — SECOND STATE DIVERGENCE

**Date:** 2026-08-31  
**Scope:** Post–Phase59F forensic — missing LW-063138 LONG at 13:40/13:41 Chicago.  
**No strategy/threshold changes.**

---

## PHASE59G — SECOND STATE DIVERGENCE

```
OHLC PARITY 13:31–13:41: PASS (user-confirmed + Python Databento reference)

FIRST STATE DIVERGENCE (post-13:31, pre-Phase59G):
  Bar: 2026-08-26 13:34:00 Chicago (14:34 NY) — then 13:35 ARMED timing
  Variable: p58State
  PYTHON @ 13:34: 3 (COOLDOWN)
  PINE Phase59F @ 13:34: 1 (ARMED_LONG) — cooldown decremented on exit bar
  PYTHON @ 13:35: 0 (WATCH)
  PINE Phase59F @ 13:35: 1 (ARMED_LONG) — armed same bar cooldown ended

POST-PHASE59G SIM (Python OHLC): p58State matches Python 13:31–13:41 inclusive

13:26 SHORT TAKE PARITY: YES (TV + Python, post-Phase59F)
13:26 SHORT ENTRY PARITY: YES (internal entry 29280.75, stop 29286.15)

SHORT EXIT TIME PYTHON: 13:32 Chicago / 14:32 NY
SHORT EXIT TIME PINE (Phase59F): 13:32 Chicago (same bar, same STOP)
SHORT EXIT REASON PYTHON: EXIT_STOP
SHORT EXIT REASON PINE: STOP (high 29289.5 ≥ stop 29286.147)

p58InTrade @ 13:32 PYTHON/PINE: False / False
p58State @ 13:33 PYTHON/PINE: 3 COOLDOWN / 3 COOLDOWN
p58State @ 13:36 PYTHON/PINE: 1 ARMED_LONG / 1 ARMED_LONG (after fix)
p58State @ 13:40 PYTHON/PINE: 2 IN_LONG / 2 IN_LONG (sim)

13:40 TAKE LONG PYTHON: YES (rawTake, decision TAKE_LONG)
13:40 TAKE LONG PINE (sim, Python OHLC): YES
13:41 ENTRY LONG PYTHON: YES @ 29293.25 (LW-063138)
13:41 ENTRY LONG PINE (sim): YES (pending M1 entry T+1)

ROOT CAUSE:
  Two Pine implementation ordering bugs after Phase59F internal-stop fix:

  1. COOLDOWN DECREMENT ON EXIT BAR (primary 13:34 divergence)
     Python TraderEngine._close_trade() returns immediately; cooldown_remaining
     is NOT decremented on the exit bar. Pine decremented cooldownRem on the
     same bar as internal STOP, reaching WATCH one bar early (13:34 vs 13:35).
     That caused ARMED_LONG one bar before Python (13:34 vs 13:36).

  2. STALE ARMED STATE WHILE p58InTrade (TV symptom: st=-1 SHORT at 14:40)
     If p58InTrade=true but p58State remains ARMED (±1) — e.g. partial bar
     ordering — signal generation is blocked (not p58InTrade check entered
     with stale ARMED), while forensic markers show st=-1 SHORT. Python
     short-circuits to HOLD/IN_* whenever st.trade is active.

CLASSIFICATION: PINE_STATE_MACHINE_MISMATCH (implementation ordering)

MINIMAL IMPLEMENTATION FIX (Phase59G):
  1. p58SkipCooldownDec — skip cooldownRem decrement on internal exit bar
  2. p58BlockSignals — skip signal generation on bar cooldown ends (Python early return)
  3. Move entry-bar stop finalize BEFORE internal manage block
  4. Coerce p58State to IN_LONG/IN_SHORT when p58InTrade and state is ARMED
  5. Clear p58Dir on internal exit (match Python direction="")

STRATEGY LOGIC CHANGED: NO
PARAMETERS CHANGED: NO
PYTHON REGRESSION: PASS (phase59b_parity.py)
ACTUAL TRADINGVIEW RETEST REQUIRED: YES
```

---

## 13:26 SHORT Lifecycle (Python reference)

| Chi | Event | p58InTrade | p58State | internal stop | Notes |
|-----|-------|------------|----------|---------------|-------|
| 13:26 | TAKE_SHORT | 1 | IN_SHORT (-2) | (pending) | signal ATR 7.196 |
| 13:27 | HOLD / entry finalize | 1 | IN_SHORT | 29286.147 | entry=29280.75 |
| 13:31 | HOLD | 1 | IN_SHORT | 29286.147 | reactL=3, LONG blocked |
| 13:32 | EXIT_STOP | 0 | COOLDOWN (3) | — | H=29289.5 hits stop |
| 13:33 | COOLDOWN | 0 | COOLDOWN | — | rem=2 (Python) |
| 13:34 | COOLDOWN | 0 | COOLDOWN | — | rem=1 (Python) |
| 13:35 | WATCH | 0 | WATCH (0) | — | rem=0 |
| 13:36 | ARMED_LONG | 0 | ARMED (1) | — | |
| 13:40 | TAKE_LONG | 1 | IN_LONG (2) | — | canonical signal |
| 13:41 | ENTRY | 1 | IN_LONG | — | LW-063138 @ 29293.25 |

---

## Execution-order audit

| Step | Python | Pine pre-59G | Pine post-59G |
|------|--------|--------------|---------------|
| Internal exit bar cooldown tick | **Skip** | Decrement same bar | **Skip** (p58SkipCooldownDec) |
| Entry stop finalize vs manage | N/A (set at TAKE) | After signal block | **Before manage** |
| IN_* while p58InTrade | trade short-circuit | ARMED can display | **Coerce to IN_*** |
| p58Dir on internal exit | `direction=""` | Stale until WATCH | **Clear on exit** |

---

## Why TV showed st=-1 SHORT at 14:40 (hypothesis)

With Phase59F OHLC parity at 13:26–13:31, the spurious 14:31 LONG is fixed (internal
IN_SHORT blocks). Forensic **st=-1 SHORT** at 14:40 indicates **ARMED_SHORT**, not
IN_SHORT (-2):

- If **p58InTrade=0**: stuck ARMED from 13:24 without canonical internal TAKE completing
  (Phase58D/P4/H1 abstain) — would invalidate on BULLISH unless blocked.
- If **p58InTrade=1** with **st=-1**: inconsistent — blocks all signal generation including
  LONG arm/take; matches missing 13:40 LONG. Phase59G coercion fixes this.

**TV must confirm** at 14:40: `p58InTrade`, `p58State`, `decision`, `rawTake` from E59 table.

---

## Artifacts

| File | Description |
|------|-------------|
| `phase59/reports/phase59g_bar_by_bar_diff.csv` | 13:31–13:41 Python vs Pine sim |
| `phase59/tools/phase59g_trace.py` | Replay + ordering sim |

---

## TradingView recheck (required)

1. Paste **Phase59G Canonical Live** (~1305 lines)
2. Aug 26 2026 NQ1! 1M with `phase59eForensic=true`
3. Confirm sequence:
   - 14:32 SHORT internal STOP
   - **14:36** (not 14:34) ARMED LONG
   - **14:40** TAKE LONG, **st=2 LONG** or **st=1 LONG** with rawTake=1
   - **14:41** ENTRY LONG @ 29293.25
4. At 14:40 verify **not** st=-1 SHORT

---

## Safe to continue

**YES** after TV confirms 13:40/13:41 LONG. Do not declare TV parity PASS from Python mirror alone.
