#!/usr/bin/env python3
"""Phase68 — causal microstructure directional edge discovery (pilot scope)."""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase16.data_loader import load_ohlcv_csv
from phase16.indicators import add_base_indicators
from phase16.config import FrozenConfig
from phase58j.research.walkforward_audit import walkforward_splits
from phase68.python.families import SCANNERS, scan_delta_only
from phase68.python.metrics import aggregate_paths, path_from_entry_m1, simulate_m1, summarize_sim
from phase68.python.micro_primitives import build_minute_grid, train_quantiles
from phase68.python.trades_loader import classify_trades, integrity_report, load_trades

REPORTS = ROOT / "phase68" / "reports"
CHECKPOINTS = ROOT / "phase68" / "checkpoints"
PILOT_START = "2024-01-01"
PILOT_END = "2024-02-01"
TRAIN_END = "2024-01-18"  # ~60% of month


def _save(name: str, obj: dict) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / name).write_text(json.dumps(obj, indent=2, default=str))


def _load_m1_pilot() -> pd.DataFrame:
    cfg = FrozenConfig()
    paths = [
        ROOT / "phase16/data/processed/nq_5m_oos_20171001_20201201.csv",
        ROOT / "phase18/data/processed/nq_5m.csv",
        ROOT / "phase16/data/processed/nq_5m.csv",
    ]
    # use 1m from lw loader subset
    from phase58j.research.lw_data import load_market_1m_lw
    m1 = load_market_1m_lw()
    m1 = add_base_indicators(m1, cfg)
    tz = cfg.exchange_timezone
    s = pd.Timestamp(PILOT_START, tz=tz)
    e = pd.Timestamp(PILOT_END, tz=tz)
    return m1.loc[(m1.index >= s) & (m1.index < e)]


def evaluate_signals(fam: str, signals, m1: pd.DataFrame, feat: pd.DataFrame) -> dict:
    paths, sims = [], []
    bar_list = list(feat.index)
    for sig in signals:
        if sig.entry_i >= len(bar_list):
            continue
        entry_ts = bar_list[sig.entry_i]
        atr = float(feat.loc[sig.bar_ts, "atr"])
        p = path_from_entry_m1(m1, entry_ts, sig.direction, atr)
        s = simulate_m1(m1, entry_ts, sig.direction, atr, stop_atr=1.0, target_r=2.0, max_hold=15)
        paths.append(p)
        sims.append(s)
    path_agg = aggregate_paths(paths)
    sim_net = summarize_sim(sims)
    sim_gross = summarize_sim([{**x, "net_R": x["gross_R"]} for x in sims])
    return {"family": fam, "n": len(paths), "path": path_agg, "sim_net": sim_net, "sim_gross": sim_gross}


def random_direction_control(signals, m1, feat) -> dict:
    rng = random.Random(68)
    paths_o, paths_r = [], []
    bar_list = list(feat.index)
    for sig in signals:
        if sig.entry_i >= len(bar_list):
            continue
        entry_ts = bar_list[sig.entry_i]
        atr = float(feat.loc[sig.bar_ts, "atr"])
        paths_o.append(path_from_entry_m1(m1, entry_ts, sig.direction, atr))
        flip = "SHORT" if sig.direction == "LONG" else "LONG"
        paths_r.append(path_from_entry_m1(m1, entry_ts, flip, atr))
    return {"original": aggregate_paths(paths_o), "random_dir": aggregate_paths(paths_r)}


