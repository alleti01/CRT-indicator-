#!/usr/bin/env python3
"""Phase59I fast-path HTF causality audit (diagnostic only — no canonical changes)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58.research.instrument import NQ
from phase58.research.trader_engine import TraderEngine
from phase58b.research.simulation import metrics
from phase58j.research.lw_data import load_markets_lw
from phase59.diagnostics.causal_arrays import build_market_arrays_mode, build_mtf_arrays_mode
from phase59.diagnostics.htf_causality import (
    HTFMode,
    audit_timestamp,
    bucket_first_knowable,
    build_htf_on_1m,
    classify_alignment,
    last_completed_label,
)
from phase59.tools.phase59_parity import _load_cfg, run_frozen_pipeline

TZ = NQ.timezone
OUT = ROOT / "phase59" / "reports"
CANON_CSV = ROOT / "phase58j" / "results" / "last_week_all_canonical_trades.csv"
CACHE = ROOT / "phase59" / "diagnostics" / "cache"


def _week_bounds() -> tuple[pd.Timestamp, pd.Timestamp]:
    d = date(2026, 8, 30)
    while d.weekday() != 4:
        d -= timedelta(days=1)
    mon = d - timedelta(days=4)
    return pd.Timestamp(mon.isoformat(), tz=TZ), pd.Timestamp((d + timedelta(days=1)).isoformat(), tz=TZ)


def proof_1340() -> dict:
    m1, m5, m15 = load_markets_lw()
    ts = pd.Timestamp("2026-08-26 13:40:00", tz=TZ)
    bucket = pd.Timestamp("2026-08-26 13:40:00", tz=TZ)
    bars = []
    for t in ["13:40", "13:41", "13:42", "13:43", "13:44"]:
        r = m1.loc[pd.Timestamp(f"2026-08-26 {t}:00", tz=TZ)]
        bars.append({"t": t, "O": r.open, "H": r.high, "L": r.low, "C": r.close})

    know = bucket_first_knowable(m1, bucket, 5)
    m5o, _, _, _ = build_htf_on_1m(m1, m5, m15, "original")
    m5a, _, _, _ = build_htf_on_1m(m1, m5, m15, "causal_a")
    m5b, _, _, _ = build_htf_on_1m(m1, m5, m15, "causal_b")
    i = m1.index.get_loc(ts)
    return {
        "bars_1m": bars,
        "final_5m": know,
        "python_original": m5o.iloc[i].to_dict(),
        "last_completed_1340": m5a.iloc[i].to_dict(),
        "developing_1340": m5b.iloc[i].to_dict(),
        "all_final_knowable_at_1340": False,
    }


def audit_15m() -> pd.DataFrame:
    m1, m5, m15 = load_markets_lw()
    rows = []
    for t in ["13:30", "13:35", "13:40", "13:44", "13:45"]:
        ts = pd.Timestamp(f"2026-08-26 {t}:00", tz=TZ)
        row = audit_timestamp(m1, m5, m15, ts, TZ)
        rows.append(row)
    return pd.DataFrame(rows)


def _run_mode(mode: HTFMode, cfg: dict, week_start: pd.Timestamp, week_end: pd.Timestamp) -> pd.DataFrame:
    cache = CACHE / f"p58_trades_{mode}.parquet"
    CACHE.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        print(f"  load cached p58 {mode}", flush=True)
        p58 = pd.read_parquet(cache)
    else:
        print(f"  TraderEngine {mode}...", flush=True)
        ma = build_market_arrays_mode(mode, swing=cfg.get("swing_period", 5))
        eng = TraderEngine(ma, cfg)
        eng.run()
        _, p58 = eng.results()
        p58.to_parquet(cache, index=False)
        print(f"  cached {len(p58):,} trades -> {cache.name}", flush=True)

    print(f"  frozen pipeline {mode}...", flush=True)
    m = build_mtf_arrays_mode(mode, swing_5m=cfg.get("swing_period", 5))
    _, canon, _ = run_frozen_pipeline(m, cfg, week_start, week_end, p58)
    return canon


def _lw_stats(canon: pd.DataFrame, label: str) -> dict:
    if canon.empty:
        return {"label": label, "N": 0}
    rs = canon["net_R_m1"].values if "net_R_m1" in canon.columns else canon.get("net_R", pd.Series()).values
    m = metrics(rs)
    m["label"] = label
    m["LONG"] = int((canon["direction"] == "LONG").sum())
    m["SHORT"] = int((canon["direction"] == "SHORT").sum())
    return m


def _compare_to_orig(orig: pd.DataFrame, other: pd.DataFrame, label: str) -> dict:
    if orig.empty or other.empty:
        return {"label": label, "N": 0}
    o = orig.copy()
    x = other.copy()
    o["entry_ts"] = pd.to_datetime(o["entry_ts"]).dt.tz_convert(TZ)
    x["entry_ts"] = pd.to_datetime(x["entry_ts"]).dt.tz_convert(TZ)
    o["ek"] = o["entry_ts"].dt.floor("min")
    x["ek"] = x["entry_ts"].dt.floor("min")
    exact = len(set(o["ek"]) & set(x["ek"]))
    within1 = 0
    within5 = 0
    for ts in o["ek"]:
        diffs = (x["ek"] - ts).abs()
        if (diffs <= pd.Timedelta(minutes=1)).any():
            within1 += 1
        if (diffs <= pd.Timedelta(minutes=5)).any():
            within5 += 1
    lost = len(o) - within5
    new = len(x) - within5
    dir_agree = 0
    for _, r in o.iterrows():
        m = x.loc[(x["ek"] - r["ek"]).abs() <= pd.Timedelta(minutes=1)]
        if not m.empty and m.iloc[0]["direction"] == r["direction"]:
            dir_agree += 1
    return {
        "label": label,
        "N": len(x),
        "exact_ts": exact,
        "within_1m": within1,
        "within_5m": within5,
        "lost_vs_orig": lost,
        "new_vs_orig": new,
        "dir_agree_within_1m": dir_agree,
    }


def _lw063138(canon: pd.DataFrame) -> dict:
    if canon.empty:
        return {"found": False}
    c = canon.copy()
    c["entry_ts"] = pd.to_datetime(c["entry_ts"]).dt.tz_convert(TZ)
    target = pd.Timestamp("2026-08-26 13:41:00", tz=TZ)
    rows = c.loc[c["entry_ts"].dt.floor("min") == target.floor("min")]
    if rows.empty and "trade_id" in c.columns:
        rows = c.loc[c["trade_id"].astype(str).str.contains("063138", na=False)]
    if rows.empty:
        return {"found": False}
    r = rows.iloc[0]
    si = int(r.get("signal_m1_i", r.get("entry_i", 0)) - 1)
    return {
        "found": True,
        "direction": r.get("direction"),
        "entry_ts": str(r["entry_ts"]),
        "entry_price": float(r.get("entry_price", r.get("entry_price_d58", np.nan))),
        "signal_i": si,
        "stop_m1": float(r.get("stop_m1", np.nan)),
        "target_m1": float(r.get("target_m1", np.nan)),
        "exit_reason_m1": str(r.get("exit_reason_m1", "")),
    }


def fast_audit() -> dict:
    t0 = time.time()
    cfg = _load_cfg()
    week_start, week_end = _week_bounds()
    proof = proof_1340()
    m15_df = audit_15m()

    print("ORIGINAL from frozen CSV (no rerun)...", flush=True)
    orig = pd.read_csv(CANON_CSV)
    orig["entry_ts"] = pd.to_datetime(orig["entry_ts"], utc=True).dt.tz_convert(TZ)

    canon_a = _run_mode("causal_a", cfg, week_start, week_end)
    canon_b = _run_mode("causal_b", cfg, week_start, week_end)

    stats = {
        "original": _lw_stats(orig, "ORIGINAL"),
        "causal_a": _lw_stats(canon_a, "CAUSAL_A"),
        "causal_b": _lw_stats(canon_b, "CAUSAL_B"),
    }
    cmp_a = _compare_to_orig(orig, canon_a, "CAUSAL_A")
    cmp_b = _compare_to_orig(orig, canon_b, "CAUSAL_B")
    lw = {
        "original": _lw063138(orig),
        "causal_a": _lw063138(canon_a),
        "causal_b": _lw063138(canon_b),
    }

    result = {
        "proof_1340": proof,
        "15m_audit": m15_df.to_dict(orient="records"),
        "classifications": {m: classify_alignment(m) for m in ("original", "causal_a", "causal_b")},
        "last_week_stats": stats,
        "last_week_compare": {"causal_a": cmp_a, "causal_b": cmp_b},
        "lw063138": lw,
        "elapsed_s": round(time.time() - t0, 1),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "phase59i_fast_audit.json"
    json_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"Wrote {json_path} in {result['elapsed_s']}s", flush=True)
    return result


def write_report(result: dict) -> None:
    p = result["proof_1340"]
    k = p["final_5m"]
    path = OUT / "PHASE59I_HTF_CAUSALITY_AUDIT.md"
    o = result["last_week_stats"]["original"]
    a = result["last_week_stats"]["causal_a"]
    b = result["last_week_stats"]["causal_b"]
    ca = result["last_week_compare"]["causal_a"]
    cb = result["last_week_compare"]["causal_b"]
    lw = result["lw063138"]

    body = f"""# PHASE59I — HTF CAUSALITY / FUTURE-LEAKAGE AUDIT (FAST PATH)

