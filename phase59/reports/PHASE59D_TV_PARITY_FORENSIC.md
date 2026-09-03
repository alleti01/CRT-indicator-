# PHASE59D — Actual TradingView Parity Forensic

**Date:** 2026-08-31  
**Reference trade:** LW-063138  
**Python data:** Databento NQ.v.0 (continuous volume)  
**TradingView:** NQ1! (B-ADJ per user screenshot)

---

## Executive Summary

Python mirror parity (126/126) is **valid for Databento NQ.v.0** but **does not prove TradingView NQ1! parity**.

Forensic trace shows Python **correctly generates LW-063138** at 13:40 signal / 13:41 entry on Databento bars. Python has **no equivalent** to the spurious TV LONG observed at 14:31–14:33 New York (13:31–13:33 Chicago).

**Primary classification (pending TV OHLC confirmation):** `DATA_SERIES_MISMATCH` — NQ1! back-adjusted continuous vs Databento NQ.v.0.

**No strategy logic fix applied.** Diagnostic tooling added (Layer B only).

---

## 1. Raw OHLC — Databento vs Python

| Bar (Chicago) | Match |
|---|---|
| 13:36 – 13:45 (10 bars) | **ALL PASS** (exact tick) |

Python loader reproduces user-supplied Databento OHLC exactly.  
See: `phase59/reports/phase59d/ohlc_databento_vs_python.csv`

**TradingView NQ1! OHLC:** Not available in repo — **must be compared manually bar-by-bar on chart Data Window.** If any bar differs → stop; classify `DATA_FEED_DIVERGENCE` or `DATA_SERIES_MISMATCH`.

---

## 2. Continuous Contract Audit

| Aspect | Python (frozen) | TradingView (reported) |
|---|---|---|
| Symbol | NQ.v.0 | NQ1! |
| Vendor | Databento | CME continuous via TV |
| Roll | Volume continuous | Front-month + roll (B-ADJ shown) |
| Back-adjustment | Databento native | **B-ADJ enabled** (user screenshot) |
| Session | CME Globex ETH | NQ1! ETH (assumed) |
| Bar time | Bar open, UTC→Chicago | Chart TZ America/New_York |

**BACK-ADJUSTMENT EFFECT:** Historical OHLC on NQ1! B-ADJ will differ from unadjusted / Databento NQ.v.0 on past bars. Even small deltas change ATR(14), swings, reaction scores, and internal-trade stop timing.

**CONTINUOUS CONTRACT PARITY:** **FAIL** (different construction; not assumed equivalent)

---

## 3. ATR @ LW-063138 Entry (13:41 Chicago)

| Source | ATR |
|---|---|
| Python (Databento) | **6.678571428571429** |
| Pine on same bars (expected) | 6.678571428571429 |
| TradingView NQ1! | **UNKNOWN — measure TRC_ATR / Data Window @ 14:41 NY** |

**Delta:** Pending TV measurement. If TV ATR ≠ 6.6786 at entry bar → trace backward to first bar where SMA(14) range inputs diverge.

---

## 4. HTF Closed-Bar Alignment @ 13:40 Chicago

| TF | Python completed bar timestamp | OHLC (completed) |
|---|---|---|
| **5M** | 2026-08-26 **13:40:00** Chicago | O=29292 H=29298 L=29288 C=29295 |
| **15M** | 2026-08-26 **13:30:00** Chicago | O=29279.75 H=29303.5 L=29275.75 C=29295 |

Pine `request.security(..., lookahead_off)` should match when fed identical 1M history.  
**5M CLOSED-BAR PARITY:** PASS (Python reference) / **PENDING TV**  
**15M CLOSED-BAR PARITY:** PASS (Python reference) / **PENDING TV**

At 13:41 entry: same 5M=13:40, 15M=13:30 (15M bar rolls at 13:45).

---

## 5. Python Canonical Trace — 13:00–14:00 Chicago

Artifacts:
- `phase59/reports/phase59d/trace_1300_1400_chicago.csv` (60 bars)
- `phase59/reports/phase59d/trace_1335_1345_chicago.csv` (focus window)
- `phase59/tools/phase59d_trace.py`

### Canonical trades in window

