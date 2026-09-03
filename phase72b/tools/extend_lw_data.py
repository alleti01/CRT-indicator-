#!/usr/bin/env python3
"""Extend Phase58J LW NQ 1M data for Phase72B parity (merge-only or download).

Uses the SAME source/methodology as phase58j/research/lw_data.py:
  - Databento GLBX.MDP3 ohlcv-1m, NQ.v.0 volume continuous
  - Appended to phase58j/data/nq_continuous_1m_lw_extension.csv
  - Historical bars preserved (append-only dedupe by timestamp)

Does NOT modify trading logic, Pine, or Python mirror.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase16.data_loader import load_ohlcv_csv
from phase58j.research.lw_data import EXTENSION, data_compatibility_report, load_market_1m_lw

REPORT = ROOT / "phase72b" / "reports" / "DATA_EXTENSION_REPORT.md"
MERGE_REPORT = ROOT / "phase72b" / "reports" / "DATA_MERGE_REPORT.md"
CHECKPOINT = ROOT / "phase72b" / "checkpoints" / "02_ohlc_parity.json"
DEFAULT_APPEND = ROOT / "phase58j" / "data" / "nq_continuous_1m_lw_extension_append.csv"
REF_CHI = pd.Timestamp("2026-08-30 20:46:00", tz="America/Chicago")


def _utc_after_last_bar() -> str:
    if not EXTENSION.exists():
        raise FileNotFoundError(f"Missing extension file: {EXTENSION}")
    raw = pd.read_csv(EXTENSION)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
    last_utc = raw["timestamp"].max()
    nxt = last_utc + pd.Timedelta(minutes=1)
    return nxt.strftime("%Y-%m-%dT%H:%M:%S")


def _download_append(start_utc: str, end_utc: str, max_cost: float, tmp: Path) -> Path:
    cmd = [
        sys.executable,
        str(ROOT / "phase16" / "download_databento.py"),
        "--start", start_utc,
        "--end", end_utc,
        "--symbols", "NQ.v.0",
        "--output", str(tmp),
        "--chunk-days", "7",
        "--max-cost-usd", str(max_cost),
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    return tmp


def _normalize_raw_ts(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S%z")


def _merge_raw_csv(old_path: Path, append_path: Path) -> tuple[pd.DataFrame, dict]:
    """Merge raw CSV rows; keep existing timestamps (conservative dedupe)."""
    old_rows = pd.read_csv(old_path)
    append_rows = pd.read_csv(append_path)
    old_rows["_ts"] = pd.to_datetime(old_rows["timestamp"], utc=True)
    append_rows["_ts"] = pd.to_datetime(append_rows["timestamp"], utc=True)

    old_ts_set = set(old_rows["timestamp"].astype(str))
    dup_in_append = append_rows["timestamp"].astype(str).isin(old_ts_set)
    n_dup = int(dup_in_append.sum())
    new_only = append_rows[~dup_in_append].copy()

    combined = pd.concat([old_rows, new_only], ignore_index=True)
    combined = combined.sort_values("_ts")
    combined = combined.drop(columns=["_ts"])
    combined = combined.drop_duplicates(subset=["timestamp"], keep="first")

    stats = {
        "append_file_rows": len(append_rows),
        "duplicate_timestamps_skipped": n_dup,
        "bars_appended": len(new_only),
        "combined_raw_rows": len(combined),
    }
    return combined, stats


def _integrity_report_normalized(df: pd.DataFrame, prev_last_chi: str) -> dict:
    gaps = []
    if len(df) > 1:
        diffs = pd.Series(df.index[1:] - df.index[:-1]).dt.total_seconds() / 60
        big = diffs[diffs > 1.5]
        for pos in big.index[:30]:
            gaps.append({"after": str(df.index[pos]), "gap_minutes": float(diffs.iloc[pos])})

    ohlc_bad = int((df["high"] < df["low"]).sum())
    hi_floor = df[["open", "close", "low"]].max(axis=1)
    lo_ceil = df[["open", "close", "high"]].min(axis=1)
    ohlc_bad += int(((df["high"] < hi_floor) | (df["low"] > lo_ceil)).sum())

    return {
        "previous_last_timestamp": prev_last_chi,
        "new_last_timestamp": str(df.index.max()),
        "combined_bar_count": len(df),
        "duplicate_timestamps": int(df.index.duplicated().sum()),
        "ohlc_invalid_rows": ohlc_bad,
        "missing_intervals_over_90s_sample": gaps[:15],
        "aug30_ref_present": REF_CHI in df.index,
        "symbol": "NQ.v.0",
        "adjustment": "Databento volume continuous (unchanged methodology)",
    }


def merge_existing_append(append_path: Path) -> dict:
    if not EXTENSION.exists():
        raise FileNotFoundError(EXTENSION)
    if not append_path.exists():
        raise FileNotFoundError(append_path)

    before_combined = load_market_1m_lw()
    prev_last = str(before_combined.index.max())

    combined_raw, merge_stats = _merge_raw_csv(EXTENSION, append_path)
    combined_raw.to_csv(EXTENSION, index=False)

    after_combined = load_market_1m_lw()
    integrity = _integrity_report_normalized(after_combined, prev_last)
    integrity["bars_appended"] = merge_stats["bars_appended"]
    integrity["duplicate_timestamps_skipped"] = merge_stats["duplicate_timestamps_skipped"]

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "MERGE_EXISTING_APPEND",
        "append_source": str(append_path),
        "merge_stats": merge_stats,
        "integrity": integrity,
        "compatibility": data_compatibility_report(before_combined, after_combined),
    }

    if integrity["ohlc_invalid_rows"] > 0 or integrity["duplicate_timestamps"] > 0:
        report["verdict"] = "MERGE_FAIL"
        report["reason"] = "OHLC integrity or duplicate timestamps after merge"
    elif not integrity["aug30_ref_present"]:
        report["verdict"] = "MERGE_FAIL"
        report["reason"] = f"Reference timestamp not in dataset: {REF_CHI}"
    else:
        report["verdict"] = "MERGE_PASS_READY_FOR_PARITY"

    return report


def _write_report(report: dict, path: Path = REPORT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase72B Data Merge / Extension Report",
        "",
        f"## Verdict: `{report.get('verdict', 'UNKNOWN')}`",
        "",
        f"Generated: {report.get('generated_at_utc', '')}",
        "",
        "```json",
        json.dumps(report, indent=2, default=str),
        "```",
    ]
    path.write_text("\n".join(lines))


def _run_trace_and_parity() -> dict:
    """Run trace at OBS-AUG30-001 and compare OHLC→ATR→features→state→signal."""
    from phase72b.python.autonomous_mirror_engine import run_mirror
    from phase72b.tools.trace_timestamp import mirror_fsm_start
    from phase58j.research.lw_data import load_markets_lw

    m1, m5, m15 = load_markets_lw()
    ref = REF_CHI
    if ref not in m1.index:
        loc = m1.index.get_indexer([ref], method="nearest")
        ci = int(loc[0])
    else:
        ci = int(m1.index.get_loc(ref))

    mirror_start_i = mirror_fsm_start(m1, ci)
    end_i = min(len(m1) - 61, ci + 11)
    _, events, _, _ = run_mirror(m1, m5, m15, mirror_start_i, end_i)
    from phase72b.python.event_log import events_to_dataframe
    df = events_to_dataframe(events)

    target = df[df["bar_index"] == ci]
    if target.empty:
        target = df.iloc[[min(len(df) - 1, 10)]]

    row = target.iloc[0]
    tv = {
        "close": 29308.75,
        "atr": 15.5,
        "state": "IN_SHORT",
        "signal_short": True,
        "ev_total_short": 6,
    }
    py = {
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "atr": float(row["atr"]),
        "state_after": str(row["state_after"]),
        "signal_short": bool(row["signal_short"]),
        "ev_total_short": int(row.get("ev_total_short", row.get("ev_total_short", 0))),
        "raw_short": bool(row.get("raw_short", False)),
        "ctx_dir": str(row.get("ctx_dir", "")),
    }

    layers = []
    first_div = None

    def _tick(a: float, b: float, tol: float = 0.01) -> bool:
        return abs(a - b) <= tol

    ohlc_ok = (
        _tick(py["close"], tv["close"], 0.25)
    )
    layers.append({"layer": "OHLC", "tv_close": tv["close"], "py_close": py["close"], "pass": ohlc_ok})
    if not ohlc_ok and first_div is None:
        first_div = {"layer": "OHLC", "field": "close", "tv": tv["close"], "python": py["close"]}

    atr_ok = _tick(py["atr"], tv["atr"], 0.15)
    layers.append({"layer": "ATR", "tv": tv["atr"], "python": py["atr"], "pass": atr_ok})
    if ohlc_ok and not atr_ok and first_div is None:
        first_div = {"layer": "ATR", "field": "atr", "tv": tv["atr"], "python": py["atr"]}

    feat_ok = py["ev_total_short"] == tv["ev_total_short"]
    layers.append({
        "layer": "FEATURES",
        "tv_ev_short": tv["ev_total_short"],
        "py_ev_short": py["ev_total_short"],
        "py_ctx": py["ctx_dir"],
        "pass": feat_ok,
    })
    if ohlc_ok and atr_ok and not feat_ok and first_div is None:
        first_div = {"layer": "FEATURES", "field": "ev_total_short", "tv": tv["ev_total_short"], "python": py["ev_total_short"]}

    st_ok = py["state_after"] == tv["state"]
    layers.append({"layer": "STATE", "tv": tv["state"], "python": py["state_after"], "pass": st_ok})
    if ohlc_ok and atr_ok and feat_ok and not st_ok and first_div is None:
        first_div = {"layer": "STATE", "field": "state_after", "tv": tv["state"], "python": py["state_after"]}

    sig_ok = py["signal_short"] == tv["signal_short"]
    layers.append({"layer": "SIGNAL", "tv_signal_short": tv["signal_short"], "py_signal_short": py["signal_short"], "pass": sig_ok})
    if ohlc_ok and atr_ok and feat_ok and st_ok and not sig_ok and first_div is None:
        first_div = {"layer": "SIGNAL", "field": "signal_short", "tv": tv["signal_short"], "python": py["signal_short"]}

    return {
        "observation_id": "OBS-AUG30-001",
        "timestamp_chicago": str(row["timestamp_chicago"]),
        "bar_index": int(row["bar_index"]),
        "python_bar": py,
        "tv_reference": tv,
        "layer_results": layers,
        "first_divergence": first_div,
        "trace_row": row.to_dict(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Extend LW NQ 1M for Phase72B")
    ap.add_argument(
        "--mode",
        choices=["download", "merge-existing-append", "dry-run"],
        default="merge-existing-append",
        help="merge-existing-append: no download; merge append CSV",
    )
    ap.add_argument("--append-file", type=str, default=str(DEFAULT_APPEND))
    ap.add_argument("--end", default="2026-09-03T00:00:00")
    ap.add_argument("--max-cost-usd", type=float, default=2.0)
    ap.add_argument("--run-parity", action="store_true", default=True)
    ap.add_argument("--no-parity", action="store_true")
    args = ap.parse_args()

    if args.mode == "dry-run":
        old_combined = load_market_1m_lw()
        print(json.dumps({
            "old_last": str(old_combined.index.max()),
            "append_file": args.append_file,
            "append_exists": Path(args.append_file).exists(),
        }, indent=2))
        return 0

    if args.mode == "merge-existing-append":
        report = merge_existing_append(Path(args.append_file))
        _write_report(report, MERGE_REPORT)
        _write_report(report, REPORT)

        CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
        CHECKPOINT.write_text(json.dumps({
            "checkpoint": "02_ohlc_parity",
            "status": "READY" if report["verdict"] == "MERGE_PASS_READY_FOR_PARITY" else "FAIL",
            "verdict": report["verdict"],
            "updated_at_utc": report["generated_at_utc"],
        }, indent=2))

        print(json.dumps(report, indent=2, default=str))

        if report["verdict"] == "MERGE_PASS_READY_FOR_PARITY" and not args.no_parity:
            parity = _run_trace_and_parity()
            parity_path = ROOT / "phase72b" / "reports" / "OBS_AUG30_001_PARITY.json"
            parity_path.write_text(json.dumps(parity, indent=2, default=str))
            print("\n=== PARITY COMPARISON OBS-AUG30-001 ===")
            print(json.dumps(parity, indent=2, default=str))

            div_report = ROOT / "phase72b" / "reports" / "FIRST_DIVERGENCE_AUG30.md"
            fd = parity.get("first_divergence")
            div_report.write_text(
                "# First Divergence — OBS-AUG30-001\n\n"
                f"Timestamp: {parity.get('timestamp_chicago')}\n\n"
                f"## Layer results\n\n```json\n{json.dumps(parity.get('layer_results'), indent=2)}\n```\n\n"
                f"## First divergence\n\n```json\n{json.dumps(fd, indent=2)}\n```\n"
            )

        return 0 if report["verdict"] == "MERGE_PASS_READY_FOR_PARITY" else 2

    # download mode (legacy)
    if not EXTENSION.exists():
        print(f"ERROR: {EXTENSION} missing")
        return 2
    old_combined = load_market_1m_lw()
    start_utc = _utc_after_last_bar()
    tmp = Path(args.append_file)
    try:
        _download_append(start_utc, args.end, args.max_cost_usd, tmp)
    except (subprocess.CalledProcessError, RuntimeError) as exc:
        report = {"verdict": "DATA_ACQUISITION_BLOCKED", "reason": str(exc)}
        _write_report(report)
        print(json.dumps(report, indent=2))
        return 2
    report = merge_existing_append(tmp)
    _write_report(report)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["verdict"] == "MERGE_PASS_READY_FOR_PARITY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
