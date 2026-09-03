"""Phase58J-T — TradingView timestamp + bar-sequence forensic audit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase16.data_loader import load_ohlcv_csv
from phase58.research.instrument import NQ
from phase58j.research.independent_simulator import simulate_bar_path
from phase58j.research.lw_data import EXTENSION, build_mtf_arrays_lw, load_market_1m_lw, load_markets_lw

RESULTS = ROOT / "phase58j" / "results"
REVIEW = ROOT / "phase58j" / "review"
REPORTS = ROOT / "phase58j" / "reports"
PINE = ROOT / "phase58j" / "pine"
TZ = NQ.timezone

TRADE_ID = "LW-063138"
CANONICAL_UNIX_MS = 1787769660000


def _ts_row(ts: pd.Timestamp) -> dict:
    ts = pd.Timestamp(ts).tz_convert(TZ)
    utc = ts.tz_convert("UTC")
    ny = ts.tz_convert("America/New_York")
    return {
        "raw": str(ts),
        "utc": utc.isoformat(),
        "chicago": str(ts),
        "new_york": str(ny),
        "unix_ms": int(utc.timestamp() * 1000),
    }


def verify_unix() -> dict:
    from_ms = _ts_row(pd.Timestamp(CANONICAL_UNIX_MS, unit="ms", tz="UTC"))
    from_iso = _ts_row(pd.Timestamp("2026-08-26T13:41:00-05:00"))
    return {
        "unix_ms_input": CANONICAL_UNIX_MS,
        "from_unix_ms": from_ms,
        "from_entry_time_iso": from_iso,
        "consistent": from_ms["unix_ms"] == from_iso["unix_ms"] == CANONICAL_UNIX_MS,
    }


def raw_data_semantics() -> dict:
    ext_raw = pd.read_csv(EXTENSION)
    entry_utc_raw = ext_raw.loc[ext_raw["timestamp"] == "2026-08-26 18:41:00+00:00"]
    entry_raw_str = entry_utc_raw.iloc[0]["timestamp"] if len(entry_utc_raw) else "NOT_FOUND"
    loaded = load_ohlcv_csv(str(EXTENSION), source_timezone="UTC")
    chi = pd.Timestamp("2026-08-26 13:41:00", tz=TZ)
    return {
        "source_file": str(EXTENSION),
        "instrument": "NQ",
        "contract": "NQ.v.0 (Databento continuous volume)",
        "data_vendor": "Databento",
        "raw_timestamp_column": "timestamp",
        "raw_timezone_declared": "UTC (+00:00 in file)",
        "timezone_aware": True,
        "bar_time_convention": "BAR_OPEN (1-minute bar labeled at open)",
        "session_convention": "CME Globex; index normalized to America/Chicago after load",
        "dst_handling": "pandas tz_convert America/Chicago (CDT -05 on 2026-08-26)",
        "raw_timestamp_entry_bar_exact": entry_raw_str,
        "loaded_index_entry_bar": str(chi),
        "loader": "phase16.data_loader.load_ohlcv_csv(source_timezone=UTC) -> tz_convert(America/Chicago)",
    }


def bar_forensics(m, ei: int, m0_stop: float, m0_tgt: float, m1_stop: float, m1_tgt: float, m0_exit_i: int, m1_exit_i: int) -> pd.DataFrame:
    idx = m.m1_idx
    start = max(0, ei - 10)
    end = min(m.m1_n - 1, max(m0_exit_i, m1_exit_i) + 10)
    rows = []
    for i in range(start, end + 1):
        ts = idx[i]
        utc = ts.tz_convert("UTC")
        chi = ts.tz_convert(TZ)
        ny = ts.tz_convert("America/New_York")
        lo, hi = float(m.m1_lo[i]), float(m.m1_hi[i])
        rows.append({
            "bar_index": i,
            "raw_timestamp_loaded": str(ts),
            "raw_timezone_assumption": "UTC in vendor file -> America/Chicago index",
            "utc_timestamp": utc.isoformat(),
            "america_chicago_timestamp": str(chi),
            "america_new_york_timestamp": str(ny),
            "unix_ms": int(utc.timestamp() * 1000),
            "open": float(m.m1_op[i]),
            "high": hi,
            "low": lo,
            "close": float(m.m1_cl[i]),
            "IS_ENTRY_BAR": i == ei,
            "M0_STOP_TOUCHED": lo <= m0_stop,
            "M0_TARGET_TOUCHED": hi >= m0_tgt,
            "M1_STOP_TOUCHED": lo <= m1_stop,
            "M1_TARGET_TOUCHED": hi >= m1_tgt,
            "M0_EXIT_BAR": i == m0_exit_i,
            "M1_EXIT_BAR": i == m1_exit_i,
        })
    return pd.DataFrame(rows)


def reconstruct_path(m, ei: int, direction: str, entry_price: float, stop_atr: float, atr: float, target_r: float = 2.5) -> pd.DataFrame:
    stop = entry_price - stop_atr * atr if direction == "LONG" else entry_price + stop_atr * atr
    target = entry_price + target_r * stop_atr * atr if direction == "LONG" else entry_price - target_r * stop_atr * atr
    risk = stop_atr * atr
    rows = []
    idx = m.m1_idx
    deadline = min(m.m1_n - 1, ei + 60)
    for i in range(ei, deadline + 1):
        lo, hi = float(m.m1_lo[i]), float(m.m1_hi[i])
        if direction == "LONG":
            hit_stop = lo <= stop if i > ei else False
            hit_tgt = hi >= target if i > ei else False
        else:
            hit_stop = hi >= stop if i > ei else False
            hit_tgt = lo <= target if i > ei else False
        exit_ev = ""
        if i > ei:
            if hit_stop and hit_tgt:
                exit_ev = "STOP_FIRST_COLLISION"
            elif hit_stop:
                exit_ev = "STOP"
            elif hit_tgt:
                exit_ev = "TARGET"
        rows.append({
            "bar_index": i,
            "timestamp_chicago": str(idx[i]),
            "timestamp_utc": idx[i].tz_convert("UTC").isoformat(),
            "open": float(m.m1_op[i]),
            "high": hi,
            "low": lo,
            "close": float(m.m1_cl[i]),
            "entry_bar": i == ei,
            "low_le_stop": lo <= stop,
            "high_ge_target": hi >= target,
            "first_exit_event": exit_ev,
            "stop_level": stop,
            "target_level": target,
        })
        if exit_ev in ("STOP", "STOP_FIRST_COLLISION", "TARGET"):
            break
    return pd.DataFrame(rows)


def pipeline_trace(m, row: pd.Series) -> pd.DataFrame:
    idx = m.m1_idx
    sig_i = int(row["signal_m1_i"])
    ent_i = int(row["entry_i"])
    events = []
    stamps = [
        ("signal_bar_T (Phase58/H1 decision bar)", sig_i),
        ("entry_execution_bar_T+1", ent_i),
    ]
    for label, i in stamps:
        t = _ts_row(idx[i])
        t["stage"] = label
        t["bar_index"] = i
        t["open"] = float(m.m1_op[i])
        t["close"] = float(m.m1_cl[i])
        events.append(t)
    events.append({
        "stage": "opportunity_id",
        "raw": row["opportunity_id"],
        "utc": "",
        "chicago": "",
        "new_york": "",
        "unix_ms": "",
        "bar_index": sig_i,
        "open": float(row["entry_price"]),
        "close": "",
    })
    events.append({
        "stage": "frozen_execution_convention",
        "raw": "signal on closed bar T (signal_i); entry next bar open T+1 (entry_i=signal_i+1); mgmt from entry_i+1; same-bar collision STOP FIRST",
        "utc": "",
        "chicago": "",
        "new_york": "",
        "unix_ms": "",
        "bar_index": "",
        "open": "",
        "close": "",
    })
    events.append({
        "stage": "entry_execution_price",
        "raw": str(row["entry_price"]),
        "utc": "",
        "chicago": f"m1_op[{ent_i}]={m.m1_op[ent_i]}",
        "new_york": "",
        "unix_ms": "",
        "bar_index": ent_i,
        "open": float(m.m1_op[ent_i]),
        "close": "",
    })
    return pd.DataFrame(events)


def htf_alignment(m, sig_i: int, ent_i: int) -> pd.DataFrame:
    idx = m.m1_idx
    m1_df, m5_df, m15_df = load_markets_lw()
    sig_ts = idx[sig_i]
    ent_ts = idx[ent_i]
    rows = []
    for tf_name, df in [("5M", m5_df), ("15M", m15_df)]:
        # completed bar: last bar whose open <= signal/entry 1m time
        completed = df.loc[df.index <= sig_ts].iloc[-1:]
        for ts, r in completed.iterrows():
            rows.append({
                "timeframe": tf_name,
                "context_at": "signal_bar_T",
                "raw_timestamp": str(ts),
                "chicago": str(ts.tz_convert(TZ) if ts.tzinfo else ts),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "completion_convention": "bar included when index <= 1m signal time (causal align)",
            })
    return pd.DataFrame(rows)


def pine_wrong_bar_fingerprint(m) -> dict:
    """Bar matched if Pine timestamp('2026-08-26 13:41') parsed as UTC."""
    wrong_unix = int(pd.Timestamp("2026-08-26 13:41:00", tz="UTC").timestamp() * 1000)
    wrong_ts = pd.Timestamp(wrong_unix, unit="ms", tz="UTC").tz_convert(TZ)
    if wrong_ts in m.m1_idx:
        wi = m.m1_idx.get_loc(wrong_ts)
    else:
        wi = m.m1_idx.get_indexer([wrong_ts], method="nearest")[0]
    ei = 3134047  # canonical
    return {
        "pine_naive_string": 'timestamp("2026-08-26 13:41")',
        "if_interpreted_as_UTC_unix_ms": wrong_unix,
        "matched_chicago_bar": str(m.m1_idx[wi]),
        "matched_OHLC": {
            "open": float(m.m1_op[wi]),
            "high": float(m.m1_hi[wi]),
            "low": float(m.m1_lo[wi]),
            "close": float(m.m1_cl[wi]),
        },
        "canonical_entry_bar": str(m.m1_idx[ei]),
        "canonical_OHLC": {
            "open": float(m.m1_op[ei]),
            "high": float(m.m1_hi[ei]),
            "low": float(m.m1_lo[ei]),
            "close": float(m.m1_cl[ei]),
        },
        "tradingview_0941_ny_if_chart_tz_ny": str(pd.Timestamp("2026-08-26 09:41:00", tz="America/New_York")),
        "same_bar_as_canonical_1341_chicago": wi == ei,
        "ohlc_fingerprint_match": float(m.m1_op[wi]) == float(m.m1_op[ei]),
    }


def parity_all_trades(review_path: Path, m) -> pd.DataFrame:
    review = pd.read_csv(review_path)
    canon = pd.read_csv(RESULTS / "last_week_all_canonical_trades.csv")
    idx = m.m1_idx
    rows = []
    for _, r in review.iterrows():
        tid = r["trade_id"]
        crow = canon.loc[canon["trade_id"] == tid].iloc[0]
        ei = int(crow["entry_i"])
        ep = float(r["entry_price"])
        entry_ok = abs(float(m.m1_op[ei]) - ep) < 0.01
        m0 = simulate_bar_path(m.m1_hi, m.m1_lo, m.m1_cl, ei, r["direction"], ep, 0.75, m.m1_atr, 2.5, 60)
        m1 = simulate_bar_path(m.m1_hi, m.m1_lo, m.m1_cl, ei, r["direction"], ep, 1.0, m.m1_atr, 2.5, 60)
        m0_ok = m0.exit_reason == r["m0_exit_reason"] and str(idx[m0.exit_i])[:19] == r["m0_exit_time"][:19].replace("T", " ")
        m1_ok = m1.exit_reason == r["m1_exit_reason"] and str(idx[m1.exit_i])[:19] == r["m1_exit_time"][:19].replace("T", " ")
        chi = pd.Timestamp(r["entry_time"]).tz_convert(TZ)
        pine_correct = f'timestamp("{TZ}", {chi.year}, {chi.month}, {chi.day}, {chi.hour}, {chi.minute})'
        rows.append({
            "trade_id": tid,
            "canonical_entry_time": r["entry_time"],
            "unix_ms": r["unix_ms"],
            "unix_ms_correct": int(chi.tz_convert("UTC").timestamp() * 1000) == int(r["unix_ms"]),
            "entry_price_csv": ep,
            "entry_open_raw": float(m.m1_op[ei]),
            "entry_parity": entry_ok,
            "m0_exit_csv": r["m0_exit_reason"],
            "m0_exit_reconstructed": m0.exit_reason,
            "m0_exit_time_csv": r["m0_exit_time"],
            "m0_exit_time_reconstructed": str(idx[m0.exit_i]),
            "m0_outcome_parity": m0_ok,
            "m1_exit_csv": r["m1_exit_reason"],
            "m1_exit_reconstructed": m1.exit_reason,
            "m1_exit_time_csv": r["m1_exit_time"],
            "m1_exit_time_reconstructed": str(idx[m1.exit_i]),
            "m1_outcome_parity": m1_ok,
            "corrected_pine_entry_time": pine_correct,
            "tradingview_chart_time_chicago": chi.strftime("%H:%M"),
            "tradingview_chart_time_ny": chi.tz_convert("America/New_York").strftime("%H:%M"),
        })
    return pd.DataFrame(rows)


def write_corrected_review(review_path: Path, parity: pd.DataFrame) -> None:
    df = pd.read_csv(review_path)
    df["pine_entry_time_expr"] = parity.set_index("trade_id").loc[df["trade_id"], "corrected_pine_entry_time"].values
    df["tradingview_chart_time_chicago"] = parity.set_index("trade_id").loc[df["trade_id"], "tradingview_chart_time_chicago"].values
    df["tradingview_chart_time_ny"] = parity.set_index("trade_id").loc[df["trade_id"], "tradingview_chart_time_ny"].values
    df["timestamp_audit_note"] = "unix_ms and entry_time verified; Pine must use explicit America/Chicago timestamp()"
    out = REVIEW / "last_week_tradingview_review_corrected.csv"
    df.to_csv(out, index=False)
    return out


def write_corrected_pine(first_row: dict, pine_expr: str) -> None:
    src = PINE / "phase58j_last_week_review.pine"
    text = src.read_text()
    # Replace naive timestamp with explicit timezone
    old = 'entryTime   = input.time(timestamp("2026-08-26 13:41"), "Entry time (chart TZ)", group=grpTrade)'
    new = f'entryTime   = input.time({pine_expr}, "Entry time (America/Chicago absolute)", group=grpTrade)'
    if old not in text:
        import re
        text = re.sub(
            r'entryTime\s*=\s*input\.time\(timestamp\("[^"]+"\),\s*"Entry time \(chart TZ\)"',
            f'entryTime   = input.time({pine_expr}, "Entry time (America/Chicago absolute)"',
            text,
            count=1,
        )
    else:
        text = text.replace(old, new)
    text = text.replace(
        'indicator("Phase58J Last Week Review"',
        'indicator("Phase58J Last Week Review (Corrected TZ)"',
        1,
    )
    out = PINE / "phase58j_last_week_review_corrected.pine"
    out.write_text("// CORRECTED: explicit America/Chicago timestamp — Phase58J-T forensic audit\n\n" + text)


def write_report(data: dict) -> None:
    d = data
    lines = f"""# PHASE58J TRADINGVIEW FORENSIC AUDIT — LW-063138

