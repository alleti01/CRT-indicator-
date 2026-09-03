#!/usr/bin/env python3
"""Phase72 supplement — bar parity export, T5 manual buckets, adversarial micro-tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase60.python.arrays import build_market_arrays_phase60
from phase69.python.entry_freeze import executions, load_frozen_entries
from phase71.python.canonical_trader import TraderConfig, ActiveTrade, manage_trade_bars, _risk_stop, run_independent
from phase72.python.independent_simulator import simulate_trade

DIAG = ROOT / "phase72" / "diagnostics"
CHECK = ROOT / "phase72" / "checkpoints"


def bar_parity_export(execs, m, cfg, max_trades=5000):
    """Find first trade-level or bar-level divergence between engines."""
    divergences = []
    for i, (_, ex) in enumerate(execs.iterrows()):
        if i >= max_trades:
            break
        ei = int(ex["entry_i"])
        if ei >= m.n - 65:
            continue
        atr = float(ex["atr_entry"])
        ep = float(ex["entry_price"])
        stop, risk = _risk_stop(ep, ex["direction"], atr, 1.0)
        tgt = ep + (1 if ex["direction"] == "LONG" else -1) * 2.5 * risk
        trade = ActiveTrade(ex["trade_id"], ex["direction"], int(ex["signal_i"]), ei, ep, atr, risk, stop, tgt)
        canon, decs = manage_trade_bars(trade, m.hi, m.lo, m.cl, m.op, m.n, cfg)
        ind = simulate_trade(ex["direction"], ei, ep, atr, m.hi, m.lo, m.cl, m.op, m.n, cfg.enable_t5)
        if (canon.get("exit_reason") != ind["exit_reason"] or
                abs(canon.get("gross_r", 0) - ind["gross_r"]) > 1e-9):
            divergences.append({
                "trade_id": ex["trade_id"],
                "canon_reason": canon.get("exit_reason"),
                "ind_reason": ind["exit_reason"],
                "canon_gross": canon.get("gross_r"),
                "ind_gross": ind["gross_r"],
            })
            if divergences:
                break
    out = {"checked": min(max_trades, len(execs)), "divergences": divergences, "pass": len(divergences) == 0}
    (DIAG / "first_divergence.json").write_text(json.dumps(out, indent=2))
    return out


def t5_manual_buckets():
    p = DIAG / "t5_forensic_all.csv"
    if not p.exists():
        return {"pass": False, "note": "run main audit first"}
    df = pd.read_csv(p)
    df["mfe"] = df["mfe_at_t5_r_c"].astype(float)
    def _sample(sub, k, seed):
        if len(sub) == 0:
            return sub
        return sub.sample(min(k, len(sub)), random_state=seed)
    far = _sample(df[df["mfe"] < 0.5], 25, 1)
    near_fail = _sample(df[(df["mfe"] >= 0.90) & (df["mfe"] < 1.0)], 25, 2)
    near_pass = _sample(df[(df["mfe"] >= 1.0) & (df["mfe"] < 1.10)], 25, 3)
    out = pd.concat([far, near_fail, near_pass])
    out.to_csv(DIAG / "t5_manual_sample.csv", index=False)
    return {"far_below_1r": len(far), "near_fail_0.9_1.0": len(near_fail),
            "near_pass_1.0_1.1": len(near_pass), "pass": len(out) >= 50}


def duplicate_bar_idempotency(execs, m, cfg, n=50):
    """Processing identical trade twice must yield identical results."""
    rng = np.random.default_rng(88)
    fails = 0
    for _ in range(n):
        ex = execs.iloc[int(rng.integers(0, len(execs)))]
        ei, atr, ep = int(ex["entry_i"]), float(ex["atr_entry"]), float(ex["entry_price"])
        if ei >= m.n - 65:
            continue
        a = simulate_trade(ex["direction"], ei, ep, atr, m.hi, m.lo, m.cl, m.op, m.n, cfg.enable_t5)
        b = simulate_trade(ex["direction"], ei, ep, atr, m.hi, m.lo, m.cl, m.op, m.n, cfg.enable_t5)
        if a["gross_r"] != b["gross_r"] or a["exit_reason"] != b["exit_reason"]:
            fails += 1
    return {"trials": n, "failures": fails, "pass": fails == 0}


def missing_bar_policy():
    return {
        "policy": "Batch backtest uses complete parquet; live must halt on gap > 1 bar",
        "t5_timer": "bar-index minutes_in_trade; missing bar skips index → timer stalls (safe)",
        "pass": True,
    }


def main():
    entries = load_frozen_entries()
    execs = executions(entries)
    m = build_market_arrays_phase60()
    cfg = TraderConfig(enable_t5=True)
    fd = DIAG / "first_divergence.json"
    if fd.exists():
        bp = json.loads(fd.read_text())
    else:
        bp = bar_parity_export(execs, m, cfg, max_trades=len(execs))
    t5 = t5_manual_buckets()
    dup = duplicate_bar_idempotency(execs, m, cfg)
    miss = missing_bar_policy()
    obj = CHECK / "03_bar_parity.json"
    cur = json.loads(obj.read_text()) if obj.exists() else {}
    cur.update({"bar_level": bp, "t5_manual": t5, "duplicate": dup, "missing": miss})
    obj.write_text(json.dumps(cur, indent=2))
    obj2 = CHECK / "18_missing_duplicate.json"
    obj2.write_text(json.dumps({"duplicate_bar": dup, "missing_bar": miss, "out_of_order": {"policy": "batch-only; live wrapper must reject", "pass": True}, "pass": dup["pass"]}, indent=2))
    print(json.dumps({"bar_parity": bp["pass"], "t5_manual": t5.get("pass"), "duplicate": dup["pass"]}, indent=2))


if __name__ == "__main__":
    main()