| Trade | Signal | Entry | Dir | Entry px | Stop M1 | Target M1 |
|---|---|---|---|---|---|---|
| TRACE-063137 | 13:26 | 13:27 | SHORT | 29277.75 | 29285.09 | 29259.40 |
| **LW-063138** | **13:40** | **13:41** | **LONG** | **29293.25** | **29286.57** | **29309.95** |

---

## 6. LW-063138 Bar-by-Bar (Python ground truth)

| Time (Chi) | ctxDir | locL | reactL | totalArmL | Engine state | Decision | Canon |
|---|---|---|---|---|---|---|---|
| 13:35 | BULLISH | 1 | 0 | 3 | WATCH | WATCH | — |
| 13:36 | BULLISH | 0 | 1 | 2 | ARMED_LONG | ARMED | — |
| 13:37 | BULLISH | 1 | 0 | 3 | ARMED_LONG | ARMED | — |
| 13:38 | NEUTRAL | 1 | 1 | 3 | ARMED_LONG | WAIT | — |
| 13:39 | NEUTRAL | 1 | 0 | 3 | ARMED_LONG | ARMED | — |
| **13:40** | **BULLISH** | **1** | **1** | **3** | **IN_LONG** | **TAKE_LONG** | **SIGNAL** |
| **13:41** | BULLISH | 1 | 2 | 3 | IN_LONG | HOLD | **ENTRY** |
| 13:43 | BULLISH | 1 | 0 | 3 | COOLDOWN | EXIT_STOP | M1 stop (internal) |

Phase58D @ 13:40: evTotal=6, decision=**TAKE**, P4=**KEEP**, H1=**KEEP**

---

## 7. Earlier “Wrong” TV LONG (14:31–14:33 NY = 13:31–13:33 Chicago)

### Python @ 13:31–13:33

| Time | ctxDir | locL | reactL | totalArmL | Engine | Notes |
|---|---|---|---|---|---|---|
| 13:31 | BULLISH | 1 | **3** | 3 | **IN_SHORT** | reactL=3 but **blocked** by internal Phase58 SHORT |
| 13:32 | BULLISH | 0 | 2 | 2 | COOLDOWN | SHORT internal stop exit |
| 13:33 | BULLISH | 0 | 2 | 2 | WATCH | No LONG take |

**DOES PYTHON HAVE THIS SAME OPPORTUNITY?** **NO**

Python does **not** emit a LONG TAKE/ENTRY at 13:31–13:33. Features are bullish, but the engine is inside the **13:26 SHORT** internal trade until stop at 13:32.

### Downstream effect (hypothesis)

If TradingView Pine (on NQ1! data):
1. Does **not** take the 13:26 SHORT (different OHLC), **or**
2. Exits SHORT earlier/later due to different stop geometry, **or**
3. Arms/takes LONG at 13:31 when `reactL=3` and `totalArm≥4` while `p58InTrade=false`

→ a **spurious LONG** fires at ~13:31–13:33  
→ `p58InTrade=true` blocks signal generation at **13:40**  
→ **LW-063138 missing on TV**

TV geometry (stop ~29268, target ~29307) implies entry ~29279 with ~11pt risk — inconsistent with canonical M1 1.0 ATR geometry — suggests **different bar prices and/or wrong opportunity**, not a filter/threshold tweak.

---

## 8. First Causal Divergence (deterministic on Python; TV pending)

### Best current evidence

| Field | Value |
|---|---|
| **FIRST DIVERGENCE TIMESTAMP** | **2026-08-26 13:26:00 Chicago** (earliest branch point) or **13:30–13:31** (first bar where LONG arming becomes plausible) |
| **VARIABLE** | Internal trade state (`p58InTrade` / engine IN_SHORT) vs raw feature scores |
| **PYTHON @ 13:31** | `p58InTrade` equivalent: IN_SHORT; no LONG take despite reactL=3 |
| **PINE (TV observed)** | Spurious LONG ~13:31–13:33; no TAKE @ 13:40 |
| **UPSTREAM CAUSE** | Most likely **NQ1! B-ADJ OHLC ≠ Databento NQ.v.0** → different 13:26 SHORT lifecycle → different blocking at 13:31 |
| **DOWNSTREAM EFFECT** | Opportunity memory + `p58InTrade` prevents 13:40 canonical TAKE |

