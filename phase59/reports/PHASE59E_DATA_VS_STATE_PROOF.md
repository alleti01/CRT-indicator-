# PHASE59E — Data vs State Proof

**Purpose:** Conclusively distinguish `DATA_SERIES_MISMATCH` from `PINE_STATE_MACHINE_MISMATCH`.  
**No strategy logic or parameter changes.**

---

## Decision Rule (Phase59E)

Compare TradingView OHLC to Databento (Python) bar-by-bar starting at **13:20 Chicago**.

| Condition | Classification |
|---|---|
| First state divergence occurs on a bar where **OHLC already differs** | **DATA_SERIES_MISMATCH** |
| OHLC **identical** through first state divergence | **PINE_STATE_MACHINE_MISMATCH** |

**Do not classify on suspicion alone.** TV OHLC must be recorded from chart (Data Window / E59 table / markers).

---

## Python / Databento Reference — Full Window

**Export:** `phase59/reports/phase59e/python_trace_1320_1345_chicago.csv` (26 bars)  
**Focus:** `python_trace_1324_1334_chicago.csv` (11 bars)  
**TV fill-in template:** `tv_vs_python_comparison_template.csv`  
**Tool:** `python3 phase59/tools/phase59e_trace.py`

### Key bars — Python canonical state

| Chi | NY | O | H | L | C | ATR | p58InTrade | p58State | p58Dir | reactL | reactS | ctxDir | rawTake | decision | internal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 13:24 | 14:24 | 29281.0 | 29281.75 | 29276.0 | 29277.5 | 7.393 | 0 | -1 ARMED_S | SHORT | 0 | 2 | BEARISH | 0 | ARMED | — |
| 13:26 | 14:26 | 29280.0 | 29281.25 | 29277.0 | 29277.5 | 7.196 | **1** | -2 IN_SHORT | SHORT | 1 | 1 | BEARISH | **1** | **TAKE_SHORT** | entry 29280.75 stop 29286.15 |
| 13:27 | 14:27 | 29277.75 | 29281.5 | 29274.75 | 29280.75 | 7.339 | **1** | -2 IN_SHORT | SHORT | 2 | 0 | BEARISH | 0 | HOLD | same |
| 13:31 | 14:31 | 29279.0 | 29283.0 | 29278.0 | 29282.75 | 6.982 | **1** | -2 IN_SHORT | SHORT | **3** | 0 | BULLISH | 0 | HOLD | **blocked** |
| 13:32 | 14:32 | 29282.5 | 29289.5 | 29281.0 | 29288.5 | 6.946 | 0 | 3 COOLDOWN | — | 2 | 0 | BULLISH | 0 | EXIT_STOP | internal SHORT stop |
| 13:33 | 14:33 | 29288.25 | 29303.5 | 29288.25 | 29300.25 | 7.536 | 0 | 3 COOLDOWN | — | 2 | 0 | BULLISH | 0 | WATCH | — |
| 13:36 | 14:36 | 29297.25 | 29298.25 | 29293.5 | 29298.0 | 7.196 | 0 | 1 ARMED_L | LONG | 1 | 0 | BULLISH | 0 | ARMED | — |
| 13:40 | 14:40 | 29292.0 | 29293.75 | 29288.5 | 29293.5 | 6.875 | 1 | 2 IN_LONG | LONG | 1 | 0 | BULLISH | 1 | TAKE_LONG | canonical signal |
| 13:41 | 14:41 | 29293.25 | 29294.75 | 29290.75 | 29293.75 | **6.679** | 1 | 2 IN_LONG | LONG | 2 | 1 | BULLISH | 0 | HOLD | **LW-063138 entry** |

### Critical Python facts

| Question | Answer |
|---|---|
| **13:26 SHORT present in Python?** | **YES** — TAKE_SHORT @ 13:26, entry 13:27 @ 29277.75 (mirror path) / internal entry 29280.75 |
| **13:31 Python IN_SHORT?** | **YES** — reactL=3 but **HOLD** (no LONG) |
| **13:32 Python** | Internal SHORT **EXIT_STOP** → COOLDOWN |
| **Early 13:31 Python LONG?** | **NO** |
| **LW-063138** | Signal 13:40, entry 13:41 @ 29293.25 |

---

## TradingView Comparison Procedure

1. Paste updated Pine; enable **`phase59eForensic=true`**
2. Chart: **NQ1!**, 1M, ETH, note **B-ADJ on/off**
3. Navigate Aug 26 2026 — orange markers appear **13:24–13:45 Chicago** (14:24–14:45 NY)
4. **Middle-right table** shows cursor bar (last bar on chart): OHLC, ATR, p58InTrade, p58State, reactL/S, ctxDir, rawTake, decision
5. Fill `tv_vs_python_comparison_template.csv` OR compare marker text to Python table above
6. First bar where `tv_* ≠ db_*` for OHLC → record timestamp
7. First bar where OHLC matches but `tv_p58State` / `tv_p58InTrade` / `tv_decision` ≠ Python → state mismatch

---

## Symbol / Continuous Series Audit

### TradingView NQ1! (user chart)

