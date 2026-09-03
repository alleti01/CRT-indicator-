#!/usr/bin/env python3
"""Phase59E — extended Python forensic trace + TV comparison template."""
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
from phase58.research.trader_state import State
from phase58j.research.lw_data import build_market_arrays_lw, load_markets_lw
from phase59.tools.phase59_parity import _load_cfg

TZ = NQ.timezone
OUT = ROOT / "phase59" / "reports" / "phase59e"
WIN_START = pd.Timestamp("2026-08-26 13:20:00", tz=TZ)
WIN_END = pd.Timestamp("2026-08-26 13:46:00", tz=TZ)
FOCUS_START = pd.Timestamp("2026-08-26 13:24:00", tz=TZ)
FOCUS_END = pd.Timestamp("2026-08-26 13:34:00", tz=TZ)


def _pine_state(st: State | str) -> int:
    s = st.value if hasattr(st, "value") else str(st)
    m = {
        "WATCH": 0,
        "ARMED_LONG": 1,
        "ARMED_SHORT": -1,
        "IN_LONG": 2,
        "IN_SHORT": -2,
        "COOLDOWN": 3,
    }
    return m.get(s, 0)


def _run_sequential_trace(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    m = build_market_arrays_lw(swing=cfg.get("swing_period", 5))
    m1_df, _, _ = load_markets_lw()

    eng = TraderEngine(m, cfg)
    warmup = eng.warmup
    end_i = m.n - 61
    rows: list[dict] = []

    for i in range(warmup, end_i):
        snap = eng.on_bar_close(i)
        ts = m.idx[i]
        if ts < WIN_START or ts >= WIN_END:
            continue

        ctx = compute_context(m, i)
        loc_l = compute_location(m, i, "LONG")
        loc_s = compute_location(m, i, "SHORT")
        react_l = compute_all_reactions(m, i, "LONG", cfg)
        react_s = compute_all_reactions(m, i, "SHORT", cfg)

        t = eng.st.trade
        p58_in = t is not None and eng.st.state in (State.IN_LONG, State.IN_SHORT)
        raw_take = snap.decision.value in ("TAKE_LONG", "TAKE_SHORT")

        # Opportunity id from canonical mirror lookup (signal bars only)
        opp_id = ""
        if raw_take:
            opp_id = f"OPP_{i}_{snap.direction}"

        rows.append(
            {
                "bar_i": i,
                "ts_utc": str(ts.tz_convert("UTC")),
                "ts_chicago": str(ts),
                "ts_ny": str(ts.tz_convert("America/New_York")),
                "unix_ms": int(ts.tz_convert("UTC").timestamp() * 1000),
                "open": float(m.op[i]),
                "high": float(m.hi[i]),
                "low": float(m.lo[i]),
                "close": float(m.cl[i]),
                "atr": float(m.atr[i]),
                "ctxDir": ctx["direction"],
                "reactL": react_l["score"],
                "reactS": react_s["score"],
                "p58InTrade": p58_in,
                "p58State": _pine_state(eng.st.state),
                "p58StateName": eng.st.state.value,
                "p58Dir": eng.st.direction,
                "rawTake": raw_take,
                "decision": snap.decision.value,
                "opportunity_id": opp_id,
                "internal_dir": t.direction if t else "",
                "internal_entry": float(t.entry_price) if t else np.nan,
                "internal_stop": float(t.stop) if t else np.nan,
                "internal_target": float(t.target) if t else np.nan,
                "internal_exit_reason": "",
                "armedBar": eng.st.armed_i,
                "armedBars": eng.st.armed_bars,
                "armedPrice": eng.st.armed_price,
                "total_score": snap.total_score,
                "location_score": snap.location_score,
                "reaction_score": snap.reaction_score,
            }
        )
        if snap.decision.value.startswith("EXIT_"):
            rows[-1]["internal_exit_reason"] = snap.decision.value.replace("EXIT_", "")

    df = pd.DataFrame(rows)
    focus = df.loc[(df["ts_chicago"] >= str(FOCUS_START)) & (df["ts_chicago"] <= str(FOCUS_END))].copy()

    _, p58 = eng.results()
    if not p58.empty:
        sig_set = set(int(x) for x in p58["signal_i"])
        ent_map = {int(r["entry_i"]): r for _, r in p58.iterrows()}
        df["canonical_signal"] = df["bar_i"].isin(sig_set)
        df["canonical_entry"] = df["bar_i"].isin(ent_map)
        df["canon_trade_id"] = df["bar_i"].apply(
            lambda bi: ent_map[bi]["trade_id"] if bi in ent_map else ""
        )

    return df, focus


def comparison_template(df: pd.DataFrame) -> pd.DataFrame:
    """Side-by-side template: fill tv_* columns from TradingView Data Window."""
    cols = [
        "ts_chicago",
        "ts_ny",
        "unix_ms",
        "open",
        "high",
        "low",
        "close",
        "atr",
        "p58InTrade",
        "p58State",
        "p58Dir",
        "reactL",
        "reactS",
        "ctxDir",
        "rawTake",
        "decision",
        "internal_dir",
        "internal_entry",
        "internal_stop",
        "internal_target",
        "internal_exit_reason",
    ]
    out = df[cols].copy()
    out = out.rename(
        columns={
            "open": "db_open",
            "high": "db_high",
            "low": "db_low",
            "close": "db_close",
            "atr": "python_atr",
            "p58InTrade": "python_p58InTrade",
            "p58State": "python_p58State",
            "p58Dir": "python_p58Dir",
            "reactL": "python_reactL",
            "reactS": "python_reactS",
            "ctxDir": "python_ctxDir",
            "rawTake": "python_rawTake",
            "decision": "python_decision",
            "internal_dir": "python_internal_dir",
            "internal_entry": "python_internal_entry",
            "internal_stop": "python_internal_stop",
            "internal_target": "python_internal_target",
            "internal_exit_reason": "python_internal_exit",
        }
    )
    for c in ("tv_open", "tv_high", "tv_low", "tv_close", "tv_atr", "tv_p58InTrade", "tv_p58State", "tv_p58Dir", "tv_reactL", "tv_reactS", "tv_ctxDir", "tv_rawTake", "tv_decision"):
        out[c] = np.nan if c.endswith(("open", "high", "low", "close", "atr")) else ""
    out["ohlc_match"] = ""
    out["state_match"] = ""
    out["first_diff_var"] = ""
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = _load_cfg()
    df, focus = _run_sequential_trace(cfg)
    df.to_csv(OUT / "python_trace_1320_1345_chicago.csv", index=False)
    focus.to_csv(OUT / "python_trace_1324_1334_chicago.csv", index=False)
    comparison_template(df).to_csv(OUT / "tv_vs_python_comparison_template.csv", index=False)

    # Key bar summary for report
    key_times = [
        "13:26:00",
        "13:27:00",
        "13:31:00",
        "13:32:00",
        "13:33:00",
        "13:36:00",
        "13:40:00",
        "13:41:00",
    ]
    key_rows = []
    for t in key_times:
        sub = df.loc[df["ts_chicago"].str.contains(f"13:{t[:2]}:{t[3:]}")]
        if len(sub):
            key_rows.append(sub.iloc[0].to_dict())
    summary = {
        "window": f"{WIN_START} – {WIN_END}",
        "bars": len(df),
        "focus_bars": len(focus),
        "short_1326_python": any(
            r.get("rawTake") and r.get("p58Dir") == "SHORT" and "13:26" in str(r.get("ts_chicago", ""))
            for r in key_rows
        ),
        "key_bars": key_rows,
    }
    (OUT / "python_key_bars.json").write_text(json.dumps(summary, indent=2, default=str))

    print("PHASE59E PYTHON TRACE")
    print(f"Bars exported: {len(df)} ({WIN_START.date()} 13:20-13:45 Chicago)")
    print(f"Focus 13:24-13:34: {len(focus)} bars")
    for r in key_rows:
        print(
            f"  {r['ts_chicago']} st={r['p58StateName']} in={r['p58InTrade']} dir={r['p58Dir']} "
            f"dec={r['decision']} reactL/S={r['reactL']}/{r['reactS']} O={r['open']} C={r['close']}"
        )
    print(f"Output: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