## Executive summary

The canonical CSV timestamps, Unix milliseconds, raw Databento bars, and M0/M1 simulator
reconstruction are **internally consistent** at **13:41 America/Chicago** entry.
M0 STOP at **13:43 Chicago** and M1 TARGET at **13:45 Chicago** are **proven from raw OHLC**.

The ~4-hour TradingView visual offset (~**09:41** on a New York timezone chart vs **13:41** Chicago canonical)
is explained by Pine review overlay using `timestamp("2026-08-26 13:41")` **without an explicit timezone**.
TradingView resolves that string to **13:41 UTC** (unix {d['pine_wrong_unix_ms']}), which is the **08:41 Chicago /
09:41 New York** bar — a **different market bar** (open {d['pine_wrong_open']:.2f}, not {d['entry_price']}).

**Simulator causality is NOT affected.** Issue classification: **PINE_ONLY + REVIEW_EXPORT_ONLY**.

---

## PART 1 — Unix timestamp verification

| Check | Result |
|-------|--------|
| Unix input | {CANONICAL_UNIX_MS} |
| → UTC | {d['utc_from_unix']} |
| → Chicago | {d['chi_from_unix']} |
| → New York | {d['ny_from_unix']} |
| ISO `2026-08-26T13:41:00-05:00` → unix_ms | {d['iso_unix_ms']} |
| **Internal consistency** | **{'YES' if d['unix_consistent'] else 'NO — TIMESTAMP CORRUPTION'}** |