| Setting | Value |
|---|---|
| Symbol | NQ1! (CME E-mini Nasdaq-100 continuous front month) |
| Roll rule | TV volume-based rule (may switch before/after CME roll week) |
| **B-ADJ** | **On** (per user) — [TradingView docs](https://www.tradingview.com/support/solutions/43000685266-how-can-i-enable-backadjustment-for-continuous-futures/): historical bars adjusted by roll-gap coefficient; **prices are not actual traded levels** |
| Session | ETH (extended) |

### Databento Python (frozen)

| Setting | Value |
|---|---|
| Symbol | **NQ.v.0** (volume continuous, GLBX.MDP3) |
| Adjustment | Databento native volume roll — **not** TV B-ADJ |
| Session | CME Globex; index → America/Chicago |
| Source | `phase58j/data/nq_continuous_1m_lw_extension.csv` + stitched history |

### Underlying outright contract (Aug 26 2026)

| Field | Value |
|---|---|
| Expected front month | **NQU26** (September 2026) |
| Roll from NQM26 | ~June 15, 2026 (CME equity index roll week) |
| Expiration NQU26 | Third Friday Sep 18, 2026 |

**UNDERLYING CONTRACT MATCH:** **UNKNOWN** until TV outright **NQU26** OHLC compared to Databento on same timestamps.

**DATA IDENTIFICATION TEST (no strategy change):**
- Compare **NQU26** (non-continuous) vs Databento on 13:24–13:45
- Compare **NQ1! B-ADJ OFF** vs Databento
- Compare **NQ1! B-ADJ ON** vs Databento

If **NQU26** matches Databento but **NQ1!** does not → continuous construction mismatch, not outright data error.

---

## Expected Divergence Scenarios

### If DATA_SERIES_MISMATCH (most likely if TV ≠ Databento OHLC)

- Different OHLC from **13:20 or earlier** → different ATR, swings, reaction scores
- 13:26 SHORT may **not fire** on TV → no IN_SHORT block at 13:31
- TV may **arm/take LONG ~13:31** (user observation) → `p58InTrade` blocks 13:40 LW-063138

### If PINE_STATE_MACHINE_MISMATCH (only if OHLC identical)

- Same OHLC through 13:31 but TV `p58InTrade=0` while Python `=1`
- Or TV `rawTake=1` LONG at 13:31 while Python `HOLD` with same reactL=3
- Would indicate Pine internal-trade gate bug — **not** yet proven

---

## Comparison Grid (fill from TV)

| Time Chi | OHLC match? | Python state | TV state (fill) | State match? | First diff var |
|---|---|---|---|---|---|
| 13:24 | ? | ARMED_SHORT | | | |
| 13:26 | ? | TAKE_SHORT / IN_SHORT | | | |
| 13:31 | ? | IN_SHORT / HOLD | | | |
| 13:32 | ? | EXIT_STOP / COOLDOWN | | | |
| 13:40 | ? | TAKE_LONG | | | |
| 13:41 | ? | HOLD / entry | | | |

---

## Pine Instrumentation Added (Layer B only)

| Control | Effect |
|---|---|
| `phase59eForensic=true` | Table on last bar + markers 13:24–13:45 Chicago |
| Markers | CHI HH:MM, O/H/L/C, ATR, p58InTrade, p58State, p58Dir, reactL/reactS |
| Table | TIME NY/CHI, OHLC, ATR, p58InTrade, p58State, p58Dir, reactL/S, ctxDir, rawTake, decision |

**Zero Layer A impact.**

---

## PHASE59E — DATA VS STATE PROOF

```
PHASE59E — DATA VS STATE PROOF
==============================

FIRST DIVERGENCE TIME:
UNRESOLVED — requires TradingView OHLC + state from chart

TV OHLC:
PENDING user capture @ first divergent bar

DATABENTO OHLC:
See python_trace_1320_1345_chicago.csv

OHLC PARITY AT FIRST DIVERGENCE:
UNRESOLVED

ATR PYTHON @ 13:41: 6.678571428571429
ATR PINE:   same on Databento bars; TV PENDING

PYTHON STATE @ 13:31: IN_SHORT (p58State=-2), reactL=3, decision=HOLD
PINE STATE:  PENDING (user: spurious LONG ~13:31-13:33)

PYTHON p58InTrade @ 13:31: 1 (SHORT)
PINE p58InTrade: PENDING

PYTHON DIRECTION @ 13:31: SHORT (internal)
PINE DIRECTION:  PENDING (user: LONG opportunity)

PYTHON REACT L/S @ 13:31: 3 / 0
PINE REACT L/S:  PENDING

13:26 SHORT PRESENT IN PYTHON: YES
13:26 SHORT PRESENT IN ACTUAL PINE: PENDING

EARLY 13:31 PINE LONG PRESENT (user report): YES (TV)
EARLY 13:31 PYTHON LONG PRESENT: NO

DATA SERIES IDENTICAL THROUGH FIRST STATE DIVERGENCE:
UNRESOLVED — TV OHLC not yet recorded

TRADINGVIEW CONTINUOUS SERIES: NQ1! CME, 1M ETH, B-ADJ ON
DATABENTO CONTINUOUS SERIES: NQ.v.0 volume continuous

UNDERLYING CONTRACT MATCH: UNKNOWN (test NQU26 vs Databento)

ROOT CAUSE PROVEN: NO

CLASSIFICATION: UNRESOLVED
(pending TV OHLC proof — leading hypothesis DATA_SERIES_MISMATCH if TV OHLC ≠ Databento)

STRATEGY LOGIC CHANGED: NO
PARAMETERS CHANGED: NO

SAFE TO FIX: NO
SAFE TO CONTINUE STRATEGY DEVELOPMENT: NO
```

---

## Files

| Path | Description |
|---|---|
| `phase59/tools/phase59e_trace.py` | Python export tool |
| `phase59/reports/phase59e/python_trace_1320_1345_chicago.csv` | Full forensic window |
| `phase59/reports/phase59e/python_trace_1324_1334_chicago.csv` | 13:24–13:34 focus |
| `phase59/reports/phase59e/tv_vs_python_comparison_template.csv` | Fill TV columns |
| `TV_REVIEW/phase59_canonical_live.pine` | `phase59eForensic` table + markers |
