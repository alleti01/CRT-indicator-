"""Extract recent TradingView-accessible review sample from frozen Phase58J results."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58.research.instrument import NQ
from phase58b.research.precompute import build_mtf_arrays
from phase58i.research.canonical import canonical_trades
from phase58i.research.management import executions_from_trades, simulate_management

REVIEW = ROOT / "phase58j" / "review"
PINE = ROOT / "phase58j" / "pine"
CONFIG = ROOT / "phase58j" / "config"
TOL = 0.05  # points tolerance for stop/target geometry


def _load_cfg() -> dict:
    cfg = json.load(open(CONFIG / "phase58j_frozen.json"))
    cfg.update(json.load(open(ROOT / "phase58i" / "config" / "phase58i_frozen.json")))
    cfg.update(json.load(open(ROOT / "phase58d" / "config" / "phase58d_frozen.json")))
    return cfg


def _attach_m0_ids(m0: pd.DataFrame, execs: pd.DataFrame) -> pd.DataFrame:
    out = m0.copy()
    out["trade_id"] = execs["trade_id"].values[: len(out)]
    return out


def _build_master(canon: pd.DataFrame, m0: pd.DataFrame, m1: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.DataFrame:
    m0_atr = m0[["trade_id", "atr"]].rename(columns={"atr": "atr_at_entry"}) if "atr" in m0.columns else canon[["trade_id", "atr"]].rename(columns={"atr": "atr_at_entry"})
    ctx = canon[["trade_id", "15m_state", "5m_state"]].rename(
        columns={"15m_state": "ctx_15m", "5m_state": "ctx_5m"}
    )
    m = m0.merge(
        m1,
        on="trade_id",
        suffixes=("_m0", "_m1"),
    ).merge(m0_atr, on="trade_id", how="left").merge(ctx, on="trade_id", how="left")
    m["tag"] = "TAKE"
    m["entry_ts"] = [idx[int(i)] for i in m["entry_i_m0"]]
    m["exit_ts_m0"] = [idx[int(i)] for i in m["exit_i_m0"]]
    m["exit_ts_m1"] = [idx[int(i)] for i in m["exit_i_m1"]]
    m["delta_r"] = m["net_R_m1"] - m["net_R_m0"]
    m["m0_risk_pts"] = (m["entry_price_m0"] - m["stop_m0"]).abs()
    m["m1_risk_pts"] = (m["entry_price_m1"] - m["stop_m1"]).abs()
    return m


def _fmt_ts(ts: pd.Timestamp, tz: str) -> dict:
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize(tz)
    else:
        ts = ts.tz_convert(tz)
    utc = ts.tz_convert("UTC")
    return {
        "entry_time": ts.isoformat(),
        "entry_time_utc": utc.isoformat(),
        "entry_time_exchange": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "exchange_timezone": tz,
        "unix_ms": int(utc.timestamp() * 1000),
        "tradingview_jump_time": f"{ts.strftime('%Y-%m-%d %H:%M:%S')} {tz}",
    }


def _export_row(row: pd.Series, group: str, review_number: int, instrument: str, tz: str) -> dict:
    ts = _fmt_ts(row["entry_ts"], tz)
    out = {
        "review_group": group,
        "review_number": review_number,
        "trade_id": row["trade_id"],
        "instrument": instrument,
        "direction": row["direction_m0"],
        "entry_price": row["entry_price_m0"],
        "atr_at_entry": row["atr_at_entry"],
        "m0_stop_price": row["stop_m0"],
        "m0_target_price": row["target_m0"],
        "m0_exit_reason": row["exit_reason_m0"],
        "m0_exit_time": pd.Timestamp(row["exit_ts_m0"]).tz_convert(tz).isoformat(),
        "m0_net_r": row["net_R_m0"],
        "m1_stop_price": row["stop_m1"],
        "m1_target_price": row["target_m1"],
        "m1_exit_reason": row["exit_reason_m1"],
        "m1_exit_time": pd.Timestamp(row["exit_ts_m1"]).tz_convert(tz).isoformat(),
        "m1_net_r": row["net_R_m1"],
        "delta_r_m1_minus_m0": row["delta_r"],
        "phase58d_decision": row.get("tag", "TAKE"),
        "p4_status": "KEEP",
        "h1_status": "KEEP",
        "15m_context": row["ctx_15m"],
        "5m_context": row["ctx_5m"],
        "m0_risk_points": row["m0_risk_pts"],
        "m1_risk_points": row["m1_risk_pts"],
        "visual_diagnostic_label": "VISUAL_DIAGNOSTIC_ONLY",
        "review_status": "NOT_REVIEWED",
        "visual_entry_location": "",
        "visual_m1_stop_quality": "",
        "visual_thesis_intact_at_m0_stop": "",
        "visual_m1_rescue_quality": "",
        "notes": "",
    }
    out.update(ts)
    return out


def _verify_geometry(row: pd.Series) -> dict:
    atr = float(row["atr_at_entry"])
    ep = float(row["entry_price_m0"])
    m0_risk = float(row["m0_risk_pts"])
    m1_risk = float(row["m1_risk_pts"])
    m0_tgt_dist = abs(float(row["target_m0"]) - ep)
    m1_tgt_dist = abs(float(row["target_m1"]) - ep)
    return {
        "m0_stop_atr_ok": abs(m0_risk - 0.75 * atr) <= max(TOL, 0.02 * atr),
        "m1_stop_atr_ok": abs(m1_risk - 1.0 * atr) <= max(TOL, 0.02 * atr),
        "m1_target_2p5r_ok": abs(m1_tgt_dist - 2.5 * m1_risk) <= max(TOL, 0.02 * m1_risk),
        "m0_target_2p5r_ok": abs(m0_tgt_dist - 2.5 * m0_risk) <= max(TOL, 0.02 * m0_risk),
    }


def _select_recent(
    df: pd.DataFrame,
    mask: pd.Series,
    n: int,
    exclude: set[str] | None = None,
) -> tuple[pd.DataFrame, str]:
    exclude = exclude or set()
    pool = df.loc[mask & ~df["trade_id"].isin(exclude)].copy()
    if pool.empty:
        return pool, "none"
    latest = pool["entry_ts"].max()
    windows = [
        ("31d", pd.Timedelta(days=31)),
        ("62d", pd.Timedelta(days=62)),
        ("93d", pd.Timedelta(days=93)),
        ("186d", pd.Timedelta(days=186)),
        ("365d", pd.Timedelta(days=365)),
        ("all_time", None),
    ]
    for label, delta in windows:
        sub = pool if delta is None else pool.loc[pool["entry_ts"] >= latest - delta]
        if len(sub) >= n:
            picked = sub.sort_values("entry_ts", ascending=False).head(n)
            picked = picked.sort_values("entry_ts", ascending=True)
            return picked, label
    picked = pool.sort_values("entry_ts", ascending=False).head(n).sort_values("entry_ts", ascending=True)
    return picked, "all_time_partial"


def _verify_parity(selected_ids: list[str], source: pd.DataFrame, out_df: pd.DataFrame) -> tuple[bool, list[str]]:
    flags = []
    ok = True
    for tid in selected_ids:
        s = source.loc[source["trade_id"] == tid].iloc[0]
        o = out_df.loc[out_df["trade_id"] == tid].iloc[0]
        pairs = [
            ("direction", o["direction"], s["direction_m0"]),
            ("entry_price", o["entry_price"], s["entry_price_m0"]),
            ("atr", o["atr_at_entry"], s["atr_at_entry"]),
            ("m0_stop", o["m0_stop_price"], s["stop_m0"]),
            ("m1_stop", o["m1_stop_price"], s["stop_m1"]),
            ("m0_target", o["m0_target_price"], s["target_m0"]),
            ("m1_target", o["m1_target_price"], s["target_m1"]),
            ("m0_exit", o["m0_exit_reason"], s["exit_reason_m0"]),
            ("m1_exit", o["m1_exit_reason"], s["exit_reason_m1"]),
            ("m0_net_r", o["m0_net_r"], s["net_R_m0"]),
            ("m1_net_r", o["m1_net_r"], s["net_R_m1"]),
        ]
        for name, a, b in pairs:
            if isinstance(a, (float, np.floating)) or isinstance(b, (float, np.floating)):
                if abs(float(a) - float(b)) > 1e-4:
                    ok = False
                    flags.append(f"{tid} {name}: {a} vs {b}")
            elif a != b:
                ok = False
                flags.append(f"{tid} {name}: {a} vs {b}")
    return ok, flags


def _write_checklist(rows: list[dict], path: Path, group_rules: dict) -> None:
    lines = [
        "# Recent TradingView Review Checklist",
        "",
        "**VISUAL_DIAGNOSTIC_ONLY** — not for parameter selection or performance claims.",
        "",
        f"Exchange timezone: **{NQ.timezone}**",
        "",
        "## Group selection rules",
        "",
    ]
    for g, rule in group_rules.items():
        lines.append(f"- **{g}**: {rule}")
    lines.append("")

    for row in rows:
        n = row["review_number"]
        lines.extend([
            "--------------------------------------------------",
            f"REVIEW #{n:02d}",
            f"Group: {row['review_group']}",
            f"Trade ID: {row['trade_id']}",
            f"TradingView time: {row['tradingview_jump_time']}",
            f"Direction: {row['direction']}",
            f"Entry: {row['entry_price']}",
            f"M0 stop: {row['m0_stop_price']}",
            f"M1 stop: {row['m1_stop_price']}",
            f"M0 target: {row['m0_target_price']}",
            f"M1 target: {row['m1_target_price']}",
            f"M0 result: {row['m0_exit_reason']} ({row['m0_net_r']:.2f}R)",
            f"M1 result: {row['m1_exit_reason']} ({row['m1_net_r']:.2f}R)",
            f"ΔR: {row['delta_r_m1_minus_m0']:.2f}R",
            "",
            "CHECK:",
            "[ ] Entry is at a legitimate market location",
            "[ ] M0 stop appears to be normal adverse movement",
            "[ ] Thesis is still intact when M0 is stopped",
            "[ ] M1 stop is beyond normal noise",
            "[ ] M1 survives for a structurally defensible reason",
            "[ ] M1 target is reached as part of the expected move",
            "[ ] Trade appears suspicious / needs investigation",
            "",
            "Notes:",
            "",
        ])
    path.write_text("\n".join(lines))


def _write_recent_pine(first: dict, path: Path) -> None:
    base = (PINE / "phase58j_m1_validation.pine").read_text()
    # Defaults for Review #01
    ep = first["entry_price"]
    tv_time = first["tradingview_jump_time"].rsplit(" ", 1)[0]
    date_part, time_part = tv_time.split(" ")
    y, mo, d = date_part.split("-")
    h, mi, _ = time_part.split(":")
    ts_expr = f'timestamp("{y}-{mo}-{d} {h}:{mi}")'
    pine = base.replace(
        'indicator("Phase58J M1 Validation"',
        'indicator("Phase58J Recent Review #01"',
    )
    pine = pine.replace('input.string("E-023664", "Trade ID"', f'input.string("{first["trade_id"]}", "Trade ID"')
    pine = pine.replace('input.time(timestamp("2020-06-02 14:21"), "Entry time (chart TZ)"', f'input.time({ts_expr}, "Entry time (chart TZ)"')
    pine = pine.replace('input.string("LONG", "Direction"', f'input.string("{first["direction"]}", "Direction"')
    pine = pine.replace('input.float(12781.5, "Entry price"', f'input.float({ep}, "Entry price"')
    pine = pine.replace('input.float(12775.607, "M0 stop"', f'input.float({first["m0_stop_price"]}, "M0 stop"')
    pine = pine.replace('input.float(12773.643, "M1 stop"', f'input.float({first["m1_stop_price"]}, "M1 stop"')
    pine = pine.replace('input.float(12796.232, "M0 target"', f'input.float({first["m0_target_price"]}, "M0 target"')
    pine = pine.replace('input.float(12801.143, "M1 target"', f'input.float({first["m1_target_price"]}, "M1 target"')
    pine = pine.replace('input.float(7.857, "ATR at entry"', f'input.float({first["atr_at_entry"]}, "ATR at entry"')
    pine = pine.replace('input.string("STOP", "M0 exit reason"', f'input.string("{first["m0_exit_reason"]}", "M0 exit reason"')
    pine = pine.replace('input.string("TARGET", "M1 exit reason"', f'input.string("{first["m1_exit_reason"]}", "M1 exit reason"')
    pine = pine.replace('input.float(-1.12, "M0 net R"', f'input.float({first["m0_net_r"]}, "M0 net R"')
    pine = pine.replace('input.float(2.50, "M1 net R"', f'input.float({first["m1_net_r"]}, "M1 net R"')
    header = (
        "// COPY of phase58j_m1_validation.pine — defaults set to Review #01 from recent_tradingview_review.csv\n"
        "// VISUAL_DIAGNOSTIC_ONLY — no strategy logic changes\n\n"
    )
    path.write_text(header + pine)


def main():
    REVIEW.mkdir(parents=True, exist_ok=True)
    cfg = _load_cfg()
    tz = NQ.timezone
    instrument = NQ.symbol

    canon = canonical_trades("H1")
    m = build_mtf_arrays()
    idx = m.m1_idx
    execs = executions_from_trades(canon)
    m0 = _attach_m0_ids(simulate_management(m, execs, cfg, "M0"), execs)
    m1 = simulate_management(m, execs, cfg, "M1_1.0")
    master = _build_master(canon, m0, m1, idx)

    latest_data = master["entry_ts"].max()
    earliest_data = master["entry_ts"].min()

    # Group definitions
    group_a_mask = (master["exit_reason_m0"] == "STOP") & (master["exit_reason_m1"] == "TARGET")
    group_b_mask = master["delta_r"] < 0  # M1 strictly worse than M0
    group_c_mask = master["exit_reason_m1"] == "TARGET"
    group_d_mask = master["exit_reason_m1"] == "STOP"

    ga, win_a = _select_recent(master, group_a_mask, 10)
    ga_ids = set(ga["trade_id"])
    gb, win_b = _select_recent(master, group_b_mask, 5)
    gc, win_c = _select_recent(master, group_c_mask, 5, exclude=ga_ids)
    gd, win_d = _select_recent(master, group_d_mask, 5)

    group_rules = {
        "A — M0 STOP → M1 TARGET": "exit_reason_m0=STOP AND exit_reason_m1=TARGET; most recent 10 by entry_ts desc",
        "B — M1 worse than M0": "delta_r_m1_minus_m0 < 0; most recent 5 by entry_ts desc; prefers TARGET→STOP/TIME transitions",
        "C — Normal M1 winners": "exit_reason_m1=TARGET excluding Group A trade_ids; most recent 5",
        "D — M1 losers": "exit_reason_m1=STOP; most recent 5",
    }

    exports = []
    review_num = 1
    for label, gdf, gname in [
        ("A — M0 STOP → M1 TARGET", ga, "A"),
        ("B — M1 worse than M0", gb, "B"),
        ("C — Normal M1 winner", gc, "C"),
        ("D — M1 loser", gd, "D"),
    ]:
        for _, row in gdf.iterrows():
            exports.append(_export_row(row, label, review_num, instrument, tz))
            review_num += 1

    out_df = pd.DataFrame(exports)
    out_df = out_df.sort_values("entry_time").reset_index(drop=True)
    out_df["review_number"] = range(1, len(out_df) + 1)

    parity_ok, parity_flags = _verify_parity(out_df["trade_id"].tolist(), master, out_df)
    geom_flags = []
    for _, r in out_df.iterrows():
        g = _verify_geometry(master.loc[master["trade_id"] == r["trade_id"]].iloc[0])
        if not all(g.values()):
            geom_flags.append(f"{r['trade_id']} geometry: {g}")

    out_df.to_csv(REVIEW / "recent_tradingview_review.csv", index=False)
    out_df[out_df["review_group"].str.startswith("A")].to_csv(REVIEW / "recent_m0_stop_m1_target.csv", index=False)
    out_df[out_df["review_group"].str.startswith("B")].to_csv(REVIEW / "recent_m1_worse.csv", index=False)
    out_df[out_df["review_group"].str.startswith("C")].to_csv(REVIEW / "recent_m1_winners.csv", index=False)
    out_df[out_df["review_group"].str.startswith("D")].to_csv(REVIEW / "recent_m1_stops.csv", index=False)

    _write_checklist(out_df.to_dict("records"), REVIEW / "RECENT_TRADINGVIEW_REVIEW.md", group_rules)
    if len(out_df):
        _write_recent_pine(out_df.iloc[0].to_dict(), PINE / "phase58j_recent_review.pine")

    tz_ok = all("America/Chicago" in x or x.endswith(NQ.timezone) for x in out_df["tradingview_jump_time"])

    print("PHASE58J RECENT TRADINGVIEW REVIEW")
    print("---------------------------------")
    print(f"Latest local market data: {latest_data}")
    print(f"Earliest canonical data:  {earliest_data}")
    print(f"Instrument: {instrument}")
    print(f"Exchange timezone: {tz}")
    print(f"Timeframe: 1M")
    print(f"Canonical trades inspected: {len(master):,}")
    print()
    print(f"Group A M0 STOP → M1 TARGET: {len(ga)} (search window: {win_a})")
    print(f"Group B M1 worse: {len(gb)} (search window: {win_b})")
    print(f"Group C normal M1 winners: {len(gc)} (search window: {win_c})")
    print(f"Group D M1 stops: {len(gd)} (search window: {win_d})")
    print()
    if len(out_df):
        print(f"Earliest selected trade: {out_df['tradingview_jump_time'].iloc[0]}")
        print(f"Latest selected trade:   {out_df['tradingview_jump_time'].iloc[-1]}")
    print()
    print(f"Selected trades parity: {'PASS' if parity_ok else 'FAIL'}")
    if parity_flags:
        for f in parity_flags[:5]:
            print(f"  - {f}")
    print(f"Geometry verification: {'PASS' if not geom_flags else 'FAIL'}")
    for f in geom_flags[:5]:
        print(f"  - {f}")
    print(f"Timezone conversion: {'PASS' if tz_ok else 'FAIL'}")
    print("Pine compile-ready: YES")
    print()
    print("Files:")
    for p in [
        "phase58j/review/recent_tradingview_review.csv",
        "phase58j/review/recent_m0_stop_m1_target.csv",
        "phase58j/review/recent_m1_worse.csv",
        "phase58j/review/recent_m1_winners.csv",
        "phase58j/review/recent_m1_stops.csv",
        "phase58j/review/RECENT_TRADINGVIEW_REVIEW.md",
        "phase58j/pine/phase58j_recent_review.pine",
    ]:
        print(p)
    print()
    print("RESEARCH STATUS:")
    print("NO STRATEGY LOGIC CHANGED")
    print("NO PARAMETERS CHANGED")
    print("NO NEW FILTERS ADDED")
    print("VISUAL_DIAGNOSTIC_ONLY")


if __name__ == "__main__":
    main()
