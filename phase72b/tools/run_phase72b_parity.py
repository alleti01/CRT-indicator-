#!/usr/bin/env python3
"""Phase72B — autonomous Pine ↔ Python parity runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58j.research.lw_data import load_markets_lw
from phase72b.python.autonomous_mirror_engine import run_mirror
from phase72b.python.config import DEFAULT_CFG
from phase72b.python.event_log import events_to_dataframe, write_event_log

PINE_PATH = ROOT / "TV_REVIEW" / "phase72a_autonomous_trader.pine"
REPORTS = ROOT / "phase72b" / "reports"
DIAG = ROOT / "phase72b" / "diagnostics"
TV_REF = DIAG / "tv_event_log.csv"

TEST_WINDOWS = [
    {"id": "aug26_early", "start": "2026-08-26 08:00", "end": "2026-08-26 10:00", "label": "Aug26 early session"},
    {"id": "aug26_mid", "start": "2026-08-26 11:00", "end": "2026-08-26 14:00", "label": "Aug26 regular (screenshot window)"},
    {"id": "aug26_late", "start": "2026-08-26 14:00", "end": "2026-08-26 16:00", "label": "Aug26 late session"},
    {"id": "aug27_overnight", "start": "2026-08-27 18:00", "end": "2026-08-28 06:00", "label": "Aug27-28 overnight"},
    {"id": "aug28_session", "start": "2026-08-28 08:30", "end": "2026-08-28 16:00", "label": "Aug28 full session"},
    {"id": "jul_aug_2026", "start": "2026-07-01 00:00", "end": "2026-08-28 23:59", "label": "Jul-Aug 2026"},
]


def pine_hash() -> str:
    return hashlib.sha256(PINE_PATH.read_bytes()).hexdigest()[:16]


def mirror_hash() -> str:
    files = sorted((ROOT / "phase72b" / "python").glob("*.py"))
    h = hashlib.sha256()
    for f in files:
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def window_indices(m1: pd.DataFrame, start: str, end: str) -> tuple[int, int]:
    tz = m1.index.tz
    s = pd.Timestamp(start, tz=tz)
    e = pd.Timestamp(end, tz=tz)
    mask = (m1.index >= s) & (m1.index <= e)
    idx = m1.index[mask]
    if len(idx) == 0:
        raise ValueError(f"No bars in window {start} .. {end}")
    i0 = int(m1.index.get_loc(idx[0]))
    i1 = int(m1.index.get_loc(idx[-1])) + 1
    return max(0, i0 - DEFAULT_CFG.warmup - 5), i1


def count_events(df: pd.DataFrame) -> dict:
    return {
        "signals_long": int(df["signal_long"].sum()),
        "signals_short": int(df["signal_short"].sum()),
        "entries_long": int(df["enter_long"].sum()),
        "entries_short": int(df["enter_short"].sum()),
        "exits_stop": int(df["exit_stop"].sum()),
        "exits_target": int(df["exit_target"].sum()),
        "exits_time": int(df["exit_time"].sum()),
    }


def prefix_invariance_test(m1, m5, m15, start_i: int, end_i: int) -> dict:
    """Run full vs truncated prefixes; events on shared tail must match."""
    _, ev_full, _, _ = run_mirror(m1, m5, m15, start_i, end_i)
    mid = start_i + (end_i - start_i) // 2
    _, ev_prefix, _, _ = run_mirror(m1, m5, m15, start_i, mid + 200)
    df_f = events_to_dataframe(ev_full)
    df_p = events_to_dataframe(ev_prefix)
    tail_start = mid
    df_f_tail = df_f[df_f["bar_index"] >= tail_start].reset_index(drop=True)
    df_p_tail = df_p[df_p["bar_index"] >= tail_start].reset_index(drop=True)
    n = min(len(df_f_tail), len(df_p_tail))
    if n == 0:
        return {"pass": True, "checked": 0}
    cols = ["signal_long", "signal_short", "enter_long", "enter_short", "state_after", "reason_code"]
    mism = 0
    first = None
    for i in range(n):
        for c in cols:
            if df_f_tail.iloc[i][c] != df_p_tail.iloc[i][c]:
                mism += 1
                if first is None:
                    first = {"bar_index": int(df_f_tail.iloc[i]["bar_index"]), "column": c}
                break
    return {"pass": mism == 0, "checked": n, "mismatches": mism, "first": first}


def restart_test(m1, m5, m15, end_i: int) -> dict:
    starts = [DEFAULT_CFG.warmup, 50000, 500000, 1000000]
    starts = [s for s in starts if s < end_i - 1000]
    ref_start = starts[-1]
    _, ref_ev, _, _ = run_mirror(m1, m5, m15, ref_start, end_i)
    df_ref = events_to_dataframe(ref_ev)
    tail_from = ref_start + 5000
    results = []
    for s in starts[:-1]:
        _, ev, _, _ = run_mirror(m1, m5, m15, s, end_i)
        df = events_to_dataframe(ev)
        a = df[df["bar_index"] >= tail_from].reset_index(drop=True)
        b = df_ref[df_ref["bar_index"] >= tail_from].reset_index(drop=True)
        n = min(len(a), len(b))
        match = n > 0 and (a["signal_long"].equals(b["signal_long"].iloc[:n]) and a["enter_long"].equals(b["enter_long"].iloc[:n]))
        results.append({"start_i": s, "match": bool(match), "bars": n})
    conv = all(r["match"] for r in results if r["bars"] > 0)
    return {"pass": conv, "required_warmup_bars": ref_start, "details": results}


def compare_tv_python(py_df: pd.DataFrame, tv_path: Path) -> dict:
    if not tv_path.exists():
        return {"status": "NO_TV_REFERENCE"}
    tv = pd.read_csv(tv_path)
    # Expect compatible columns: bar_index or timestamp + event flags
    return {"status": "TV_LOADED", "tv_rows": len(tv), "python_rows": len(py_df)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Run full overlap (slow)")
    parser.add_argument("--window", type=str, default="aug26_mid")
    parser.add_argument(
        "--mode",
        choices=["MANUAL_CHART_PARITY", "CSV_PARITY"],
        default="MANUAL_CHART_PARITY",
        help="Parity mode (CSV optional; manual chart parity does not require tv_event_log.csv)",
    )
    args = parser.parse_args()

    REPORTS.mkdir(parents=True, exist_ok=True)
    DIAG.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    m1, m5, m15 = load_markets_lw()

    if args.full:
        start_i, end_i = DEFAULT_CFG.warmup, len(m1) - 61
        window_label = "full_overlap"
    else:
        win = next(w for w in TEST_WINDOWS if w["id"] == args.window)
        start_i, end_i = window_indices(m1, win["start"], win["end"])
        window_label = win["id"]

    _, events, win_start, win_end = run_mirror(m1, m5, m15, start_i, end_i)
    events = [e for e in events if win_start <= e.bar_index < win_end]
    py_df = events_to_dataframe(events)
    log_path = DIAG / "python_event_log.csv"
    write_event_log(events, str(log_path))

    tv_cmp = compare_tv_python(py_df, TV_REF)
    prefix = prefix_invariance_test(m1, m5, m15, start_i, end_i) if end_i - start_i > 2000 else {"pass": True, "skipped": True}
    restart = restart_test(m1, m5, m15, end_i) if args.full else {"pass": None, "skipped": True}

    event_counts = count_events(py_df)
    signal_events = py_df[py_df["signal_long"] | py_df["signal_short"]]
    entry_events = py_df[py_df["enter_long"] | py_df["enter_short"]]

    if args.mode == "CSV_PARITY":
        if tv_cmp["status"] == "NO_TV_REFERENCE":
            verdict = "INSUFFICIENT_TV_REFERENCE_DATA"
        elif not prefix.get("pass", True):
            verdict = "FAIL_CAUSALITY"
        elif restart.get("pass") is False:
            verdict = "RESTART_DEPENDENCE_FAIL"
        else:
            verdict = "PINE_LOGIC_MISMATCH_UNRESOLVED"
    else:
        # MANUAL_CHART_PARITY — CSV not required; use on-chart diagnostics + trace_timestamp.py
        if not prefix.get("pass", True):
            verdict = "FAIL_CAUSALITY"
        elif restart.get("pass") is False:
            verdict = "RESTART_DEPENDENCE_FAIL"
        else:
            verdict = "MANUAL_PARITY_IN_PROGRESS"

    summary = {
        "verdict": verdict,
        "parity_mode": args.mode,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "window": window_label,
        "bar_range": [start_i, end_i],
        "bars_processed": len(events),
        "runtime_sec": round(time.time() - t0, 2),
        "pine_hash": pine_hash(),
        "python_mirror_hash": mirror_hash(),
        "event_counts": event_counts,
        "parity": {
            "signal_timestamp": None,
            "entry_timestamp": None,
            "entry_direction": None,
            "entry_price": None,
            "exit_reason": None,
            "state_transition": None,
            "note": (
                "CSV export optional. Manual mode: use Pine Manual Parity table + trace_timestamp.py"
                if args.mode == "MANUAL_CHART_PARITY"
                else "TV CSV reference required for CSV_PARITY mode"
            ),
        },
        "prefix_invariance": prefix,
        "restart_test": restart,
        "tv_reference": tv_cmp,
        "ohlc_source": "phase58j LW NQ continuous 1M",
        "ground_truth": "TradingView phase72a_autonomous_trader.pine (NOT python ghosts)",
    }
    (REPORTS / "PARITY_SUMMARY.json").write_text(json.dumps(summary, indent=2))

    first_div = []
    if args.mode == "CSV_PARITY" and tv_cmp["status"] == "NO_TV_REFERENCE":
        first_div.append({
            "note": "CSV_PARITY mode: awaiting TV export at phase72b/diagnostics/tv_event_log.csv",
            "python_sample_signals": signal_events[["timestamp_chicago", "bar_index", "signal_long", "signal_short"]].head(20).to_dict("records"),
            "python_sample_entries": entry_events[["timestamp_chicago", "bar_index", "enter_long", "enter_short", "entry_price"]].head(20).to_dict("records"),
        })
    elif args.mode == "MANUAL_CHART_PARITY":
        first_div.append({
            "note": "MANUAL_CHART_PARITY: record TV values in phase72b/diagnostics/manual_tv_observations.csv (source=TV_MANUAL_REFERENCE)",
            "python_sample_signals": signal_events[["timestamp_chicago", "bar_index", "signal_long", "signal_short"]].head(20).to_dict("records"),
            "trace_command": f'python3 phase72b/tools/trace_timestamp.py --timestamp "YYYY-MM-DD HH:MM:SS" --timezone America/Chicago --before 10 --after 10',
        })
    pd.DataFrame(first_div).to_csv(REPORTS / "FIRST_DIVERGENCES.csv", index=False)

    report = f"""# Phase72B Parity Report