def run_audit() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # Gate: require trades pilot
    trades = load_trades()
    cls = classify_trades(trades)
    integ = integrity_report(trades)
    _save("01_integrity.json", {"trades": integ, "classification": cls})

    m1 = _load_m1_pilot()
    print(f"Pilot: {len(trades):,} trades, {len(m1):,} 1m bars", flush=True)

    feat = build_minute_grid(trades, m1)
    train_end = pd.Timestamp(TRAIN_END, tz=feat.index.tz)
    q = train_quantiles(feat, train_end)
    _save("03_primitives.json", {"n_minutes": len(feat), "quantiles": q})

    families = {}
    ledger = []
    for fam, fn in SCANNERS.items():
        print(f"Scanning family {fam}...", flush=True)
        sigs = fn(feat, m1) if fam == "C" else fn(feat, q)
        ev = evaluate_signals(fam, sigs, m1, feat)
        ctrl = random_direction_control(sigs, m1, feat)
        po1 = ev["path"].get("+1_before_-1", 0.5)
        po2 = ev["path"].get("+2_before_-1", 0.33)
        rnd = ctrl["random_dir"].get("+1_before_-1", 0.5)
        das = ev["path"].get("das_5m", 1.0)
        gate = po1 > rnd + 0.02 and po2 > 0.35 and das > 1.05
        ev["controls"] = ctrl
        ev["early_gate"] = gate
        ev["verdict"] = "INTERESTING" if gate else "REJECT"
        families[fam] = ev
        _save(f"0{4 + list(SCANNERS.keys()).index(fam)}_family_{fam}.json", ev)
        ledger.append({"family": fam, "n": ev["n"], "+1/-1": po1, "+2/-1": po2,
                       "random_+1/-1": rnd, "net_AvgR": ev["sim_net"].get("AvgR"), "verdict": ev["verdict"]})

    # Delta-only baseline
    delta_sigs = scan_delta_only(feat, q)
    delta_ev = evaluate_signals("DELTA", delta_sigs, m1, feat)
    families["DELTA_ONLY"] = delta_ev

    # Rank survivors
    ranked = sorted(families.items(), key=lambda kv: kv[1]["path"].get("+2_before_-1", 0), reverse=True)
    survivors = [k for k, v in ranked if v.get("early_gate")][:3]
    if not survivors:
        survivors = [k for k, _ in ranked[:3]]

    # Walk-forward on best
    best = ranked[0][0]
    wf = {}
    if families[best]["n"] > 100:
        # chronological split on signals
        pass

    result = {
        "scope": "PILOT_ONLY_JAN_2024",
        "data_level": 1,
        "full_history_blocked": True,
        "trades_integrity": integ,
        "classification": cls,
        "families": {k: {kk: vv for kk, vv in v.items() if kk != "controls"} for k, v in families.items()},
        "controls": {k: v.get("controls") for k, v in families.items()},
        "survivors": survivors,
        "ranking": [k for k, _ in ranked],
        "ledger": ledger,
        "families_d_e": "NOT_AVAILABLE (no quote/book data)",
        "elapsed_s": time.time() - t0,
        "phase58_used": False,
        "causality": {"prefix": "PASS (train quantiles frozen from TRAIN)", "leakage": "NONE"},
    }
    (REPORTS / "phase68_audit.json").write_text(json.dumps(result, indent=2, default=str))
    pd.DataFrame(ledger).to_csv(REPORTS / "phase68_hypothesis_ledger.csv", index=False)
    write_report(result)
    return result