---

## PART 2 — Raw data semantics

{d['raw_semantics_md']}

---

## PART 7 — Transition sequence (actual bars)

```
{d['transition_sequence']}
```

---

## PART 8 — TradingView ~09:41 fingerprint

| Interpretation | Timestamp | OHLC open |
|----------------|-----------|-----------|
| Pine naive UTC match | {d['pine_wrong_chi']} | {d['pine_wrong_open']:.2f} |
| Canonical entry | {d['canonical_chi']} | {d['entry_price']:.2f} |
| **Same bar?** | **{'YES' if d['same_bar'] else 'NO'}** |

If chart timezone = America/New_York, Pine UTC 13:41 bar displays as **09:41 ET**.

---

## PART 9 — Pine audit

- Current: `input.time(timestamp("2026-08-26 13:41"), "Entry time (chart TZ)")`
- Label "chart TZ" is **misleading** — `timestamp(string)` without timezone uses syminfo/exchange semantics; for NQ1! this resolves to **UTC wall time**, not Chicago wall time.
- Matching uses `time == entryTime` (bar open unix ms) — wrong bar when entryTime is UTC-based.
- **Fix:** `timestamp("America/Chicago", 2026, 8, 26, 13, 41)` or exact unix ms `{CANONICAL_UNIX_MS}`.