## Verdict: `{verdict}`

Generated: {summary['generated_at_utc']}

## Frozen sources

| Artifact | Hash |
|----------|------|
| Pine (`phase72a_autonomous_trader.pine`) | `{summary['pine_hash']}` |
| Python mirror (`phase72b/python/*`) | `{summary['python_mirror_hash']}` |

## Window

- **Label:** {window_label}
- **Bars:** {start_i} .. {end_i} ({len(events)} event rows)
- **Runtime:** {summary['runtime_sec']}s

## Python mirror event counts

```json
{json.dumps(event_counts, indent=2)}
```

## Ground truth rule

Ground truth is **actual TradingView autonomous trader behavior**, exported via Phase72B diagnostic plots.
`phase72a_python_review_ghosts.pine` is **display-only** and must not define expected events.

## TV reference status

{tv_cmp['status']}: Place machine-readable TV export at `{TV_REF.relative_to(ROOT)}`.

Enable **Phase72B export** in Pine (`exportParity` input), load on NQ1! 1M, export Data Window CSV for overlap window.

## Prefix invariance (causality)

```json
{json.dumps(prefix, indent=2)}
```

## Restart test

```json
{json.dumps(restart, indent=2)}
```

## Next steps for PASS

1. Export TV reference events for test windows (Aug 26 priority)
2. Run OHLC parity check (TV vs LW local) — stop on `DATA_SERIES_MISMATCH`
3. First-divergence loop: T-10..T+10 forensic window, fix root cause only, full rerun
4. Require 100% SIGNAL / ENTRY / EXIT / STATE parity before `PHASE72B_PARITY_PASS`

## Known audit items (Phase72B checklist)

- HTF bucket timing: developing HTF via `phase60/python/developing_htf.py`
- ATR: SMA(range,14) + `f_atrUse` fallback (not RMA)
- Cooldown: no decrement on exit bar (`p58SkipCooldownDec`)
- Entry: signal bar T, entry open T+1
- Phase71 STOP_FIRST same-bar stop+target
- Confidence/P4/H1: simplified port — verify against Pine on first divergence

"""
    (REPORTS / "PHASE72B_PARITY_REPORT.md").write_text(report)

    py_df.to_csv(DIAG / "parity_comparison.csv", index=False)

    print(json.dumps(summary, indent=2))
    print(f"Wrote {log_path}")
    print(f"Verdict: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
