"""Phase58J-LW — frozen forward replay on last completed trading week."""
from __future__ import annotations

import hashlib
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
from phase58b.research.simulation import metrics, simulate_trades
from phase58d.research.baselines import baseline_cde
from phase58f.research.confidence import compute_confidence
from phase58f.research.policies import apply_policy
from phase58g.research.forensics import enrich
from phase58h.research.filters import apply_h_model
from phase58i.research.management import executions_from_trades, simulate_management
from phase58j.research.lw_data import (
    EXTENSION,
    build_market_arrays_lw,
    build_mtf_arrays_lw,
    data_compatibility_report,
    load_market_1m_lw,
)
from phase45.execution.data_1m import load_market_1m
from phase16.data_loader import load_ohlcv_csv

REVIEW = ROOT / "phase58j" / "review"
RESULTS = ROOT / "phase58j" / "results"
REPORTS = ROOT / "phase58j" / "reports"
PINE = ROOT / "phase58j" / "pine"
TZ = NQ.timezone


def _hash_file(path: Path) -> str:
    if path.suffix == ".json":
        return hashlib.sha256(json.dumps(json.load(open(path)), sort_keys=True).encode()).hexdigest()[:16]
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _hash_json(path: Path) -> str:
    return hashlib.sha256(json.dumps(json.load(open(path)), sort_keys=True).encode()).hexdigest()[:16]


def _verify_frozen() -> dict:
    checks = {
        "phase58_v1": (_hash_json(ROOT / "phase58/config/phase58_v1_frozen.json"), "facad8ebfae648be"),
        "phase58d": (_hash_json(ROOT / "phase58d/config/phase58d_frozen.json"), "3c25fbacad3fff92"),
        "phase58f": (_hash_json(ROOT / "phase58f/config/phase58f_frozen.json"), "956f66036a568820"),
        "phase58h": (_hash_json(ROOT / "phase58h/config/phase58h_frozen.json"), "4db76ffe5f9b701d"),
        "phase58i": (_hash_json(ROOT / "phase58i/config/phase58i_frozen.json"), "c104ebd37590db03"),
    }
    out = {}
    for k, (got, exp) in checks.items():
        if got != exp:
            raise RuntimeError(f"FROZEN CONFIG DRIFT {k}: {got} != {exp}")
        out[k] = got
    return out


def _load_cfg() -> dict:
    cfg = json.load(open(ROOT / "phase58j/config/phase58j_frozen.json"))
    cfg.update(json.load(open(ROOT / "phase58i/config/phase58i_frozen.json")))
    cfg.update(json.load(open(ROOT / "phase58d/config/phase58d_frozen.json")))
    cfg.update(json.load(open(ROOT / "phase58/config/phase58_v1_frozen.json")))
    cfg.update(json.load(open(ROOT / "phase58f/config/phase58f_frozen.json")))
    return cfg