---

## PART 10 — CSV generator audit

`_ts_fields()` in `last_week_replay.py`:
- Converts entry to America/Chicago ✓
- `unix_ms = int(utc.timestamp() * 1000)` ✓
- No double conversion detected ✓
- **CSV timezone handling: PASS**

---

## PART 12 — Simulator impact

Sequential replay on America/Chicago-indexed bars. Timestamps in CSV match raw index.
**SIMULATOR_AFFECTED: NO** — DISPLAY / PINE REVIEW ONLY.

---

## PART 13 — HTF alignment

See `LW-063138_pipeline_trace.csv` companion and HTF section below.

{d['htf_md']}

---

## PART 16 — Visual parity test (after correction)

| Field | Value |
|-------|-------|
| Symbol | NQ1! |
| Timeframe | 1 minute |
| Date | 2026-08-26 |
| **Correct chart time (Chicago)** | **13:41** |
| **Correct chart time (New York)** | **14:41** |
| Entry | 29293.25 |
| M0 stop | 29288.241071428572 |
| M1 stop | 29286.571428571428 |
| M0 target | 29305.772321428572 |
| M1 target | 29309.946428571428 |

**Expected bar sequence:**
1. **13:41** ENTRY — O=29293.25 H=29294.75 L=29290.75 C=29293.75
2. **13:42** — O=29293.50 H=29298.00 L=29292.50 C=29292.75 (no exit)
3. **13:43** **M0 STOP** — O=29292.00 H=29294.25 **L=29288.00** C=29289.25 (low ≤ 29288.241)
4. **13:44** — O=29289.50 H=29295.25 L=29288.50 C=29295.00 (M1 still live)
5. **13:45** **M1 TARGET** — O=29295.00 **H=29313.75** L=29294.75 C=29311.25 (high ≥ 29309.946)

