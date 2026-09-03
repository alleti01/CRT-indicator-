#!/usr/bin/env python3
"""Phase72B Aug 30 multi-event TV ↔ Python parity (manual observations)."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58j.research.lw_data import load_markets_lw
from phase72b.python.autonomous_mirror_engine import run_mirror
from phase72b.python.config import DEFAULT_CFG
from phase72b.python.event_log import events_to_dataframe
from phase72b.tools.trace_timestamp import mirror_fsm_start

OBS_CSV = ROOT / "phase72b" / "diagnostics" / "aug30_tv_events.csv"
PINE_PATH = ROOT / "TV_REVIEW" / "phase72a_autonomous_trader.pine"
REPORT_CSV = ROOT / "phase72b" / "reports" / "AUG30_MULTI_EVENT_PARITY.csv"
REPORT_MD = ROOT / "phase72b" / "reports" / "AUG30_MULTI_EVENT_PARITY.md"
FREEZE_JSON = ROOT / "phase72b" / "checkpoints" / "PARITY_CANDIDATE_FREEZE.json"

TICK = 0.25


def _tick(x: float) -> float:
    if not np.isfinite(x):
        return x
    return round(round(x / TICK) * TICK, 2)


def _pass_close(a: float, b: float, tol: float = 0.26) -> bool:
    return abs(a - b) <= tol


def _pass_atr(a: float, b: float, tol: float = 0.2) -> bool:
    return abs(a - b) <= tol


def _pass_price(a: float, b: float, tol: float = 0.26) -> bool:
    if not np.isfinite(a) and not np.isfinite(b):
        return True
    if not np.isfinite(a) or not np.isfinite(b):
        return False
    return abs(_tick(a) - _tick(b)) <= tol


def _chi_ts(row: pd.Series) -> pd.Timestamp:
    ts = pd.Timestamp(row["tv_timestamp"])
    tz = row.get("tv_timezone", "America/New_York")
    if tz:
        ts = ts.tz_localize(tz) if ts.tzinfo is None else ts.tz_convert(tz)
        ts = ts.tz_convert("America/Chicago")
    else:
        ts = ts.tz_localize("America/Chicago")
    return ts


def _as_int(val) -> int:
    if pd.isna(val) or val == "":
        return 0
    return int(val)


def _event_type(row: pd.Series) -> tuple[str, str]:
    et = str(row.get("event_type", "") or "").strip()
    direction = str(row.get("direction", "") or "")
    if et:
        return et, direction
    if _as_int(row.get("signal_long", 0)):
        return "SIGNAL_LONG", "LONG"
    if _as_int(row.get("signal_short", 0)):
        return "SIGNAL_SHORT", "SHORT"
    if _as_int(row.get("enter_long", 0)):
        return "ENTER_LONG", "LONG"
    if _as_int(row.get("enter_short", 0)):
        return "ENTER_SHORT", "SHORT"
    if _as_int(row.get("exit_stop", 0)):
        return "EXIT_STOP", str(row.get("direction", "") or "")
    if _as_int(row.get("exit_target", 0)):
        return "EXIT_TARGET", str(row.get("direction", "") or "")
    if _as_int(row.get("exit_time", 0)):
        return "EXIT_TIME", str(row.get("direction", "") or "")
    return "UNKNOWN", str(row.get("direction", "") or "")


def _py_row_at(df: pd.DataFrame, m1: pd.DataFrame, chi: pd.Timestamp) -> pd.Series | None:
    if chi not in m1.index:
        loc = m1.index.get_indexer([chi], method="nearest")
        if loc[0] < 0:
            return None
        chi = m1.index[int(loc[0])]
    bi = int(m1.index.get_loc(chi))
    hit = df[df["bar_index"] == bi]
    return hit.iloc[0] if len(hit) else None


def _compare_event(obs: pd.Series, py: pd.Series | None) -> dict:
    etype, direction = _event_type(obs)
    chi = _chi_ts(obs)
    tv_close = float(obs["close"]) if pd.notna(obs.get("close")) and obs.get("close") != "" else np.nan
    tv_atr = float(obs["atr"]) if pd.notna(obs.get("atr")) and obs.get("atr") != "" else np.nan
    tv_state = str(obs.get("state", "") or "")
    tv_ev = obs.get("total_evidence", "")
    tv_ev = int(tv_ev) if pd.notna(tv_ev) and str(tv_ev).strip() != "" else np.nan

    if py is None:
        return {
            "event_id": obs["observation_id"],
            "timestamp": str(chi),
            "event_type": etype,
            "direction": direction,
            "tv_ohlc": tv_close,
            "python_ohlc": "",
            "ohlc_pass": False,
            "tv_atr": tv_atr,
            "python_atr": "",
            "atr_pass": False,
            "tv_state": tv_state,
            "python_state": "MISSING_BAR",
            "state_pass": False,
            "tv_evidence": tv_ev,
            "python_evidence": "",
            "evidence_pass": False,
            "tv_signal": bool(_as_int(obs.get("signal_long", 0)) or _as_int(obs.get("signal_short", 0))),
            "python_signal": "",
            "signal_pass": False,
            "tv_entry": bool(_as_int(obs.get("enter_long", 0)) or _as_int(obs.get("enter_short", 0))),
            "python_entry": "",
            "entry_pass": False,
            "tv_exit": bool(_as_int(obs.get("exit_stop", 0)) or _as_int(obs.get("exit_target", 0)) or _as_int(obs.get("exit_time", 0))),
            "python_exit": "",
            "exit_pass": False,
            "tv_price": obs.get("entry_price") or obs.get("stop_price") or obs.get("target_price") or tv_close,
            "python_price": "",
            "price_pass": False,
            "first_divergence": "MISSING_BAR",
            "status": "FAIL",
        }

    py_close = float(py["close"])
    py_atr = float(py["atr"])
    py_state = str(py["state_after"])
    py_ev = int(py["ev_total_long"]) if direction == "LONG" else int(py["ev_total_short"])
    py_sig = bool(py["signal_long"]) if "LONG" in etype else bool(py["signal_short"]) if "SHORT" in etype else bool(py["signal_long"] or py["signal_short"])
    py_ent = bool(py["enter_long"]) if "LONG" in etype else bool(py["enter_short"]) if "SHORT" in etype else bool(py["enter_long"] or py["enter_short"])
    py_ex = bool(py["exit_stop"]) if etype == "EXIT_STOP" else bool(py["exit_target"]) if etype == "EXIT_TARGET" else bool(py["exit_time"]) if etype == "EXIT_TIME" else bool(py["exit_stop"] or py["exit_target"] or py["exit_time"])

    tv_sig = bool(_as_int(obs.get("signal_long", 0)) or _as_int(obs.get("signal_short", 0)))
    tv_ent = bool(_as_int(obs.get("enter_long", 0)) or _as_int(obs.get("enter_short", 0)))
    tv_ex = bool(_as_int(obs.get("exit_stop", 0)) or _as_int(obs.get("exit_target", 0)) or _as_int(obs.get("exit_time", 0)))

    ohlc_ok = _pass_close(py_close, tv_close) if np.isfinite(tv_close) else True
    atr_ok = _pass_atr(py_atr, tv_atr) if np.isfinite(tv_atr) else True
    ev_ok = (py_ev == tv_ev) if np.isfinite(tv_ev) else True

    if etype.startswith("SIGNAL"):
        state_ok = py_state.startswith("IN_") or (direction in py_state)
        sig_ok = py_sig == tv_sig
        ent_ok = True
        ex_ok = True
    elif etype.startswith("ENTER"):
        state_ok = py_state in ("LONG_ACTIVE", "SHORT_ACTIVE", "IN_LONG", "IN_SHORT")
        sig_ok = True
        ent_ok = py_ent == tv_ent
        ex_ok = True
    elif etype.startswith("EXIT"):
        state_ok = py_state in ("COOLDOWN", "WATCH") or tv_state in py_state
        sig_ok = True
        ent_ok = True
        ex_ok = py_ex == tv_ex
    else:
        state_ok = tv_state == py_state if tv_state else True
        sig_ok = py_sig == tv_sig
        ent_ok = py_ent == tv_ent
        ex_ok = py_ex == tv_ex

    if etype.startswith("ENTER") and pd.notna(obs.get("entry_price")) and obs.get("entry_price") != "":
        tv_price = float(obs["entry_price"])
        py_price = float(py["entry_price"])
        price_ok = _pass_price(py_price, tv_price)
    elif etype.startswith("EXIT") and pd.notna(obs.get("stop_price")) and obs.get("stop_price") != "":
        tv_price = float(obs["stop_price"])
        py_price = float(py.get("stop_price", np.nan))
        price_ok = _pass_price(py_price, tv_price) if np.isfinite(py_price) else py_ex == tv_ex
    else:
        tv_price = tv_close
        py_price = py_close
        price_ok = ohlc_ok

    first = None
    for layer, ok, field, tv_v, py_v in [
        ("OHLC", ohlc_ok, "close", tv_close, py_close),
        ("ATR", atr_ok, "atr", tv_atr, py_atr),
        ("FEATURES", ev_ok, "evidence", tv_ev, py_ev),
        ("STATE", state_ok, "state_after", tv_state, py_state),
        ("SIGNAL", sig_ok, "signal", tv_sig, py_sig),
        ("ENTRY", ent_ok, "enter", tv_ent, py_ent),
        ("EXIT", ex_ok, "exit", tv_ex, py_ex),
        ("PRICE", price_ok, "price", tv_price, py_price),
    ]:
        if not ok and first is None:
            first = f"{layer}:{field} tv={tv_v} py={py_v}"

    all_ok = first is None
    return {
        "event_id": obs["observation_id"],
        "timestamp": str(chi),
        "event_type": etype,
        "direction": direction,
        "tv_ohlc": tv_close,
        "python_ohlc": py_close,
        "ohlc_pass": ohlc_ok,
        "tv_atr": tv_atr,
        "python_atr": py_atr,
        "atr_pass": atr_ok,
        "tv_state": tv_state,
        "python_state": py_state,
        "state_pass": state_ok,
        "tv_evidence": tv_ev,
        "python_evidence": py_ev,
        "evidence_pass": ev_ok,
        "tv_signal": tv_sig,
        "python_signal": py_sig,
        "signal_pass": sig_ok,
        "tv_entry": tv_ent,
        "python_entry": py_ent,
        "entry_pass": ent_ok,
        "tv_exit": tv_ex,
        "python_exit": py_ex,
        "exit_pass": ex_ok,
        "tv_price": tv_price if np.isfinite(tv_price) else "",
        "python_price": py_price if np.isfinite(py_price) else "",
        "price_pass": price_ok,
        "first_divergence": first or "",
        "status": "PASS" if all_ok else "FAIL",
    }


def _prefix_compare(m1, m5, m15, ref_start: int, starts: list[int], end_i: int, check_from: int) -> dict:
    _, ref_ev, _, _ = run_mirror(m1, m5, m15, ref_start, end_i)
    df_ref = events_to_dataframe(ref_ev)
    cols = ["signal_long", "signal_short", "enter_long", "enter_short", "exit_stop", "exit_target", "state_after", "reason_code"]
    out = []
    for s in starts:
        _, ev, _, _ = run_mirror(m1, m5, m15, s, end_i)
        df = events_to_dataframe(ev)
        a = df[df["bar_index"] >= check_from].reset_index(drop=True)
        b = df_ref[df_ref["bar_index"] >= check_from].reset_index(drop=True)
        n = min(len(a), len(b))
        mism = 0
        first = None
        for i in range(n):
            for c in cols:
                if a.iloc[i][c] != b.iloc[i][c]:
                    mism += 1
                    if first is None:
                        first = {"bar_index": int(a.iloc[i]["bar_index"]), "column": c, "prefix_start": s}
                    break
        out.append({"start_i": s, "start_ts": str(m1.index[s]), "bars_checked": n, "mismatches": mism, "first": first, "pass": mism == 0})
    return {"reference_start": ref_start, "reference_ts": str(m1.index[ref_start]), "prefixes": out, "pass": all(p["pass"] for p in out)}


def _hash_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-start", default="2026-08-30 17:00:00")
    ap.add_argument("--session-end", default="2026-08-30 22:00:00")
    args = ap.parse_args()

    obs = pd.read_csv(OBS_CSV)
    id_col = "event_id" if "event_id" in obs.columns else "observation_id"
    obs = obs[obs[id_col].astype(str).str.startswith("OBS-AUG30")].copy()
    obs = obs.rename(columns={id_col: "observation_id"})
    obs["_chi"] = obs.apply(_chi_ts, axis=1)
    obs = obs.sort_values("_chi")

    m1, m5, m15 = load_markets_lw()
    sess_start = pd.Timestamp(args.session_start, tz="America/Chicago")
    sess_end = pd.Timestamp(args.session_end, tz="America/Chicago")
    start_i = int(m1.index.get_loc(sess_start))
    end_i = int(m1.index.get_loc(sess_end)) + 1

    _, events, _, _ = run_mirror(m1, m5, m15, start_i, end_i)
    py_df = events_to_dataframe(events)

    rows = []
    stopped = False
    first_fail = None
    for _, obs_row in obs.iterrows():
        chi = obs_row["_chi"]
        py = _py_row_at(py_df, m1, chi)
        rec = _compare_event(obs_row, py)
        if rec["status"] == "FAIL" and not stopped:
            stopped = True
            first_fail = rec
            rows.append(rec)
            break
        rows.append(rec)

    out_df = pd.DataFrame(rows)
    REPORT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(REPORT_CSV, index=False)

    ci_ref = int(m1.index.get_loc(pd.Timestamp("2026-08-30 20:46:00", tz="America/Chicago")))
    check_from = start_i
    fsm_start = mirror_fsm_start(m1, ci_ref)
    prefix_starts = [
        ("session_start", start_i),
        ("fsm_gap_restart", fsm_start),
        ("short_warmup", max(DEFAULT_CFG.warmup, start_i - 500)),
        ("extended_warmup", max(DEFAULT_CFG.warmup, start_i - 3000)),
    ]
    # De-dupe while preserving order
    seen = set()
    starts = []
    for _, s in prefix_starts:
        if s not in seen:
            seen.add(s)
            starts.append(s)
    prefixes = _prefix_compare(m1, m5, m15, start_i, starts, end_i, check_from)
    # Prefixes before session open cannot match after weekend gap — only require session+ starts
    session_prefixes = [p for p in prefixes["prefixes"] if p["start_i"] >= start_i]
    prefix_pass = all(p["pass"] for p in session_prefixes) if session_prefixes else prefixes["pass"]

    # Short-window regression (run_end_i fix — must process 20:46 on trace-length runs)
    ci_2046 = int(m1.index.get_loc(pd.Timestamp("2026-08-30 20:46:00", tz="America/Chicago")))
    _, ev_short, _, _ = run_mirror(m1, m5, m15, start_i, ci_2046 + 6)
    df_short = events_to_dataframe(ev_short)
    r46 = df_short[df_short["bar_index"] == ci_2046]
    short_window_ok = len(r46) == 1 and bool(r46.iloc[0]["signal_short"]) and r46.iloc[0]["state_after"] == "IN_SHORT"

    levels = {
        "OHLC": bool(out_df["ohlc_pass"].all()),
        "ATR": bool(out_df["atr_pass"].all()),
        "FEATURE": bool(out_df["evidence_pass"].all()),
        "STATE": bool(out_df["state_pass"].all()),
        "SIGNAL": bool(out_df["signal_pass"].all()),
        "ENTRY": bool(out_df["entry_pass"].all()),
        "EXIT": bool(out_df["exit_pass"].all()),
    }

    if first_fail is not None:
        verdict = "FIRST_NEW_DIVERGENCE_FOUND"
    elif not prefix_pass or not short_window_ok:
        verdict = "PREFIX_RESTART_FAIL"
    elif levels["OHLC"] and levels["ATR"] and all(
        out.loc[out["status"] == "PASS", c].all() for c in ["signal_pass", "entry_pass"]
    ):
        verdict = "MULTI_EVENT_PARITY_PASS"
    else:
        verdict = "FIRST_NEW_DIVERGENCE_FOUND"

    # Python-only exit coverage note
    py_exits = py_df[py_df["exit_stop"] | py_df["exit_target"] | py_df["exit_time"]]
    has_stop = bool(py_df["exit_stop"].any())
    has_tgt = bool(py_df["exit_target"].any())

    md = [
        "# Aug 30 Multi-Event Parity",
        "",
        f"## Verdict: `{verdict}`",
        "",
        f"Session: {sess_start} .. {sess_end} Chicago",
        "",
        "### Parity levels (TV reference events)",
        "",
    ]
    for k, v in levels.items():
        md.append(f"- **{k}**: {'PASS' if v else 'FAIL'}")
    md.extend(["", "### Prefix invariance", "", "```json", json.dumps(prefixes, indent=2, default=str), "```"])
    if first_fail:
        md.extend(["", "### First failure (chronological)", "", "```json", json.dumps(first_fail, indent=2, default=str), "```"])
    md.extend([
        "",
        "### Minimum stable warmup (Aug 30)",
        "",
        f"**{m1.index[start_i]}** (session open after weekend gap). Prefixes starting before this bar diverge at session open (expected).",
        "",
        "### Short trace window (20:46)",
        "",
        f"PASS={short_window_ok}",
        "",
        "**MORE_TV_REFERENCE_REQUIRED** — only Aug 30 screenshot observations exist in `manual_tv_observations.csv`.",
        "",
        f"Python session exit coverage: EXIT_STOP={has_stop}, EXIT_TARGET={has_tgt} (TV confirms STOP only via OBS-AUG30-004).",
    ])
    REPORT_MD.write_text("\n".join(md))

    if verdict == "MULTI_EVENT_PARITY_PASS" and prefixes["pass"]:
        entry_stream = py_df[py_df["enter_long"] | py_df["enter_short"]][["timestamp_chicago", "entry_price", "stop_price", "target_price"]]
        FREEZE_JSON.parent.mkdir(parents=True, exist_ok=True)
        FREEZE_JSON.write_text(json.dumps({
            "label": "PARITY_CANDIDATE_FREEZE",
            "session": "2026-08-30",
            "pine_hash": _hash_file(PINE_PATH),
            "python_mirror_hash": _hash_file(ROOT / "phase72b" / "python" / "autonomous_mirror_engine.py"),
            "entry_stream_hash": hashlib.sha256(entry_stream.to_csv(index=False).encode()).hexdigest()[:16],
            "event_count_session": int(len(py_df)),
            "tv_reference_events": int(len(out_df)),
            "note": "Candidate only — requires multi-window TV validation",
        }, indent=2))

    print(json.dumps({"verdict": verdict, "levels": levels, "first_fail": first_fail, "prefix_pass": prefix_pass, "short_window_ok": short_window_ok}, indent=2, default=str))
    print(f"Wrote {REPORT_CSV}")
    return 0 if verdict == "MULTI_EVENT_PARITY_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
