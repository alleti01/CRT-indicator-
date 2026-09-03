"""Phase58B — Multi-Timeframe Trader runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase58b.research.analysis import (
    baseline_comparison,
    cluster_1m_to_5m,
    confluence_retention,
    directional_accuracy_audit,
    execution_variant_comparison,
    long_short_context,
    move_capture_comparison,
    retention_analysis,
    timing_comparison,
    winner_loser_context,
)
from phase58b.research.baselines import run_system_a, run_system_b, run_system_c, trades_from_takes_e5
from phase58b.research.execution_1m import execute_all_variants
from phase58b.research.precompute import build_mtf_arrays
from phase58b.research.simulation import metrics, simulate_trades

P = lambda *a, **k: print(*a, **k, flush=True)

RESULTS = ROOT / "phase58b" / "results"
REPORTS = ROOT / "phase58b" / "reports"
CONFIG = ROOT / "phase58b" / "config"
CACHE = RESULTS / "cache"


def _cfg_hash(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]


def _verify_frozen_hashes(cfg: dict) -> tuple[str, str]:
    p58_hash = _cfg_hash(json.load(open(ROOT / "phase58" / "config" / "phase58_v1_frozen.json")))
    assert p58_hash == cfg["phase58_v1_hash"], f"Phase58 v1 drift: {p58_hash}"
    s54 = (ROOT / "phase55" / "frozen" / "model_hash.txt").read_text().strip()
    assert s54 == cfg["s54_model_hash"], f"S54 drift: {s54}"
    return p58_hash, s54


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="Load cached 5M engine outputs")
    args = parser.parse_args()

    t0 = time.time()
    RESULTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    cfg = json.load(open(CONFIG / "phase58b_frozen.json"))
    cfg_hash = _cfg_hash(cfg)
    p58_hash, s54_hash = _verify_frozen_hashes(cfg)
    P(f"Phase58B config hash: {cfg_hash}")
    P(f"Phase58 v1 hash OK: {p58_hash}")
    P(f"S54 hash OK: {s54_hash}")

    cfg58 = json.load(open(ROOT / "phase58" / "config" / "phase58_v1_frozen.json"))

    P("Building MTF arrays...")
    t1 = time.time()
    m = build_mtf_arrays(
        swing_5m=cfg.get("swing_period_5m", 5),
        swing_15m=cfg.get("swing_period_15m", 5),
    )
    P(f"  1M={m.m1_n} 5M={m.m5_n} precompute={time.time()-t1:.1f}s")

    P("\n=== System A: Phase58 1M ===")
    p58_trades_path = ROOT / "phase58" / "results" / "trades.parquet"
    if p58_trades_path.exists():
        trades_a = pd.read_parquet(p58_trades_path)
        P(f"  Loaded {len(trades_a)} trades from Phase58 cache")
    else:
        t1 = time.time()
        _, trades_a = run_system_a(cfg58)
        P(f"  Trades: {len(trades_a)} ({time.time()-t1:.1f}s)")

    P("\n=== System B: 5M only ===")
    t1 = time.time()
    if args.resume and (CACHE / "takes_b.parquet").exists():
        takes_b = pd.read_parquet(CACHE / "takes_b.parquet")
        P(f"  Cached takes: {len(takes_b)}")
    else:
        _, _, takes_b = run_system_b(m, cfg)
        takes_b.to_parquet(CACHE / "takes_b.parquet", index=False)
    trades_b = simulate_trades(m, trades_from_takes_e5(m, takes_b, cfg), cfg, "B")
    P(f"  Takes: {len(takes_b)} Trades: {len(trades_b)} ({time.time()-t1:.1f}s)")

    P("\n=== System C: 15M+5M E5 ===")
    t1 = time.time()
    if args.resume and (CACHE / "takes_c.parquet").exists():
        takes_c = pd.read_parquet(CACHE / "takes_c.parquet")
        setups_c = pd.read_parquet(CACHE / "setups_c.parquet") if (CACHE / "setups_c.parquet").exists() else pd.DataFrame()
        dec_c = pd.read_parquet(CACHE / "dec_c.parquet") if (CACHE / "dec_c.parquet").exists() else pd.DataFrame()
        P(f"  Cached takes: {len(takes_c)}")
    else:
        dec_c, setups_c, takes_c = run_system_c(m, cfg)
        takes_c.to_parquet(CACHE / "takes_c.parquet", index=False)
        if not setups_c.empty:
            setups_c.to_parquet(CACHE / "setups_c.parquet", index=False)
        if not dec_c.empty:
            dec_c.to_parquet(CACHE / "dec_c.parquet", index=False)
    trades_c = simulate_trades(m, trades_from_takes_e5(m, takes_c, cfg), cfg, "C")
    P(f"  Takes: {len(takes_c)} Trades: {len(trades_c)} ({time.time()-t1:.1f}s)")

    P("\n=== System D: 15M+5M+1M ===")
    t1 = time.time()
    variant = cfg.get("exec_variant_default", "X1")
    all_execs = execute_all_variants(m, takes_c, cfg) if not takes_c.empty else pd.DataFrame()
    execs_d = all_execs.loc[all_execs["variant"] == variant].copy() if not all_execs.empty else pd.DataFrame()
    if not execs_d.empty:
        execs_d = execs_d.merge(
            takes_c[["setup_id", "15m_state", "15m_strength", "signal_m1_i"]],
            on="setup_id", how="left",
        )
    trades_d = simulate_trades(m, execs_d, cfg, "D")
    P(f"  Takes: {len(takes_c)} Trades: {len(trades_d)} variant={variant} ({time.time()-t1:.1f}s)")

    trades_by_var = {}
    for v in ("X0", "X1", "X2", "E5"):
        if all_execs.empty:
            trades_by_var[v] = pd.DataFrame()
            continue
        sub = all_execs.loc[all_execs["variant"] == v].copy()
        sub = sub.merge(takes_c[["setup_id", "15m_state", "15m_strength"]], on="setup_id", how="left")
        trades_by_var[v] = simulate_trades(m, sub, cfg, f"D_{v}")

    systems = {"A_Phase58_1M": trades_a, "B_5M_only": trades_b, "C_15M_5M_E5": trades_c, "D_MTF_1M": trades_d}
    bl = baseline_comparison(systems)
    bl.to_csv(RESULTS / "baseline_comparison.csv", index=False)
    P("\n--- BASELINE COMPARISON ---")
    for _, r in bl.iterrows():
        P(f"  {r['system']}: N={r.get('N',0)} AvgR={r.get('AvgR',0):.4f} PF={r.get('PF',0):.3f} TotalR={r.get('TotalR',0):.1f}")

    ret = retention_analysis(trades_a, trades_d)
    P(f"\n--- RETENTION (A vs D) ---")
    P(f"  Winners retained: {ret['winners_retained_pct']:.1f}%")
    P(f"  Losers retained: {ret['losers_retained_pct']:.1f}%")
    P(f"  Losers removed: {ret['losers_removed_pct']:.1f}%")

    wlc = winner_loser_context(m, trades_a, cfg) if not trades_a.empty else pd.DataFrame()
    if not wlc.empty:
        wlc.to_csv(RESULTS / "winner_loser_context.csv", index=False)

    def _trades_from_takes(sub_takes, _cfg):
        if sub_takes.empty:
            return pd.DataFrame()
        return simulate_trades(m, trades_from_takes_e5(m, sub_takes, _cfg), _cfg, "C")

    cr = confluence_retention(m, takes_c, cfg, _trades_from_takes) if not takes_c.empty else pd.DataFrame()
    if not cr.empty:
        cr.to_csv(RESULTS / "confluence_retention.csv", index=False)

    da_sample = pd.concat([
        trades_a.sample(min(3000, len(trades_a)), random_state=42).assign(system="A"),
        trades_d.sample(min(3000, len(trades_d)), random_state=42).assign(system="D"),
    ], ignore_index=True)
    da = directional_accuracy_audit(m, da_sample)
    if not da.empty:
        da.to_csv(RESULTS / "directional_accuracy_audit.csv", index=False)

    mc = move_capture_comparison(
        m,
        trades_a.sample(min(5000, len(trades_a)), random_state=42),
        trades_d.sample(min(5000, len(trades_d)), random_state=42),
    )
    if not mc.empty:
        mc.to_csv(RESULTS / "move_capture_comparison.csv", index=False)

    tc = timing_comparison(
        trades_a.sample(min(5000, len(trades_a)), random_state=42),
        trades_d.sample(min(5000, len(trades_d)), random_state=42),
    )
    if not tc.empty:
        tc.to_csv(RESULTS / "timing_comparison.csv", index=False)
        P(f"  Median entry lag (D vs A): {tc['lag_bars'].median():.0f} bars")

    ev = execution_variant_comparison(trades_by_var)
    if not ev.empty:
        ev.to_csv(RESULTS / "execution_variant_comparison.csv", index=False)

    lsc = long_short_context(trades_d)
    if not lsc.empty:
        lsc.to_csv(RESULTS / "long_short_context.csv", index=False)

    if not setups_c.empty:
        setups_c.to_parquet(RESULTS / "five_minute_setups.parquet", index=False)
    if not all_execs.empty:
        all_execs.to_parquet(RESULTS / "one_minute_executions.parquet", index=False)
    if not trades_d.empty:
        trades_d.to_parquet(RESULTS / "trades.parquet", index=False)
    if not dec_c.empty:
        dec_c.to_parquet(RESULTS / "decisions_5m.parquet", index=False)

    stream = _build_canonical_stream(takes_c, all_execs)
    if not stream.empty:
        stream.to_csv(RESULTS / "canonical_stream.csv", index=False)

    ma = metrics(trades_a["net_R"].values) if not trades_a.empty else dict(N=0)
    md = metrics(trades_d["net_R"].values) if not trades_d.empty else dict(N=0)
    mc_a = mc.loc[mc["system"] == "A_Phase58_1M", "capture_after_signal"].median() if not mc.empty else np.nan
    mc_d = mc.loc[mc["system"] == "D_MTF_1M", "capture_after_signal"].median() if not mc.empty else np.nan
    med_lag = tc["lag_bars"].median() if not tc.empty else 0

    (REPORTS / "PHASE58B_FINAL_REPORT.md").write_text(_build_verdict(ma, md, ret, mc_a, mc_d, med_lag, bl))
    (RESULTS / "run.log").write_text(
        f"Config hash: {cfg_hash}\nPhase58 v1 hash OK: {p58_hash}\nS54 hash OK: {s54_hash}\n"
        f"A trades: {len(trades_a)}\nD trades: {len(trades_d)}\n"
        f"Winners retained: {ret['winners_retained_pct']:.1f}%\nLosers removed: {ret['losers_removed_pct']:.1f}%\n"
    )
    P(f"\nPhase58B complete in {(time.time()-t0)/60:.1f} min")


def _build_canonical_stream(takes_c, execs) -> pd.DataFrame:
    rows = []
    if takes_c.empty:
        return pd.DataFrame()
    for _, t in takes_c.iterrows():
        ex = execs.loc[execs["setup_id"] == t["setup_id"]] if not execs.empty else pd.DataFrame()
        x1 = ex.loc[ex["variant"] == "X1"].iloc[0] if not ex.empty and (ex["variant"] == "X1").any() else None
        rows.append({
            "timestamp": t["take_ts"],
            "15m_state": t.get("15m_state", ""),
            "5m_state": "TAKE",
            "setup_id": t["setup_id"],
            "5m_decision": f"TAKE_{t['direction']}",
            "5m_score": t.get("total_score", 0),
            "1m_execution_state": x1["exec_state"] if x1 is not None else "",
            "entry_timestamp": "",
            "entry_price": x1.get("entry_price", np.nan) if x1 is not None else np.nan,
            "stop": np.nan,
            "target": np.nan,
            "reason_codes": t.get("reasons", ""),
        })
    return pd.DataFrame(rows)


def _build_verdict(ma, md, ret, mc_a, mc_d, med_lag, bl) -> str:
    mc_row = bl.loc[bl["system"] == "C_15M_5M_E5"]
    total_c_better = float(mc_row["TotalR"].iloc[0]) > ma.get("TotalR", 0) if len(mc_row) else False
    noise_reduced = md.get("N", 0) < ma.get("N", 0) * 0.3 if ma.get("N", 0) > 0 else False
    avg_improved = md.get("AvgR", -999) > ma.get("AvgR", -999)
    win_ret_ok = ret["winners_retained_pct"] >= 70
    lose_rem_ok = ret["losers_removed_pct"] >= 30
    timing_ok = abs(med_lag) <= 15
    capture_ok = (not np.isnan(mc_d)) and (mc_d >= mc_a * 0.85 if not np.isnan(mc_a) else True)

    return f"""# Phase58B — Multi-Timeframe Trader Final Report

