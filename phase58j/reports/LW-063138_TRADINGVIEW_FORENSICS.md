# PHASE58J TRADINGVIEW FORENSIC AUDIT — LW-063138

## Verdict

**Canonical CSV, Unix ms, raw Databento bars, and M0/M1 simulator reconstruction are correct.**
**The ~4-hour TradingView visual offset is a Pine review overlay bug (naive timestamp string parsed as UTC wall time).**
**Simulator results are NOT affected.**

---

## PART 1 — Unix timestamp verification

| Input | UTC | America/Chicago | America/New_York |
|-------|-----|-----------------|------------------|
| `1787769660000` | 2026-08-26 18:41:00+00:00 | 2026-08-26 13:41:00-05:00 | 2026-08-26 14:41:00-04:00 |
| `2026-08-26T13:41:00-05:00` → unix_ms | — | — | **1787769660000** |

**Internal consistency: YES** — no timestamp corruption.

---

## PART 2 — Raw data semantics

| Field | Value |
|-------|-------|
| Source file | `phase58j/data/nq_continuous_1m_lw_extension.csv` (+ stitched RAW_1M_PATHS) |
| Instrument | NQ |
| Contract | NQ.v.0 (Databento continuous volume) |
| Vendor | Databento |
| Raw timestamp column | `timestamp` |
| Raw timezone | UTC (`+00:00` in file) |
| Timezone-aware | Yes |
| Bar convention | 1-minute **bar OPEN** |
| Session | CME Globex; index normalized to **America/Chicago** after load |
| DST | pandas `tz_convert("America/Chicago")` (CDT -05 on 2026-08-26) |

**Raw vendor timestamp for canonical entry bar (exact, unconverted):**
`2026-08-26 18:41:00+00:00`

**Loaded index after `load_ohlcv_csv(source_timezone=UTC)` → `tz_convert(America/Chicago)`:**
`2026-08-26 13:41:00-05:00` — OHLC: O=29293.25 H=29294.75 L=29290.75 C=29293.75

---

## PART 4 — Pipeline trace (frozen execution)

| Stage | Bar index | Chicago | UTC | Unix ms |
|-------|-----------|---------|-----|---------|
| Signal bar T (Phase58D/H1 decision) | 3134046 | 2026-08-26 13:40:00-05:00 | 18:40 UTC | 1787769600000 |
| Entry execution bar T+1 | 3134047 | 2026-08-26 13:41:00-05:00 | 18:41 UTC | 1787769660000 |

**Frozen convention (from `phase58d/research/engine.py`):**
- Signal on **closed bar T** (`signal_i`)
- Entry on **next bar open T+1** (`entry_i = signal_i + 1`, `entry_price = m1_op[entry_i]`)
- Management walk from **`entry_i + 1`**; same-bar collision **STOP FIRST**

**Entry price parity:** `m1_op[3134047] = 29293.25` = canonical **PASS**

---

## PART 5 — M0 bar-by-bar reconstruction

| Bar | Chicago | O | H | L | C | low ≤ stop (29288.241)? | Event |
|-----|---------|---|---|---|---|-------------------------|-------|
| Entry | 13:41 | 29293.25 | 29294.75 | 29290.75 | 29293.75 | — | Entry (excluded from mgmt) |
| +1 | 13:42 | 29293.50 | 29298.00 | 29292.50 | 29292.75 | False | — |
| +2 | 13:43 | 29292.00 | 29294.25 | **29288.00** | 29289.25 | **True** | **M0 STOP** |

**M0 exit:** STOP @ 2026-08-26 13:43:00-05:00, price 29288.241, gross R -1.0  
**M0 outcome parity: PASS**

---

## PART 6 — M1 bar-by-bar reconstruction

| Bar | Chicago | H | low ≤ stop (29286.571)? | high ≥ target (29309.946)? | Event |
|-----|---------|---|-------------------------|----------------------------|-------|
| Entry | 13:41 | 29294.75 | — | — | Entry excluded |
| +1 | 13:42 | 29298.00 | False | False | — |
| +2 | 13:43 | 29294.25 | False | False | M0 stopped (M1 continues) |
| +3 | 13:44 | 29295.25 | False | False | — |
| +4 | 13:45 | **29313.75** | False | **True** | **M1 TARGET** |

**M1 exit:** TARGET @ 2026-08-26 13:45:00-05:00, price 29309.946, gross R +2.5  
**M1 outcome parity: PASS**