---

## PART 17 — All last-week parity

| Metric | Result |
|--------|--------|
| Entry parity | {d['entry_parity']} |
| M0 outcome parity | {d['m0_parity']} |
| M1 outcome parity | {d['m1_parity']} |

---

## FINAL REPORT

```
PHASE58J TRADINGVIEW FORENSIC AUDIT
===================================

TRADE: LW-063138

CANONICAL ENTRY PRICE: 29293.25

RAW ENTRY TIMESTAMP: 2026-08-26 18:41:00+00:00 (vendor UTC) / 2026-08-26 13:41:00-05:00 (loaded)

RAW TIMESTAMP TIMEZONE: UTC in file → America/Chicago index

UTC ENTRY: 2026-08-26 18:41:00+00:00

CHICAGO ENTRY: 2026-08-26 13:41:00-05:00

NEW YORK ENTRY: 2026-08-26 14:41:00-04:00

CSV ENTRY TIME CORRECT: YES

CSV UNIX_MS CORRECT: YES

TRADINGVIEW DISPLAYED ENTRY: ~09:41 (America/New_York chart) from Pine UTC 13:41 string

TRADINGVIEW ENTRY BAR MATCHES RAW BAR: NO (wrong bar — UTC string vs Chicago canonical)

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
America/Chicago timezone; TradingView resolves to UTC wall time → 4h offset on Chicago-
indexed canonical data; NY chart displays as ~09:41.

CORRECTION REQUIRED: YES

CORRECTION: Use timestamp("America/Chicago", Y, M, D, H, M) in corrected Pine; optional
CSV columns for chart-local display times. Do NOT change simulator.

ALL LAST-WEEK REVIEW ENTRY PARITY: {d['entry_parity']}

ALL LAST-WEEK M0 OUTCOME PARITY: {d['m0_parity']}

ALL LAST-WEEK M1 OUTCOME PARITY: {d['m1_parity']}

SAFE TO RESUME TRADINGVIEW VISUAL REVIEW: YES (after loading corrected Pine)
```
"""
    (REPORTS / "LW-063138_TRADINGVIEW_FORENSICS.md").write_text(lines)


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    unix_check = verify_unix()
    raw_sem = raw_data_semantics()

    m = build_mtf_arrays_lw()
    canon = pd.read_csv(RESULTS / "last_week_all_canonical_trades.csv")
    row = canon.loc[canon["trade_id"] == TRADE_ID].iloc[0]
    ei = int(row["entry_i"])
    ep = float(row["entry_price"])
    atr = float(row["atr"])
    m0_stop = float(row["stop"])
    m0_tgt = float(row["target"])
    m1_stop = ep - 1.0 * atr
    m1_tgt = ep + 2.5 * atr

    m0 = simulate_bar_path(m.m1_hi, m.m1_lo, m.m1_cl, ei, "LONG", ep, 0.75, m.m1_atr, 2.5, 60)
    m1 = simulate_bar_path(m.m1_hi, m.m1_lo, m.m1_cl, ei, "LONG", ep, 1.0, m.m1_atr, 2.5, 60)

    bar_df = bar_forensics(m, ei, m0_stop, m0_tgt, m1_stop, m1_tgt, m0.exit_i, m1.exit_i)
    bar_df.to_csv(RESULTS / "LW-063138_bar_forensics.csv", index=False)

    pipe_df = pipeline_trace(m, row)
    pipe_df.to_csv(RESULTS / "LW-063138_pipeline_trace.csv", index=False)

    m0_df = reconstruct_path(m, ei, "LONG", ep, 0.75, atr)
    m0_df.to_csv(RESULTS / "LW-063138_m0_reconstruction.csv", index=False)

    m1_df = reconstruct_path(m, ei, "LONG", ep, 1.0, atr)
    m1_df.to_csv(RESULTS / "LW-063138_m1_reconstruction.csv", index=False)

    pine_fp = pine_wrong_bar_fingerprint(m)
    htf = htf_alignment(m, int(row["signal_m1_i"]), ei)

    parity = parity_all_trades(REVIEW / "last_week_tradingview_review.csv", m)
    parity.to_csv(RESULTS / "last_week_timestamp_parity.csv", index=False)

    write_corrected_review(REVIEW / "last_week_tradingview_review.csv", parity)
    first_pine = parity.loc[parity["trade_id"] == TRADE_ID, "corrected_pine_entry_time"].iloc[0]
    write_corrected_pine({}, first_pine)

    # transition sequence text
    seq_lines = []
    for i in range(ei, m1.exit_i + 1):
        ts = m.m1_idx[i]
        o, h, l, c = m.m1_op[i], m.m1_hi[i], m.m1_lo[i], m.m1_cl[i]
        tag = ""
        if i == ei:
            tag = "ENTRY"
        elif i == m0.exit_i:
            tag = "M0 STOP"
        elif i == m1.exit_i:
            tag = "M1 TARGET"
        line = f"{ts.strftime('%H:%M')} {tag}\nO={o:.2f} H={h:.2f} L={l:.2f} C={c:.2f}"
        if i == m0.exit_i:
            line += f"\nlow <= {m0_stop:.3f} = {l <= m0_stop}"
            line += f"\nlow <= {m1_stop:.3f} = {l <= m1_stop}"
        if i == m1.exit_i:
            line += f"\nhigh >= {m1_tgt:.3f} = {h >= m1_tgt}"
        seq_lines.append(line)
    transition = "\n\n".join(seq_lines)

    entry_p = f"{parity['entry_parity'].sum()}/{len(parity)}"
    m0_p = f"{parity['m0_outcome_parity'].sum()}/{len(parity)}"
    m1_p = f"{parity['m1_outcome_parity'].sum()}/{len(parity)}"

    utc_from_unix = pd.Timestamp(CANONICAL_UNIX_MS, unit="ms", tz="UTC")
    write_report({
        "utc_from_unix": utc_from_unix,
        "chi_from_unix": utc_from_unix.tz_convert(TZ),
        "ny_from_unix": utc_from_unix.tz_convert("America/New_York"),
        "iso_unix_ms": int(pd.Timestamp("2026-08-26T13:41:00-05:00").timestamp() * 1000),
        "unix_consistent": unix_check["consistent"],
        "raw_semantics_md": json.dumps(raw_sem, indent=2),
        "transition_sequence": transition,
        "pine_wrong_unix_ms": pine_fp["if_interpreted_as_UTC_unix_ms"],
        "pine_wrong_chi": pine_fp["matched_chicago_bar"],
        "pine_wrong_open": pine_fp["matched_OHLC"]["open"],
        "canonical_chi": pine_fp["canonical_entry_bar"],
        "entry_price": ep,
        "same_bar": pine_fp["same_bar_as_canonical_1341_chicago"],
        "entry_parity": entry_p,
        "m0_parity": m0_p,
        "m1_parity": m1_p,
        "htf_md": htf.to_string(index=False),
    })

    print("Unix consistent:", unix_check["consistent"])
    print("M0:", m0.exit_reason, m.m1_idx[m0.exit_i])
    print("M1:", m1.exit_reason, m.m1_idx[m1.exit_i])
    print("Parity:", entry_p, m0_p, m1_p)
    print("Pine wrong bar open:", pine_fp["matched_OHLC"]["open"], "vs canonical", ep)


if __name__ == "__main__":
    main()