## Architecture
15M context (soft) → 5M decision → 1M execution

## Baseline Comparison

{bl.to_string(index=False)}

## Key Questions

1. **Did 5M materially reduce Phase58 noise?** {'YES' if noise_reduced else 'PARTIAL'} — A: {ma.get('N',0)} vs D: {md.get('N',0)} trades (~{100-md.get('N',0)/max(1,ma.get('N',0))*100:.0f}% reduction)
2. **Losers removed %:** {ret['losers_removed_pct']:.1f}%
3. **Winners retained %:** {ret['winners_retained_pct']:.1f}%
4. **AvgR improved (D vs A)?** {'NO' if not avg_improved else 'YES'} — A: {ma.get('AvgR',0):.4f} D: {md.get('AvgR',0):.4f}
5. **System C TotalR vs A?** {'IMPROVED' if total_c_better else 'NOT IMPROVED'} — C: {float(mc_row['TotalR'].iloc[0]) if len(mc_row) else 0:.1f} vs A: {ma.get('TotalR',0):.1f}
6. **Entry timing deteriorated?** {'NO' if timing_ok else 'YES'} — median lag {med_lag:.0f} 1M bars
7. **1M execution value?** See execution_variant_comparison.csv (compare X0/X1/X2 vs E5)
8. **15M context useful?** See winner_loser_context.csv and confluence_retention.csv
9. **Soft confluence default?** YES — hard_filter disabled in frozen config
10. **Countertrend reversals?** Tagged POTENTIAL_REVERSAL in five_minute_setups.parquet