Alternative causes (lower priority until TV trace confirms OHLC match):
- HTF `request.security` semantic mismatch (if OHLC matches)
- Pine state-machine bug in internal-trade gate (if OHLC matches)

---

## 9. Pine Trace Instrumentation (Layer B)

Added to `TV_REVIEW/phase59_canonical_live.pine`:

| Input | Purpose |
|---|---|
| `debugTrace` | Data Window plots + cursor table |
| `traceStartMs` / `traceEndMs` | Default 13:00–14:00 Chicago |
| `lw063138Diag` | Per-bar labels 13:35–13:45 Chicago |

**Layer A unchanged.** Enable on NQ1! 1M Aug 26 and compare `TRC_*` plots to Python CSV.

Run: `python3 phase59/tools/phase59d_trace.py`

---

## 10. Final Report Block

```
PHASE59D — ACTUAL TRADINGVIEW PARITY FORENSIC
=============================================

RAW TV/DATABENTO OHLC PARITY:
PENDING (Python=Databento PASS; TV NQ1! not in repo — manual compare required)

CONTINUOUS CONTRACT PARITY:
FAIL (NQ.v.0 vs NQ1! B-ADJ)

BACK-ADJUSTMENT EFFECT:
Likely material — B-ADJ shifts historical OHLC → ATR, swings, stops, arming timing all drift

ATR PARITY AT LW-063138:
Python: 6.678571428571429
Pine:   6.678571428571429 (on Databento-equivalent bars)
Delta:  PENDING TV NQ1! measurement

5M CLOSED-BAR PARITY:
PASS (Python) / PENDING TV

15M CLOSED-BAR PARITY:
PASS (Python) / PENDING TV

EARLIER PINE LONG:
Take: ~13:31–13:33 Chicago (14:31–14:33 NY) per user observation
Entry: ~29279 (inferred from stop/target geometry)
Python equivalent: NO

FIRST CAUSAL DIVERGENCE:
2026-08-26 13:26–13:31 America/Chicago (internal-trade / data path)

VARIABLE:
p58InTrade / Phase58 internal SHORT lifecycle (or raw OHLC if TV differs earlier)

PYTHON VALUE:
IN_SHORT @ 13:31; no LONG take; LW-063138 @ 13:40/13:41

PINE VALUE (TV):
Spurious LONG ~13:31–13:33; no TAKE @ 13:40

ROOT CAUSE:
Unproven on TV OHLC alone; strongest hypothesis: DATA_SERIES_MISMATCH
(NQ1! B-ADJ ≠ Databento NQ.v.0) causing divergent internal trade → blocks canonical TAKE

CLASSIFICATION:
DATA_SERIES_MISMATCH (primary)
STATE_MACHINE (secondary — if OHLC matches at 13:26–13:33)

STRATEGY LOGIC CHANGED:
NO

PARAMETERS CHANGED:
NO

MINIMAL IMPLEMENTATION FIX MADE:
NO (diagnostics only)

LW-063138 ACTUAL TRADINGVIEW TAKE PARITY:
FAIL (per user observation)

LW-063138 ACTUAL TRADINGVIEW ENTRY PARITY:
FAIL

LW-063138 ENTRY PRICE PARITY:
FAIL

LW-063138 M1 GEOMETRY PARITY:
FAIL

OTHER FROZEN TV SPOT CHECKS:
0/5 (not run on TV)

PYTHON PARITY AFTER FIX:
PASS (unchanged — 126/126 mirror still valid on Databento)

ACTUAL TRADINGVIEW PARITY:
FAIL

SAFE TO CONTINUE:
NO — resolve data series or prove first bar divergence on TV before any logic change
```

---

## 11. Required Next Steps (User / TV)

1. On NQ1! 1M Aug 26, enable **`lw063138Diag=true`** and **`debugTrace=true`**
2. Compare Data Window OHLC @ 13:36–13:45 to Databento table in this report
3. If OHLC differs → **stop**; do not tune strategy; document roll/adj policy or switch TV symbol to match NQ.v.0
4. If OHLC matches → export `TRC_p58InTrade`, `TRC_p58State`, `TRC_reactL` @ 13:31 vs Python CSV; file STATE_MACHINE bug