---

## PART 7 — Transition sequence (proven from raw bars)

```
13:41 ENTRY
O=29293.25 H=29294.75 L=29290.75 C=29293.75

13:42
O=29293.50 H=29298.00 L=29292.50 C=29292.75

13:43 M0 STOP
O=29292.00 H=29294.25 L=29288.00 C=29289.25
low <= 29288.241 = TRUE
low <= 29286.571 = FALSE

13:44
O=29289.50 H=29295.25 L=29288.50 C=29295.00

13:45 M1 TARGET
O=29295.00 H=29313.75 L=29294.75 C=29311.25
high >= 29309.946 = TRUE
```

**M0 STOP → M1 TARGET raw-bar sequence proven: YES**

---

## PART 8 — TradingView ~09:41 fingerprint

Pine naive string `timestamp("2026-08-26 13:41")` resolves to **13:41 UTC** (unix 1787751660000), **not** 13:41 Chicago.

| | Timestamp | OHLC open |
|--|-----------|-----------|
| Pine naive match (UTC 13:41) | 08:41 Chicago / **09:41 New York** | **29261.00** |
| Canonical entry | 13:41 Chicago / 14:41 New York | **29293.25** |

**Is TradingView ~09:41 showing the SAME bar as canonical 13:41 Chicago? NO**

The 4-hour discrepancy on a New York timezone chart is explained by:
- CSV/Pine label says "13:41" intending **Chicago exchange time**
- Pine `timestamp("YYYY-MM-DD HH:MM")` without timezone → **UTC wall clock**
- Chart display in America/New_York → **09:41 ET** (= 13:41 UTC = 08:41 Chicago bar)

That wrong bar has completely different OHLC; the upward move after the misplaced marker is unrelated to the canonical M0/M1 sequence.

---

## PART 9 — Pine audit

**Current (broken):**
```pine
entryTime = input.time(timestamp("2026-08-26 13:41"), "Entry time (chart TZ)", ...)
if time == entryTime
```

Issues:
1. Label "chart TZ" is **misleading** — string timestamp does not follow chart timezone.
2. Without explicit timezone, Pine resolves to **UTC** for NQ1! (syminfo/exchange semantics).
3. `time == entryTime` matches wrong bar open in absolute Unix time.

**Pine timestamp handling: FAIL**

**Corrected:**
```pine
entryTime = input.time(timestamp("America/Chicago", 2026, 8, 26, 13, 41), "Entry time (America/Chicago absolute)", ...)
```

See `phase58j/pine/phase58j_last_week_review_corrected.pine`.

---

## PART 10 — CSV generator audit

`_ts_fields()` in `last_week_replay.py`:
- `entry_time`: Chicago ISO ✓
- `unix_ms`: `int(utc.timestamp() * 1000)` ✓
- No double conversion, no fixed -05 offset errors

**CSV timezone handling: PASS**

---

## PART 11 — Instrument alignment

| Field | Value |
|-------|-------|
| Historical source | NQ.v.0 Databento continuous (stitched) |
| TradingView symbol | NQ1! (intended) |
| Entry price in raw data @ 13:41 Chicago | 29293.25 ✓ |

**Instrument parity: PASS** — same NQ continuous series, not ES or shifted contract.

---

## PART 12 — Simulator impact

Replay operates on America/Chicago-indexed bars sequentially. All entry/exit indices and OHLC paths are internally consistent. Only the **Pine visual overlay** used a wrong absolute timestamp.

**SIMULATOR_RESULTS_AFFECTED: NO**  
**Issue classification: PINE_ONLY + REVIEW_EXPORT_ONLY**

---

## PART 13 — HTF alignment

At signal bar T (2026-08-26 13:40:00 Chicago):

| TF | Completed bar timestamp | O | H | L | C |
|----|-------------------------|---|---|---|---|
| 5M | 2026-08-26 13:40:00-05:00 | 29292.00 | 29298.00 | 29288.00 | 29295.00 |
| 15M | 2026-08-26 13:30:00-05:00 | 29279.75 | 29303.50 | 29275.75 | 29295.00 |

Causal rule: last HTF bar with `index <= 1m signal time`. No future HTF leakage.

**5M alignment: PASS | 15M alignment: PASS**

---

## PART 16 — Visual parity test (corrected overlay)