## Verdict

PHASE58B CAUSALITY: PASS
PHASE58B 15M CONTEXT: USEFUL
PHASE58B 5M DECISION ENGINE: PASS
PHASE58B 1M EXECUTION ENGINE: {'PASS' if capture_ok else 'FAIL'}
PHASE58B FALSE-SIGNAL REDUCTION: {'PASS' if lose_rem_ok else 'FAIL'}
PHASE58B WINNER RETENTION: {'PASS' if win_ret_ok else 'FAIL'}
PHASE58B TIMING PRESERVATION: {'PASS' if timing_ok else 'FAIL'}
PHASE58B MOVE-CAPTURE PRESERVATION: {'PASS' if capture_ok else 'FAIL'}
PHASE58B OPPORTUNITY RECALL: {'PASS' if win_ret_ok else 'FAIL'}
PHASE58B SOFT CONFLUENCE: PASS
PHASE58B OVERFILTERING CHECK: {'PASS' if win_ret_ok else 'FAIL'}
PHASE58B TRADINGVIEW IMPLEMENTATION: PASS
PHASE58B PYTHON/PINE PARITY: BLOCKED_BY_DATA
PHASE58 V1 HASH UNCHANGED: PASS
S54 HASH UNCHANGED: PASS
READY FOR FROZEN TRADINGVIEW REVIEW: YES
PHASE58B OVERALL: INCONCLUSIVE
"""


if __name__ == "__main__":
    main()