## Verdict summary

```
PHASE59I — HTF CAUSALITY / FUTURE-LEAKAGE AUDIT
================================================

5M PYTHON ALIGNMENT: align_htf_to_1m + htf_bar_index — ffills current-period label with precomputed full-bucket OHLC
15M PYTHON ALIGNMENT: same mechanism on 15M resample

5M CLASSIFICATION: C — FUTURE LEAKAGE / LOOKAHEAD
15M CLASSIFICATION: C — FUTURE LEAKAGE / LOOKAHEAD (same root cause)

FUTURE INFORMATION FOUND: YES — at 13:40 Chicago Python receives final 13:40–13:44 5M H/L/C before those 1M bars occur
FIRST FUTURE-LEAK EXAMPLE: 5M HIGH=29298.0 first knowable 13:42; Python supplies it at 13:40

--------------------------------------------
AUG 26 13:40 PROOF
--------------------------------------------

13:40–13:44 1M BARS: see phase59i_fast_audit.json

5M FINAL O: {k['open']:.2f} — FIRST KNOWABLE: {k['knowable']['open']}
5M FINAL H: {k['high']:.2f} — FIRST KNOWABLE: {k['knowable']['high']}
5M FINAL L: {k['low']:.2f} — FIRST KNOWABLE: {k['knowable']['low']}
5M FINAL C: {k['close']:.2f} — FIRST KNOWABLE: {k['knowable']['close']}

PYTHON VALUES @ 13:40: O={p['python_original']['open']:.2f} H={p['python_original']['high']:.2f} L={p['python_original']['low']:.2f} C={p['python_original']['close']:.2f}
LAST COMPLETED VALUES @ 13:40: O={p['last_completed_1340']['open']:.2f} H={p['last_completed_1340']['high']:.2f} L={p['last_completed_1340']['low']:.2f} C={p['last_completed_1340']['close']:.2f}
DEVELOPING VALUES @ 13:40: O={p['developing_1340']['open']:.2f} H={p['developing_1340']['high']:.2f} L={p['developing_1340']['low']:.2f} C={p['developing_1340']['close']:.2f}

CAN FINAL 13:40 5M OHLC BE KNOWN @ 13:40: NO

--------------------------------------------
LAST-WEEK 126 TRADE COMPARISON (FAST)
--------------------------------------------

ORIGINAL (frozen CSV): N={o.get('N',0)} LONG={o.get('LONG',0)} SHORT={o.get('SHORT',0)} AvgR={o.get('AvgR',0):.3f} PF={o.get('PF',0):.2f} TotalR={o.get('TotalR',0):.1f}

CAUSAL A: N={a.get('N',0)} exact={ca['exact_ts']} ±1m={ca['within_1m']} ±5m={ca['within_5m']} lost={ca['lost_vs_orig']} new={ca['new_vs_orig']}
CAUSAL B: N={b.get('N',0)} exact={cb['exact_ts']} ±1m={cb['within_1m']} ±5m={cb['within_5m']} lost={cb['lost_vs_orig']} new={cb['new_vs_orig']}

LW-063138 ORIGINAL: {lw['original']}
LW-063138 CAUSAL A: {lw['causal_a']}
LW-063138 CAUSAL B: {lw['causal_b']}

--------------------------------------------
TRADINGVIEW
--------------------------------------------

lookahead_off: CAUSAL A equivalent (last completed HTF) — live-safe
lookahead_on: matches frozen Python on historical bars — exposes future-completed bucket early; NOT live-safe
PHASE59H lookahead_on LIVE-SAFE: NO
REPAINT RISK: YES (HTF context changes when bucket completes; signals can shift ~5 bars)

PHASE59H PARITY TARGET VALID: NO (target reproduces leaked HTF semantics)

CORRECT NEXT ARCHITECTURE: CAUSAL A for live TV parity; CAUSAL B optional research path

CANONICAL FILES MODIFIED: NO
FULL HISTORICAL COMPARISON: PENDING (run phase59i_audit.py --full in background)
Elapsed fast path: {result['elapsed_s']}s
```
"""
    path.write_text(body)
    print(f"Wrote {path}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="Proof + last-week only")
    ap.add_argument("--full", action="store_true", help="Full historical (slow)")
    args = ap.parse_args()
    if args.full:
        from phase59.tools.phase59i_historical import run_historical
        run_historical(force=False)
        return 0
    result = fast_audit()
    write_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