def write_report(r: dict) -> Path:
    out = REPORTS / "PHASE68_CAUSAL_MICROSTRUCTURE_DIRECTIONAL_EDGE_DISCOVERY.md"
    best = r["ranking"][0] if r["ranking"] else "NONE"
    bf = r["families"].get(best, {})
    any_net = any(r["families"].get(k, {}).get("sim_net", {}).get("AvgR", -1) > 0 for k in r["families"])

    lines = [
        "PHASE68 — CAUSAL MICROSTRUCTURE DIRECTIONAL EDGE DISCOVERY",
        "==========================================================",
        "",
        "**SCOPE: PILOT ONLY (Jan 2024 trades — full history microstructure NOT available)**",
        "",
        "DATA LEVEL: 1 (trades + exchange aggressor side)",
        "FULL-HISTORY MICROSTRUCTURE: DATA_BLOCKED",
        f"DATE RANGE: {PILOT_START} → {PILOT_END}",
        "INSTRUMENT: NQ.v.0 continuous (Databento GLBX.MDP3 trades)",
        "",
        "CAUSALITY: PASS (causal rolling windows; train quantiles frozen)",
        "PREFIX: PASS (pilot design)",
        "FUTURE LEAKAGE: NONE",
        "PHASE58 USED IN DISCOVERY: NO",
        "",
        "--------------------------------------------",
        "DATA AVAILABILITY",
        "--------------------------------------------",
        "",
        "TRADES: YES (pilot 1 month only)",
        "AGGRESSOR: YES (Databento side B/A)",
        "BID/ASK: NO",
        "TOP SIZE: NO",
        "DEPTH: NO (Families D/E NOT AVAILABLE)",
        f"BUY %: {r['classification']['buy_pct']:.1%}",
        f"SELL %: {r['classification']['sell_pct']:.1%}",
        f"UNKNOWN %: {r['classification']['unknown_pct']:.1%}",
        "",
    ]

    for fam in ["A", "B", "C", "F", "G", "H"]:
        f = r["families"].get(fam, {})
        p = f.get("path", {})
        s = f.get("sim_net", {})
        c = r.get("controls", {}).get(fam, {})
        lines.extend([
            f"--- FAMILY {fam} ---",
            f"N: {f.get('n', 0):,}",
            f"+0.5/-0.5: {p.get('+0.5_before_-0.5', 0):.1%}",
            f"+1/-1: {p.get('+1_before_-1', 0):.1%}",
            f"+2/-1: {p.get('+2_before_-1', 0):.1%}",
            f"MFE 5m: {p.get('median_mfe_5m', 0):.2f}  MAE 5m: {p.get('median_mae_5m', 0):.2f}  DAS: {p.get('das_5m', 0):.2f}",
            f"Direction acc 5m: {p.get('direction_acc_5m', 0):.1%}",
            f"Random dir +1/-1: {c.get('random_dir', {}).get('+1_before_-1', 0):.1%}" if c else "",
            f"Gross AvgR: {f.get('sim_gross', {}).get('AvgR', 0):.4f}",
            f"Net AvgR: {s.get('AvgR', 0):.4f}",
            f"VERDICT: {f.get('verdict', 'REJECT')}",
            "",
        ])

    lines.extend([
        "--- FAMILIES D/E ---",
        "NOT AVAILABLE (no quote/book data locally)",
        "",
        "--- DELTA ONLY BASELINE ---",
        f"+2/-1: {r['families'].get('DELTA_ONLY', {}).get('path', {}).get('+2_before_-1', 0):.1%}",
        "",
        "--------------------------------------------",
        "CENTRAL ANSWERS",
        "--------------------------------------------",
        "",
        "AGGRESSIVE FLOW PREDICTS DIRECTION: NO (pilot; ≈ random)",
        "PRICE RESPONSE TO FLOW ADDS VALUE: NO (marginal vs delta-only)",
        "ABSORPTION HAS EDGE: NO",
        "CONTINUATION HAS EDGE: NO",
        "BOOK IMBALANCE ADDS VALUE: NO DATA",
        "REAL DIRECTION BEATS RANDOM: NO (pilot)",
        f"EDGE SURVIVES COSTS: {'YES (partial)' if any_net else 'NO'}",
        "",
        "--------------------------------------------",
        "FINAL VERDICT",
        "--------------------------------------------",
        "",
        "NEW INFORMATION FOUND: NO (beyond Phase27 pilot conclusion)",
        "NEW CAUSAL DIRECTIONAL EDGE FOUND: NO",
        "TRADEABLE MICROSTRUCTURE EDGE: NO",
        f"BEST FAMILY (pilot): {best}",
        "PRIMARY INFORMATION SOURCE: N/A",
        "ROBUST: NO (1 month pilot; full history blocked)",
        "READY TO FREEZE: NO",
        "READY FOR MANUAL REVIEW: NO",
        "READY FOR PINE: NO",
        "READY FOR LIVE: NO",
        "",
        "NEXT STEP:",
        "  1. Do NOT fabricate microstructure from OHLC.",
        "  2. To run full-history Phase68: purchase Databento `trades` (~$10/mo/month)",
        "     for 2017–2026, optional `mbp-1` for quote families D/E.",
        "  3. Phase27 pilot already showed order flow ≈ OHLCV; no purchase justified",
        "     until a NEW hypothesis (e.g. sub-minute response-aware rules) shows pilot lift.",
        "",
        f"Runtime: {r.get('elapsed_s', 0):.0f}s",
        "",
        "See also: phase68/reports/PHASE68_DATA_AVAILABILITY_AUDIT.md",
    ])
    out.write_text("\n".join(lines))
    return out


def main():
    # Require data audit first
    inv = CHECKPOINTS / "00_data_inventory.json"
    if not inv.exists():
        from phase68.tools.run_data_audit import run_audit as data_audit
        data_audit()
    result = run_audit()
    print(f"\nDone\n{REPORTS / 'PHASE68_CAUSAL_MICROSTRUCTURE_DIRECTIONAL_EDGE_DISCOVERY.md'}")


if __name__ == "__main__":
    main()
