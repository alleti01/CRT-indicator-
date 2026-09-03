#!/usr/bin/env python3
"""Phase59D — bar-by-bar Python canonical trace for TV parity forensic."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58.research.context import compute_context
from phase58.research.instrument import NQ
from phase58.research.location import compute_location
from phase58.research.reaction import compute_all_reactions
from phase58.research.trader_engine import TraderEngine
from phase58d.research.evidence import compute_evidence, decide
from phase58f.research.confidence import compute_confidence
from phase58f.research.policies import apply_policy
from phase58g.research.forensics import enrich
from phase58h.research.filters import apply_h_model
from phase58j.research.lw_data import build_market_arrays_lw, build_mtf_arrays_lw, load_markets_lw
from phase53.research.data import htf_bar_index
from phase59.research.pine_mirror_engine import PineMirrorEngine
from phase59.tools.phase59_parity import _load_cfg

TZ = NQ.timezone
OUT = ROOT / "phase59" / "reports" / "phase59d"
TRACE_START = pd.Timestamp("2026-08-26 13:00:00", tz=TZ)
TRACE_END = pd.Timestamp("2026-08-26 14:00:00", tz=TZ)
FOCUS_START = pd.Timestamp("2026-08-26 13:35:00", tz=TZ)
FOCUS_END = pd.Timestamp("2026-08-26 13:45:00", tz=TZ)

DATABENTO_OHLC = {
    "2026-08-26 13:36:00-05:00": (29297.25, 29298.25, 29293.50, 29298.00),
    "2026-08-26 13:37:00-05:00": (29298.00, 29298.25, 29292.75, 29293.75),
    "2026-08-26 13:38:00-05:00": (29294.00, 29296.50, 29290.00, 29295.50),
    "2026-08-26 13:39:00-05:00": (29295.00, 29296.75, 29290.75, 29292.00),
    "2026-08-26 13:40:00-05:00": (29292.00, 29293.75, 29288.50, 29293.50),
    "2026-08-26 13:41:00-05:00": (29293.25, 29294.75, 29290.75, 29293.75),
    "2026-08-26 13:42:00-05:00": (29293.50, 29298.00, 29292.50, 29292.75),
    "2026-08-26 13:43:00-05:00": (29292.00, 29294.25, 29288.00, 29289.25),
    "2026-08-26 13:44:00-05:00": (29289.50, 29295.25, 29288.50, 29295.00),
    "2026-08-26 13:45:00-05:00": (29295.00, 29313.75, 29294.75, 29311.25),
}


def _htf_ts(htf_index: pd.DatetimeIndex, pos: int) -> str:
    if pos < 0 or pos >= len(htf_index):
        return ""
    return str(htf_index[pos])


def ohlc_audit(m1_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ts_str, (o, h, l, c) in DATABENTO_OHLC.items():
        ts = pd.Timestamp(ts_str)
        if ts not in m1_df.index:
            rows.append({"ts_chicago": ts_str, "match": False, "note": "missing in python index"})
            continue
        r = m1_df.loc[ts]
        rows.append(
            {
                "ts_chicago": ts_str,
                "db_open": o,
                "py_open": float(r["open"]),
                "db_high": h,
                "py_high": float(r["high"]),
                "db_low": l,
                "py_low": float(r["low"]),
                "db_close": c,
                "py_close": float(r["close"]),
                "d_open": float(r["open"]) - o,
                "d_high": float(r["high"]) - h,
                "d_low": float(r["low"]) - l,
                "d_close": float(r["close"]) - c,
                "match": all(
                    abs(float(r[k]) - v) < 1e-6 for k, v in zip(["open", "high", "low", "close"], [o, h, l, c])
                ),
            }
        )
    return pd.DataFrame(rows)


def build_trace(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    m = build_market_arrays_lw(swing=cfg.get("swing_period", 5))
    m_mtf = build_mtf_arrays_lw(swing_5m=cfg.get("swing_period", 5))
    m1_df, m5_df, m15_df = load_markets_lw()
    m5_pos = htf_bar_index(m1_df.index, m5_df.index)
    m15_pos = htf_bar_index(m1_df.index, m15_df.index)

    eng = TraderEngine(m, cfg)
    eng.run()
    decisions_df, p58_trades = eng.results()
    dec_by_i = {int(r["bar_i"]): r for _, r in decisions_df.iterrows()}

    # Canonical mirror trades for Aug 26
    mirror = PineMirrorEngine(m_mtf, cfg, "TRACE")
    day_start = pd.Timestamp("2026-08-26 00:00:00", tz=TZ)
    day_end = pd.Timestamp("2026-08-27 00:00:00", tz=TZ)
    canon = mirror.run_batch(p58_trades, day_start, day_end)
    if not canon.empty:
        canon["entry_ts"] = pd.to_datetime(canon["entry_ts"]).dt.tz_convert(TZ)
        canon["signal_ts"] = [m.idx[int(si)] for si in canon["signal_m1_i"]]
    signal_lookup = {}
    entry_lookup = {}
    for _, t in canon.iterrows():
        si = int(t["signal_m1_i"])
        ei = int(t["entry_i"])
        signal_lookup[si] = t
        entry_lookup[ei] = t

    armed_min = cfg.get("armed_min_score", 2)
    take_thr = cfg.get("take_threshold", 4)

    rows: list[dict] = []
    for i in range(m.n):
        ts = m.idx[i]
        if ts < TRACE_START or ts >= TRACE_END:
            continue

        ctx = compute_context(m, i)
        loc_l = compute_location(m, i, "LONG")
        loc_s = compute_location(m, i, "SHORT")
        react_l = compute_all_reactions(m, i, "LONG", cfg)
        react_s = compute_all_reactions(m, i, "SHORT", cfg)
        ctx_sc_l = min(2, ctx["bull_score"])
        ctx_sc_s = min(2, ctx["bear_score"])
        total_arm_l = ctx_sc_l + loc_l["score"]
        total_arm_s = ctx_sc_s + loc_s["score"]

        dec = dec_by_i.get(i, {})
        m5_i = int(m5_pos[i])
        m15_i = int(m15_pos[i])

        ev = {}
        p58d_dec = ""
        p4_status = ""
        h1_status = ""
        if i in signal_lookup:
            ev_mtf = compute_evidence(m_mtf, i, signal_lookup[i]["direction"], cfg)
            p58d_dec, _ = decide(ev_mtf, "E", cfg, 0)
            conf = compute_confidence(m_mtf, i, signal_lookup[i]["direction"], cfg)
            row1 = pd.DataFrame([{**signal_lookup[i].to_dict(), **conf}])
            row1 = enrich(row1)
            row1["p4_status"] = apply_policy(row1, "P4")
            row1["h1_status"] = apply_h_model(row1, "H1")
            ev = ev_mtf
            p4_status = str(row1.iloc[0]["p4_status"])
            h1_status = str(row1.iloc[0]["h1_status"])
            conf = row1.iloc[0]

        sig_trade = signal_lookup.get(i)
        ent_trade = entry_lookup.get(i)
        tid = ""
        if ent_trade is not None:
            tid = str(ent_trade.get("trade_id", ""))
        elif sig_trade is not None:
            tid = str(sig_trade.get("trade_id", ""))

        rows.append(
            {
                "bar_i": i,
                "ts_utc": str(ts.tz_convert("UTC")),
                "ts_chicago": str(ts),
                "ts_ny": str(ts.tz_convert("America/New_York")),
                "unix_ms": int(ts.tz_convert("UTC").timestamp() * 1000),
                "open": m.op[i],
                "high": m.hi[i],
                "low": m.lo[i],
                "close": m.cl[i],
                "atr": m.atr[i],
                "m5_completed_ts": _htf_ts(m5_df.index, m5_i),
                "m15_completed_ts": _htf_ts(m15_df.index, m15_i),
                "m5_open": float(m5_df.iloc[m5_i]["open"]),
                "m5_high": float(m5_df.iloc[m5_i]["high"]),
                "m5_low": float(m5_df.iloc[m5_i]["low"]),
                "m5_close": float(m5_df.iloc[m5_i]["close"]),
                "m15_open": float(m15_df.iloc[m15_i]["open"]),
                "m15_high": float(m15_df.iloc[m15_i]["high"]),
                "m15_low": float(m15_df.iloc[m15_i]["low"]),
                "m15_close": float(m15_df.iloc[m15_i]["close"]),
                "ctxDir": ctx["direction"],
                "ctxConf": ctx["confidence"],
                "bullSc": ctx["bull_score"],
                "bearSc": ctx["bear_score"],
                "ctxRs": "|".join(ctx["reasons"]),
                "locationScore_LONG": loc_l["score"],
                "locationScore_SHORT": loc_s["score"],
                "reactionScore_LONG": react_l["score"],
                "reactionScore_SHORT": react_s["score"],
                "totalArm_LONG": total_arm_l,
                "totalArm_SHORT": total_arm_s,
                "would_arm_LONG": total_arm_l >= armed_min and ctx["direction"] == "BULLISH",
                "would_arm_SHORT": total_arm_s >= armed_min and ctx["direction"] == "BEARISH",
                "engine_state": dec.get("state", ""),
                "engine_decision": dec.get("decision", ""),
                "engine_dir": dec.get("direction", ""),
                "armedBar": dec.get("armed_i", -1),
                "armedPrice": dec.get("armed_price", np.nan),
                "pbExtreme": dec.get("pb_extreme", np.nan),
                "engine_total_score": dec.get("total_score", 0),
                "rawTake_engine": dec.get("decision") == "TAKE",
                "evTotal": ev.get("total_evidence", np.nan),
                "evLoc": ev.get("location_score", np.nan),
                "evDir": ev.get("direction_score", np.nan),
                "evReact": ev.get("reaction_score", np.nan),
                "evContra": ev.get("contra_score", np.nan),
                "phase58d_decision": p58d_dec,
                "p4_status": p4_status,
                "h1_status": h1_status,
                "canonical_signal": i in signal_lookup,
                "canonical_entry": i in entry_lookup,
                "trade_id": tid,
                "signal_trade_id": str(sig_trade.get("trade_id", "")) if sig_trade is not None else "",
                "entry_price_canon": ent_trade.get("entry_price", np.nan) if ent_trade is not None else np.nan,
                "stop_m1": ent_trade.get("stop_m1", np.nan) if ent_trade is not None else np.nan,
                "target_m1": ent_trade.get("target_m1", np.nan) if ent_trade is not None else np.nan,
            }
        )

    trace_df = pd.DataFrame(rows)
    focus_df = trace_df.loc[(trace_df["ts_chicago"] >= str(FOCUS_START)) & (trace_df["ts_chicago"] <= str(FOCUS_END))].copy()
    ohlc_df = ohlc_audit(m1_df)
    return trace_df, focus_df, ohlc_df, canon


def analyze_divergence(trace_df: pd.DataFrame, canon: pd.DataFrame) -> dict:
    """Heuristic first-divergence notes for report (Python ground truth)."""
    out: dict = {}
    if canon.empty:
        out["note"] = "no canonical trades"
        return out

    day = canon.copy()
    day["entry_ts"] = pd.to_datetime(day["entry_ts"]).dt.tz_convert(TZ)
    window = day.loc[(day["entry_ts"] >= TRACE_START) & (day["entry_ts"] < TRACE_END)]
    out["python_trades_in_window"] = window[
        ["trade_id", "direction", "signal_ts", "entry_ts", "entry_price", "stop_m1", "target_m1"]
    ].to_dict(orient="records")

    wrong = window.loc[
        (window["entry_ts"] >= pd.Timestamp("2026-08-26 13:30:00", tz=TZ))
        & (window["entry_ts"] <= pd.Timestamp("2026-08-26 13:34:00", tz=TZ))
    ]
    out["python_has_1331_1333_trade"] = len(wrong) > 0
    out["python_1331_1333"] = wrong.to_dict(orient="records") if len(wrong) else []

    sig = trace_df.loc[trace_df["canonical_signal"]]
    out["python_signal_bars"] = sig[["ts_chicago", "trade_id", "ctxDir", "evTotal", "phase58d_decision", "p4_status", "h1_status"]].to_dict(
        orient="records"
    )

    ref_sig = trace_df.loc[trace_df["ts_chicago"].str.contains("13:40:00")]
    ref_ent = trace_df.loc[trace_df["ts_chicago"].str.contains("13:41:00")]
    if len(ref_sig):
        out["ref_1340_signal"] = ref_sig.iloc[0].to_dict()
    if len(ref_ent):
        out["ref_1341_entry"] = ref_ent.iloc[0].to_dict()
        out["python_atr_1341"] = float(ref_ent.iloc[0]["atr"])
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = _load_cfg()
    trace_df, focus_df, ohlc_df, canon = build_trace(cfg)
    analysis = analyze_divergence(trace_df, canon)

    trace_df.to_csv(OUT / "trace_1300_1400_chicago.csv", index=False)
    focus_df.to_csv(OUT / "trace_1335_1345_chicago.csv", index=False)
    ohlc_df.to_csv(OUT / "ohlc_databento_vs_python.csv", index=False)
    (OUT / "trace_analysis.json").write_text(json.dumps(analysis, indent=2, default=str))

    ohlc_pass = bool(ohlc_df["match"].all()) if len(ohlc_df) else False
    print("PHASE59D PYTHON TRACE")
    print(f"OHLC Databento vs Python: {'PASS' if ohlc_pass else 'FAIL'}")
    print(f"Trace bars: {len(trace_df)} | Focus: {len(focus_df)}")
    print("Python trades 13:00-14:00:")
    for t in analysis.get("python_trades_in_window", []):
        print(f"  {t}")
    print(f"Python has 13:31-13:33 trade: {analysis.get('python_has_1331_1333_trade')}")
    if analysis.get("ref_1340_signal"):
        r = analysis["ref_1340_signal"]
        print(
            f"13:40: ctx={r['ctxDir']} locL={r['locationScore_LONG']} reactL={r['reactionScore_LONG']} "
            f"rawTake={r['rawTake_engine']} canon_signal={r['canonical_signal']}"
        )
    if analysis.get("python_atr_1341"):
        print(f"ATR@13:41 Python: {analysis['python_atr_1341']}")
    print(f"Output: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