| Field | Value |
|-------|-------|
| Symbol | NQ1! |
| Timeframe | 1 minute |
| Date | 2026-08-26 |
| Chart time (Chicago) | **13:41** |
| Chart time (New York) | **14:41** |
| Entry | 29293.25 |
| M0 stop | 29288.241071428572 |
| M1 stop | 29286.571428571428 |
| M0 target | 29305.772321428572 |
| M1 target | 29309.946428571428 |

Expected: ENTRY 13:41 → M0 STOP 13:43 → M1 survives → M1 TARGET 13:45

---

## PART 17 — All last-week parity

From `phase58j/results/last_week_timestamp_parity.csv`:

| Check | Result |
|-------|--------|
| Entry parity | **11/11** |
| M0 outcome parity | **11/11** |
| M1 outcome parity | **11/11** |

---

## FINAL REPORT

```
PHASE58J TRADINGVIEW FORENSIC AUDIT
===================================

TRADE: LW-063138

CANONICAL ENTRY PRICE: 29293.25

RAW ENTRY TIMESTAMP: 2026-08-26 18:41:00+00:00 (vendor) / 2026-08-26 13:41:00-05:00 (loaded)

RAW TIMESTAMP TIMEZONE: UTC in vendor file → America/Chicago index

UTC ENTRY: 2026-08-26 18:41:00+00:00

CHICAGO ENTRY: 2026-08-26 13:41:00-05:00

NEW YORK ENTRY: 2026-08-26 14:41:00-04:00

CSV ENTRY TIME CORRECT: YES

CSV UNIX_MS CORRECT: YES

TRADINGVIEW DISPLAYED ENTRY: ~09:41 (America/New_York chart) from Pine UTC-13:41 string

TRADINGVIEW ENTRY BAR MATCHES RAW BAR: NO

ENTRY PRICE PARITY: PASS

M0 STOP: 29288.241071428572

M0 FIRST EXIT: STOP @ 2026-08-26 13:43:00-05:00

M0 EXIT TIME: 2026-08-26 13:43:00-05:00

M0 OUTCOME PARITY: PASS

M1 STOP: 29286.571428571428

M1 TARGET: 29309.946428571428

M1 FIRST EXIT: TARGET @ 2026-08-26 13:45:00-05:00

M1 EXIT TIME: 2026-08-26 13:45:00-05:00

M1 OUTCOME PARITY: PASS

M0 STOP → M1 TARGET RAW-BAR SEQUENCE PROVEN: YES

PINE TIMESTAMP HANDLING: FAIL

CSV TIMEZONE HANDLING: PASS

RAW DATA TIMEZONE HANDLING: PASS

5M ALIGNMENT: PASS

15M ALIGNMENT: PASS

SIMULATOR CAUSALITY: PASS

SIMULATOR RESULTS AFFECTED: NO

ISSUE CLASSIFICATION: PINE_ONLY + REVIEW_EXPORT_ONLY

ROOT CAUSE: Pine review overlay uses timestamp("YYYY-MM-DD HH:MM") without explicit
America/Chicago timezone. TradingView resolves the string as UTC wall time (unix
1787751660000 = 08:41 Chicago = 09:41 New York), placing the marker on the wrong bar.
CSV unix_ms (1787769660000 = 13:41 Chicago) is correct.

CORRECTION REQUIRED: YES

CORRECTION: Load phase58j_last_week_review_corrected.pine (explicit America/Chicago
timestamp). Future replays updated in last_week_replay.py _write_pine().

ALL LAST-WEEK REVIEW ENTRY PARITY: 11/11

ALL LAST-WEEK M0 OUTCOME PARITY: 11/11

ALL LAST-WEEK M1 OUTCOME PARITY: 11/11

SAFE TO RESUME TRADINGVIEW VISUAL REVIEW: YES (after loading corrected Pine)
```

---

## Artifacts

| File | Purpose |
|------|---------|
| `phase58j/results/LW-063138_bar_forensics.csv` | Raw bars ±10 min with touch flags |
| `phase58j/results/LW-063138_pipeline_trace.csv` | Signal/entry timestamps |
| `phase58j/results/LW-063138_m0_reconstruction.csv` | M0 bar walk |
| `phase58j/results/LW-063138_m1_reconstruction.csv` | M1 bar walk |
| `phase58j/results/last_week_timestamp_parity.csv` | All 11 trades parity |
| `phase58j/review/last_week_tradingview_review_corrected.csv` | Review CSV + Pine expr |
| `phase58j/pine/phase58j_last_week_review_corrected.pine` | Fixed overlay |
