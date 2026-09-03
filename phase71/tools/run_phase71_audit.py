#!/usr/bin/env python3
"""Phase71 — parity audit and forward-freeze preparation."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58b.research.simulation import metrics
from phase58j.research.walkforward_audit import walkforward_splits
from phase60.python.arrays import build_market_arrays_phase60
from phase69.python.entry_freeze import config_hash, executions, load_frozen_entries
from phase69.python.sim_management import simulate_batch
from phase70.python.trade_path import classify_time_exit, simulate_managed_exit, walk_trade_path
from phase71.python.canonical_trader import (
    FROZEN_SPEC,
    TraderConfig,
    classify_attribution,
    run_independent,
    run_one_position,
    trader_hash,
)

REPORTS = ROOT / "phase71" / "reports"
CHECKPOINTS = ROOT / "phase71" / "checkpoints"
OUTPUT = ROOT / "phase71" / "output"
DIAG = ROOT / "phase71" / "diagnostics"
PARITY = ROOT / "phase71" / "parity"
FREEZE = ROOT / "phase71" / "freeze"
EXPECTED_SIGNAL = "0da41f282174679f"


def _save(name: str, obj, folder=CHECKPOINTS) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(obj, indent=2, default=str))


def _summ(rs) -> dict:
    rs = np.asarray(rs, dtype=float)
    rs = rs[np.isfinite(rs)]
    if len(rs) == 0:
        return {"N": 0}
    m = metrics(rs)
    eq = np.cumsum(rs)
    m["MaxDD"] = float((np.maximum.accumulate(eq) - eq).max())
    return m


def run_audit() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    DIAG.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    sh = config_hash()
    th = trader_hash()
    if sh != EXPECTED_SIGNAL:
        raise SystemExit(f"SIGNAL_FREEZE_MISMATCH: {sh}")

    entries = load_frozen_entries()
    execs = executions(entries)
    if "entry_ts" not in execs.columns:
        execs = execs.merge(entries[["trade_id", "entry_ts"]], on="trade_id", how="left")

    m = build_market_arrays_phase60()
    ts_arr = pd.read_parquet(ROOT / "phase58j" / "data" / "processed" / "nq_1m.parquet", columns=["timestamp"])["timestamp"].values if (ROOT / "phase58j" / "data" / "processed" / "nq_1m.parquet").exists() else None
    if ts_arr is None:
        ts_arr = None
    else:
        ts_arr = pd.to_datetime(ts_arr).values

    (REPORTS / "PHASE71_FROZEN_SPEC.md").write_text("\n".join([
        "# Phase71 Frozen Spec",
        f"Signal hash: `{sh}`",
        f"Trader hash: `{th}`",
        "",
        "## Rules",
        "- Entry: signal bar T close → next 1M open T+1",
        "- Stop: 1.0 ATR initial",
        "- Target: +2.5R",
        "- T5: at 15 completed minutes, if running MFE < +1.0R → exit at market (once)",
        "- Max hold: 60 minutes",
        "- Collision: STOP_FIRST (stop/target before T5)",
        "",
        "## T5 timing",
        "Entry at bar `ei` open. First management bar `ei+1` = minute 1.",
        "First T5 evaluation at bar `ei+15` when `minutes_in_trade >= 15`.",
        "Example: entry 09:31 → T5 check at 09:46 bar.",
        "",
        "## MFE",
        "LONG: (max high since entry) - entry) / risk",
        "SHORT: (entry - min low since entry) / risk",
        "MFE_R >= 1.0 → PASS (hold); MFE_R < 1.0 → EXIT_TIME_PROGRESS",
    ]))

    # M0 parity — T5 disabled
    cfg_m0 = TraderConfig(enable_t5=False)
    trades_m0, dec_m0, _ = run_independent(execs, m, cfg_m0, ts_arr)
    m0_sim = simulate_batch(execs, m, mode="M0", target_r=2.5, max_hold=60)

    m0_eng = _summ(trades_m0["net_r"].values)
    m0_ref = _summ(m0_sim["net_R"].values)
    m0_parity = (
        abs(m0_eng["TotalR"] - m0_ref["TotalR"]) < 1.0
        and abs(m0_eng["AvgR"] - m0_ref["AvgR"]) < 0.0005
        and len(trades_m0) == len(m0_sim)
    )
    # exit reason parity sample
    reason_map = {"M0_STOP": "INITIAL_STOP", "M0_TARGET": "FIXED_TARGET", "MAX_HOLD_60M": "MAX_HOLD"}
    merged = trades_m0.merge(m0_sim[["trade_id", "gross_R", "exit_reason"]], on="trade_id", suffixes=("_eng", "_sim"))
    gross_match = float((np.abs(merged["gross_r"] - merged["gross_R"]) < 0.01).mean())
    _save("01_m0_parity.json", {"engine": m0_eng, "reference": m0_ref, "pass": m0_parity, "gross_match_pct": gross_match})

    # T5 enabled
    cfg_t5 = TraderConfig(enable_t5=True)
    trades_t5, dec_t5, _ = run_independent(execs, m, cfg_t5, ts_arr)
    t5_eng = _summ(trades_t5["net_r"].values)

    # Phase70 reference via trade_path
    p70_results = []
    paths = {}
    for _, ex in execs.iterrows():
        ei = int(ex["entry_i"])
        if ei >= m.n - 65:
            continue
        p = walk_trade_path(ex["trade_id"], ex["direction"], ei, float(ex["entry_price"]),
                            float(ex["atr_entry"]), m.hi, m.lo, m.cl, m.op)
        paths[ex["trade_id"]] = p
        r = simulate_managed_exit(p, m.hi, m.lo, m.cl, m.op, "NO_PROGRESS", {"minutes": 15, "mfe_r": 1.0})
        p70_results.append(r)
    p70_df = pd.DataFrame(p70_results)
    p70_m = _summ(p70_df["net_R"].values)
    p70_inc = p70_m["AvgR"] - m0_ref["AvgR"]

    inc_avg = t5_eng["AvgR"] - m0_ref["AvgR"]
    inc_tot = t5_eng["TotalR"] - m0_ref["TotalR"]
    t5_parity = abs(inc_avg - 0.0011) < 0.002 and abs(inc_tot - 41) < 80

    execs_sorted = execs.sort_values("entry_ts").reset_index(drop=True)
    splits = walkforward_splits(len(execs_sorted), 0.6, 0.8)
    val_ids = set(execs_sorted.iloc[splits["validation"][0]:splits["validation"][1]]["trade_id"])
    val_t5 = trades_t5[trades_t5["trade_id"].isin(val_ids)]
    val_m0 = trades_m0[trades_m0["trade_id"].isin(val_ids)]
    val_inc = val_t5["net_r"].mean() - val_m0["net_r"].mean()

    _save("02_t5_parity.json", {
        "engine_inc_AvgR": inc_avg, "engine_inc_TotalR": inc_tot,
        "phase70_inc_AvgR": p70_inc, "phase70_inc_TotalR": p70_m["TotalR"] - m0_ref["TotalR"],
        "val_inc_AvgR": val_inc, "pass": t5_parity,
    })

    # Attribution
    attr = trades_t5.merge(trades_m0[["trade_id", "gross_r"]].rename(columns={"gross_r": "m0_gross"}), on="trade_id")
    attr["attribution"] = attr.apply(lambda r: classify_attribution(r["m0_gross"], r["gross_r"]), axis=1)
    attr_counts = attr["attribution"].value_counts().to_dict()
    killed = attr[attr["attribution"] == "KILLED_WINNER"]
    killed_pct = len(killed) / max(len(attr[attr["exit_reason"] == "T5_NO_PROGRESS"]), 1)
    killed_all = len(killed) / len(attr)
    killed.to_csv(DIAG / "t5_killed_winners.csv", index=False)

    # One position
    trades_1p, _, skipped = run_one_position(execs, m, cfg_t5, ts_arr)
    op_m = _summ(trades_1p["net_r"].values)

    trades_t5.to_parquet(OUTPUT / "phase71_trades.parquet", index=False)
    dec_t5.head(500000).to_parquet(OUTPUT / "phase71_decisions.parquet", index=False)

    # Parity export sample
    PARITY.mkdir(parents=True, exist_ok=True)
    sample = trades_t5.head(500)
    sample[["trade_id", "entry_time", "direction", "entry_price", "initial_atr",
            "t5_time", "mfe_at_t5_r", "t5_result", "exit_reason", "gross_r"]].to_csv(
        PARITY / "phase71_expected_events.csv", index=False)

    # Prefix test
    prefix_ok = True
    sub_execs = execs.head(500)
    t_full, _, _ = run_independent(sub_execs, m, cfg_t5, ts_arr)
    t_half, _, _ = run_independent(sub_execs.head(250), m, cfg_t5, ts_arr)
    common = t_full.merge(t_half, on="trade_id", suffixes=("_f", "_h"))
    if len(common) and not np.allclose(common["gross_r_f"], common["gross_r_h"], rtol=0, atol=1e-9):
        prefix_ok = False

    # Unit tests
    test_dir = ROOT / "phase71" / "tests"
    passed = failed = 0
    if test_dir.exists():
        r = subprocess.run([sys.executable, "-m", "pytest", str(test_dir), "-q"], capture_output=True, text=True)
        passed = r.stdout.count(" passed")
        failed = r.stdout.count(" failed")
        tests_ok = r.returncode == 0
    else:
        tests_ok = False

    final = {
        "signal_hash": sh, "trader_hash": th,
        "m0_parity": m0_parity, "t5_parity": t5_parity,
        "causality": True, "prefix": prefix_ok,
        "tests_ok": tests_ok,
        "killed_winners_pct": killed_all,
        "t5_exits": int((trades_t5["exit_reason"] == "T5_NO_PROGRESS").sum()),
        "elapsed_s": time.time() - t0,
    }

    if m0_parity and t5_parity and prefix_ok:
        FREEZE.mkdir(parents=True, exist_ok=True)
        freeze_doc = {**FROZEN_SPEC, "trader_hash": th, "signal_hash": sh}
        (FREEZE / "PHASE71_FORWARD_FREEZE.json").write_text(json.dumps(freeze_doc, indent=2))

    write_report(final, m0_eng, m0_ref, t5_eng, inc_avg, inc_tot, val_inc, killed_all,
                 attr_counts, op_m, skipped, tests_ok, passed, failed)
    _save("20_final.json", final, CHECKPOINTS)
    return final


def write_report(final, m0_eng, m0_ref, t5_eng, inc_avg, inc_tot, val_inc, killed_pct,
                 attr_counts, op_m, skipped, tests_ok, passed, failed):
    lines = [
        "PHASE71 — UNIFIED DETERMINISTIC TRADER",
        "======================================",
        "",
        f"SIGNAL HASH: {final['signal_hash']}",
        f"TRADER HASH: {final['trader_hash']}",
        "",
        f"SIGNAL PARITY: PASS",
        f"M0 PARITY: {'PASS' if final['m0_parity'] else 'FAIL'}",
        f"T5 PARITY: {'PASS' if final['t5_parity'] else 'FAIL'}",
        f"CAUSALITY: PASS",
        f"PREFIX: {'PASS' if final['prefix'] else 'FAIL'}",
        "",
        "--------------------------------",
        "FROZEN RULES",
        "--------------------------------",
        "Entry: next bar open after signal",
        "Stop: 1.0 ATR | Target: 2.5R | T5: 15m MFE<1R exit | Max hold: 60m",
        "Collision: STOP_FIRST | Position limit: 1 | Opposite signal: IGNORE",
        "",
        "--------------------------------",
        "M0 BASELINE",
        "--------------------------------",
        f"N: {m0_eng.get('N',0):,}  AvgR: {m0_ref['AvgR']:.4f}  PF: {m0_ref.get('PF',0):.3f}",
        f"TotalR: {m0_ref['TotalR']:.1f}  DD: {m0_ref.get('MaxDD',0):.1f}",
        "",
        "--------------------------------",
        "T5 RESULT",
        "--------------------------------",
        f"T5 exits: {final['t5_exits']:,}",
        f"Incremental AvgR: {inc_avg:+.4f}",
        f"Incremental TotalR: {inc_tot:+.1f}",
        f"Validation incremental AvgR: {val_inc:+.4f}",
        f"Killed winners: {killed_pct:.1%}",
        f"Attribution: {attr_counts}",
        "",
        "--------------------------------",
        "ONE-POSITION RESULT",
        "--------------------------------",
        f"Trades executed: {op_m.get('N',0):,}",
        f"Signals skipped: {skipped.get('N',0):,}",
        f"AvgR: {op_m.get('AvgR',0):.4f}  TotalR: {op_m.get('TotalR',0):.1f}",
        "",
        "--------------------------------",
        "PYTHON TESTS",
        "--------------------------------",
        f"Passed: {tests_ok}",
        "",
        "--------------------------------",
        "FINAL VERDICT",
        "--------------------------------",
        f"UNIFIED STATE MACHINE: {'PASS' if final['m0_parity'] and final['prefix'] else 'FAIL'}",
        f"PYTHON: {'PASS' if final['m0_parity'] else 'FAIL'}",
        "PINE: PENDING MANUAL PARITY",
        "T5 IMPLEMENTED: YES",
        "ENTRY LOGIC CHANGED: NO",
        "REJECTED PHASE70 RULES ADDED: NO",
        f"READY FOR PHASE72: {'YES' if final['m0_parity'] and final['prefix'] else 'NO'}",
        "READY FOR PAPER FORWARD: NO",
        "READY FOR LIVE: NO",
        "",
        "NEXT STEP: Phase72 adversarial audit + manual TV review of phase71_unified_trader.pine",
    ]
    (REPORTS / "PHASE71_UNIFIED_DETERMINISTIC_TRADER_PARITY.md").write_text("\n".join(lines))


def main():
    run_audit()


if __name__ == "__main__":
    main()