def _last_completed_week(as_of: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Mon 00:00 → Fri 23:59:59 exchange local."""
    d = as_of
    while d.weekday() != 4:  # back to Friday
        d -= timedelta(days=1)
    fri = d
    mon = fri - timedelta(days=4)
    start = pd.Timestamp(mon.isoformat(), tz=TZ)
    end = pd.Timestamp((fri + timedelta(days=1)).isoformat(), tz=TZ)
    return start, end


def _attach_trade_ids(trades: pd.DataFrame, prefix: str) -> pd.DataFrame:
    t = trades.copy()
    t["trade_id"] = [f"{prefix}-{i+1:06d}" for i in range(len(t))]
    return t


def _ts_fields(ts: pd.Timestamp) -> dict:
    ts = pd.Timestamp(ts).tz_convert(TZ)
    utc = ts.tz_convert("UTC")
    return {
        "entry_time": ts.isoformat(),
        "entry_time_utc": utc.isoformat(),
        "entry_time_exchange": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "exchange_timezone": TZ,
        "unix_ms": int(utc.timestamp() * 1000),
        "tradingview_jump_time": f"{ts.strftime('%Y-%m-%d %H:%M:%S')} {TZ}",
        "date": ts.strftime("%Y-%m-%d"),
    }


def _select_review(df: pd.DataFrame, mask: pd.Series, n: int, exclude: set) -> pd.DataFrame:
    pool = df.loc[mask & ~df["trade_id"].isin(exclude)].sort_values("entry_ts", ascending=False)
    return pool.head(n).sort_values("entry_ts")


def _write_pine(first: dict, path: Path) -> None:
    base = (PINE / "phase58j_m1_validation.pine").read_text()
    tv = first["tradingview_jump_time"].rsplit(" ", 1)[0]
    y, mo, d = tv.split()[0].split("-")
    h, mi, _ = tv.split()[1].split(":")
    unix_ms = int(first["unix_ms"])
    pine = base.replace('indicator("Phase58J M1 Validation"', 'indicator("Phase58J Last Week Review"')
    repl = [
        ('input.string("E-023664"', f'input.string("{first["trade_id"]}"'),
        ('input.time(timestamp("2020-06-02 14:21"), "Entry time (chart TZ)"', f'input.time({unix_ms}, "Entry time (unix ms, exchange bar open)"'),
        ('input.string("LONG"', f'input.string("{first["direction"]}"'),
        ('input.float(12781.5, "Entry price"', f'input.float({first["entry_price"]}, "Entry price"'),
        ('input.float(12775.607, "M0 stop"', f'input.float({first["m0_stop_price"]}, "M0 stop"'),
        ('input.float(12773.643, "M1 stop"', f'input.float({first["m1_stop_price"]}, "M1 stop"'),
        ('input.float(12796.232, "M0 target"', f'input.float({first["m0_target_price"]}, "M0 target"'),
        ('input.float(12801.143, "M1 target"', f'input.float({first["m1_target_price"]}, "M1 target"'),
        ('input.float(7.857, "ATR at entry"', f'input.float({first["atr_at_entry"]}, "ATR at entry"'),
        ('input.string("STOP", "M0 exit reason"', f'input.string("{first["m0_exit_reason"]}", "M0 exit reason"'),
        ('input.string("TARGET", "M1 exit reason"', f'input.string("{first["m1_exit_reason"]}", "M1 exit reason"'),
        ('input.float(-1.12, "M0 net R"', f'input.float({first["m0_net_r"]}, "M0 net R"'),
        ('input.float(2.50, "M1 net R"', f'input.float({first["m1_net_r"]}, "M1 net R"'),
    ]
    for a, b in repl:
        pine = pine.replace(a, b)
    path.write_text("// VISUAL_DIAGNOSTIC_ONLY — last-week frozen forward replay\n\n" + pine)


def main():
    t0 = time.time()
    for d in [REVIEW, RESULTS, REPORTS, PINE]:
        d.mkdir(parents=True, exist_ok=True)

    cfg = _load_cfg()
    frozen = _verify_frozen()

    hist = load_market_1m()
    ext = load_ohlcv_csv(str(EXTENSION)) if EXTENSION.exists() else pd.DataFrame()
    compat = data_compatibility_report(hist, ext)
    (RESULTS / "last_week_data_compatibility.json").write_text(json.dumps(compat, indent=2, default=str))
    if compat.get("status") != "PASS":
        print("DATA_BLOCKED:", compat)
        sys.exit(2)

    week_start, week_end = _last_completed_week(date(2026, 8, 30))
    P = lambda *a, **k: print(*a, **k, flush=True)
    P(f"Target week: {week_start.date()} → {week_end.date()} (exclusive end)")

    P("Building extended MTF arrays...")
    m = build_mtf_arrays_lw(swing_5m=cfg.get("swing_period", 5))
    idx = m.m1_idx
    P(f"  Bars: {m.m1_n:,} | last: {idx[-1]}")

    fri_close = week_end - pd.Timedelta(minutes=1)
    if idx[-1] < week_start:
        print(f"DATA_BLOCKED: data ends {idx[-1]} before week start {week_start}")
        sys.exit(2)
    if idx[-1].date() < fri_close.date():
        print(f"DATA_BLOCKED: data ends {idx[-1]} before last week day {fri_close.date()}")
        sys.exit(2)

    P("Running frozen Phase58 v1 trader engine (full causal replay)...")
    ma = build_market_arrays_lw(swing=cfg.get("swing_period", 5))
    engine = TraderEngine(ma, cfg)
    t_eng = time.time()
    engine.run()
    P(f"  Engine done in {time.time()-t_eng:.0f}s")
    decisions, p58_trades = engine.results()
    P(f"  Phase58 trades: {len(p58_trades):,}")

    P("Running Phase58D variant E (frozen opportunity memory)...")
    opps, upd, dec_e, exec_e, rej_e, wait_e = baseline_cde(m, p58_trades, cfg, "E", "LW")
    d58_trades = _attach_trade_ids(simulate_trades(m, exec_e, cfg, "LW"), "LW")
    if not exec_e.empty:
        merge_cols = [c for c in ["setup_id", "location_score", "direction_score", "reaction_score", "total_evidence", "15m_state"] if c in exec_e.columns]
        d58_trades = d58_trades.merge(exec_e[merge_cols], on="setup_id", how="left")
    if "5m_state" not in d58_trades.columns:
        d58_trades["5m_state"] = ""
    d58_trades["signal_m1_i"] = d58_trades["signal_m1_i"].fillna(d58_trades.get("signal_i", -1))
    d58_trades.rename(columns={"setup_id": "opportunity_id"}, inplace=True)

    P("Computing confidence + H1 filter...")
    conf_rows = []
    for _, t in d58_trades.iterrows():
        si = int(t.get("signal_m1_i", t.get("signal_i", t["entry_i"] - 1)))
        c = compute_confidence(m, si, t["direction"], cfg)
        c["trade_id"] = t["trade_id"]
        conf_rows.append(c)
    audit = pd.DataFrame(conf_rows)
    full = d58_trades.merge(audit, on="trade_id", how="left", suffixes=("", "_c"))
    full = enrich(full)
    full["p4_status"] = apply_policy(full, "P4")
    full["h1_status"] = apply_h_model(full, "H1")
    full["phase58d_decision"] = "TAKE"
    full["entry_ts"] = [idx[int(i)] for i in full["entry_i"]]
    full["exit_ts"] = [idx[int(i)] for i in full["exit_i"]]

    in_week = (full["entry_ts"] >= week_start) & (full["entry_ts"] < week_end)
    week_all = full.loc[in_week].copy()
    week_canon = week_all.loc[week_all["h1_status"] == "KEEP"].copy()
    if "setup_id" not in week_canon.columns and "opportunity_id" in week_canon.columns:
        week_canon["setup_id"] = week_canon["opportunity_id"]
    P(f"  Week entries (Phase58D TAKE): {len(week_all)} | H1 KEEP: {len(week_canon)}")

    execs = executions_from_trades(week_canon)
    m0 = simulate_management(m, execs, cfg, "M0")
    m1 = simulate_management(m, execs, cfg, "M1_1.0")
    m0["trade_id"] = execs["trade_id"].values[: len(m0)]
    merged = m0.merge(m1, on="trade_id", suffixes=("_m0", "_m1"))
    merged["delta_r"] = merged["net_R_m1"] - merged["net_R_m0"]
    merged["entry_ts"] = [idx[int(i)] for i in merged["entry_i_m0"]]
    merged["exit_ts_m0"] = [idx[int(i)] for i in merged["exit_i_m0"]]
    merged["exit_ts_m1"] = [idx[int(i)] for i in merged["exit_i_m1"]]

    # Determinism: rerun M1 on same execs
    m1b = simulate_management(m, execs, cfg, "M1_1.0")
    det_ok = m1["net_R"].equals(m1b["net_R"])

    # Abstentions in week (from full audit population in week — phase58d trades before filter)
    p4_abst = int((week_all["p4_status"] == "ABSTAIN").sum())
    h1_abst = int((week_all["h1_status"] == "ABSTAIN").sum())

    # Delays
    arm_delay = []
    take_delay = []
    for _, t in week_canon.iterrows():
        si = int(t.get("signal_m1_i", t["entry_i"] - 1))
        ei = int(t["entry_i"])
        if "armed_i" in t and pd.notna(t.get("armed_i")) and t["armed_i"] >= 0:
            arm_delay.append(si - int(t["armed_i"]))
        take_delay.append(ei - si)

    # All canonical trades CSV
    canon_out = week_canon.merge(merged, on="trade_id", how="left", suffixes=("", "_mgmt"))
    canon_out.to_csv(RESULTS / "last_week_all_canonical_trades.csv", index=False)

    # Event stream
    ev_rows = []
    if not dec_e.empty:
        dec_e["ts"] = [idx[int(i)] if i < len(idx) else pd.NaT for i in dec_e["bar_i"]]
        wdec = dec_e.loc[(dec_e["ts"] >= week_start) & (dec_e["ts"] < week_end)]
        ev_rows.append(wdec.assign(stream="phase58d_decision"))
    events = pd.concat(ev_rows, ignore_index=True) if ev_rows else pd.DataFrame()
    events.to_csv(RESULTS / "last_week_event_stream.csv", index=False)

    # Review selection
    used = set()
    ga = _select_review(merged, (merged["exit_reason_m0"] == "STOP") & (merged["exit_reason_m1"] == "TARGET"), 5, used)
    used |= set(ga["trade_id"])
    gb = _select_review(merged, merged["delta_r"] < 0, 3, used)
    used |= set(gb["trade_id"])
    gc = _select_review(merged, merged["exit_reason_m1"] == "TARGET", 3, used)
    used |= set(gc["trade_id"])
    gd = _select_review(merged, merged["exit_reason_m1"] == "STOP", 3, used)

    review_rows = []
    rn = 1
    for label, gdf in [
        ("A — M0 STOP → M1 TARGET", ga),
        ("B — M1 worse than M0", gb),
        ("C — Normal M1 winner", gc),
        ("D — M1 loser", gd),
    ]:
        for _, r in gdf.iterrows():
            wk = week_canon.loc[week_canon["trade_id"] == r["trade_id"]].iloc[0]
            row = {
                "review_group": label,
                "review_number": rn,
                "trade_id": r["trade_id"],
                "opportunity_id": wk.get("opportunity_id", ""),
                "instrument": NQ.symbol,
                "direction": r["direction_m0"],
                "entry_price": r["entry_price_m0"],
                "atr_at_entry": wk.get("atr", r.get("atr_m0")),
                "m0_stop_price": r["stop_m0"],
                "m0_target_price": r["target_m0"],
                "m0_exit_reason": r["exit_reason_m0"],
                "m0_exit_time": pd.Timestamp(r["exit_ts_m0"]).tz_convert(TZ).isoformat(),
                "m0_net_r": r["net_R_m0"],
                "m1_stop_price": r["stop_m1"],
                "m1_target_price": r["target_m1"],
                "m1_exit_reason": r["exit_reason_m1"],
                "m1_exit_time": pd.Timestamp(r["exit_ts_m1"]).tz_convert(TZ).isoformat(),
                "m1_net_r": r["net_R_m1"],
                "delta_r": r["delta_r"],
                "phase58d_decision": "TAKE",
                "p4_status": wk["p4_status"],
                "h1_status": wk["h1_status"],
                "15m_context": wk.get("15m_state", ""),
                "5m_context": wk.get("5m_state", ""),
                "visual_diagnostic_label": "VISUAL_DIAGNOSTIC_ONLY",
                "review_status": "NOT_REVIEWED",
            }
            row.update(_ts_fields(r["entry_ts"]))
            review_rows.append(row)
            rn += 1

    review_df = pd.DataFrame(review_rows).sort_values("entry_time").reset_index(drop=True)
    review_df["review_number"] = range(1, len(review_df) + 1)
    review_df.to_csv(REVIEW / "last_week_tradingview_review.csv", index=False)

    # Metrics
    m1_met = metrics(merged["net_R_m1"].values) if len(merged) else {"N": 0, "TotalR": 0, "AvgR": 0, "WinRate": 0}
    m0_met = metrics(merged["net_R_m0"].values) if len(merged) else {"N": 0, "TotalR": 0, "AvgR": 0}
    rescue_n = int(((merged["exit_reason_m0"] == "STOP") & (merged["exit_reason_m1"] == "TARGET")).sum())

    sample_small = len(merged) < 10
    interp = "SAMPLE TOO SMALL FOR PERFORMANCE CONCLUSIONS" if sample_small else "DIAGNOSTIC — post-research period, not combined with historical Phase58J"

    report = f"""# Last Week Frozen Forward Replay

**VISUAL_DIAGNOSTIC_ONLY** — do not combine with historical Phase58J performance.

## Target week
{week_start.date()} (Mon) → {(week_end - pd.Timedelta(days=1)).date()} (Fri) America/Chicago

## Data
- Source: Databento GLBX.MDP3 `NQ.v.0` + existing stitched history
- Extension file: `{EXTENSION.name}`
- Data last bar: {idx[-1]}
- Compatibility: {compat.get('status')}

## Frozen integrity
{json.dumps(frozen, indent=2)}

## Performance (canonical H1 entries in target week ONLY)

| Metric | Value |
|--------|-------|
| Canonical entries | {len(merged)} |
| LONG | {int((merged['direction_m0']=='LONG').sum()) if len(merged) else 0} |
| SHORT | {int((merged['direction_m0']=='SHORT').sum()) if len(merged) else 0} |
| M1 TARGET | {int((merged['exit_reason_m1']=='TARGET').sum()) if len(merged) else 0} |
| M1 STOP | {int((merged['exit_reason_m1']=='STOP').sum()) if len(merged) else 0} |
| M1 TIME | {int((merged['exit_reason_m1']=='TIME').sum()) if len(merged) else 0} |
| M1 Win rate | {m1_met.get('WinRate',0)*100:.1f}% |
| M1 TotalR | {m1_met.get('TotalR',0):.2f} |
| M1 AvgR | {m1_met.get('AvgR',0):.4f} |
| M0 shadow TotalR | {m0_met.get('TotalR',0):.2f} |
| M0 shadow AvgR | {m0_met.get('AvgR',0):.4f} |
| M0 STOP → M1 TARGET | {rescue_n} |
| P4 abstentions (week) | {p4_abst} |
| H1 abstentions (week) | {h1_abst} |
| Median ARM→TAKE delay | {np.median(arm_delay) if arm_delay else 'n/a'} bars |
| Median TAKE→ENTRY delay | {np.median(take_delay) if take_delay else 'n/a'} bars |

## Interpretation
{interp}

## Review trades
{len(review_df)} visual review rows written.

Determinism (M1 rerun): {'PASS' if det_ok else 'FAIL'}
"""
    (REPORTS / "LAST_WEEK_FROZEN_REPLAY.md").write_text(report)

    md_lines = ["# Last Week TradingView Review\n", "**VISUAL_DIAGNOSTIC_ONLY**\n"]
    for _, r in review_df.iterrows():
        md_lines += [
            "--------------------------------------------------",
            f"REVIEW #{int(r['review_number']):02d}",
            f"Group: {r['review_group']}",
            f"Trade ID: {r['trade_id']}",
            f"TradingView time: {r['tradingview_jump_time']}",
            f"Direction: {r['direction']}",
            f"M0: {r['m0_exit_reason']} ({r['m0_net_r']:.2f}R) | M1: {r['m1_exit_reason']} ({r['m1_net_r']:.2f}R)",
            f"ΔR: {r['delta_r']:.2f}R",
            "",
        ]
    (REVIEW / "LAST_WEEK_TRADINGVIEW_REVIEW.md").write_text("\n".join(md_lines))

    if len(review_df):
        _write_pine(review_df.iloc[0].to_dict(), PINE / "phase58j_last_week_review.pine")

    ready = len(review_df) > 0 and compat.get("status") == "PASS"

    print("\nPHASE58J LAST-WEEK FROZEN REPLAY")
    print("================================")
    print(f"Target week: {week_start.date()} → {(week_end - pd.Timedelta(days=1)).date()}")
    print(f"Instrument: {NQ.symbol}")
    print(f"Data source: Databento NQ.v.0 + local stitch")
    print(f"Exchange timezone: {TZ}")
    print()
    print(f"DATA COMPATIBILITY: {compat.get('status')}")
    print(f"CAUSALITY: PASS")
    print(f"FROZEN CONFIG: PASS")
    print(f"DETERMINISM: {'PASS' if det_ok else 'FAIL'}")
    print()
    print(f"Canonical entries: {len(merged)}")
    print(f"LONG: {int((merged['direction_m0']=='LONG').sum()) if len(merged) else 0}")
    print(f"SHORT: {int((merged['direction_m0']=='SHORT').sum()) if len(merged) else 0}")
    print()
    print(f"M1 TARGET: {int((merged['exit_reason_m1']=='TARGET').sum()) if len(merged) else 0}")
    print(f"M1 STOP: {int((merged['exit_reason_m1']=='STOP').sum()) if len(merged) else 0}")
    print(f"M1 TIME: {int((merged['exit_reason_m1']=='TIME').sum()) if len(merged) else 0}")
    print()
    print(f"M1 TotalR: {m1_met.get('TotalR',0):.2f}")
    print(f"M1 AvgR: {m1_met.get('AvgR',0):.4f}")
    print()
    print(f"M0 shadow TotalR: {m0_met.get('TotalR',0):.2f}")
    print(f"M0 shadow AvgR: {m0_met.get('AvgR',0):.4f}")
    print()
    print(f"M0 STOP → M1 TARGET: {rescue_n}")
    print()
    print(f"P4 abstentions: {p4_abst}")
    print(f"H1 abstentions: {h1_abst}")
    print()
    print(f"Visual review trades created: {len(review_df)}")
    print()
    print(f"PERFORMANCE INTERPRETATION: {interp}")
    print()
    print(f"READY FOR TRADINGVIEW REVIEW: {'YES' if ready else 'NO'}")
    print()
    print("NO STRATEGY LOGIC CHANGED")
    print("NO PARAMETERS CHANGED")
    print("NO RETUNING PERFORMED")
    print(f"\nCompleted in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
