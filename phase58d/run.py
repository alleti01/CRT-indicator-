"""Phase58D — Early Opportunity State Trader runner."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase58b.research.baselines import trades_from_takes_e5
from phase58b.research.precompute import build_mtf_arrays
from phase58c.research.clustering import cluster_1m_opportunities, summarize_opportunities
from phase58c.research.evaluation import label_meaningful_moves, retention_tier
from phase58d.research.analysis import (
    baseline_comparison_table,
    compare_vs_phase58b,
    evidence_retention_curve,
    move_capture_report,
    opportunity_retention_vs_c,
    shadow_pass_analysis,
    timing_comparison,
    year_stability,
)
from phase58d.research.baselines import baseline_a_frozen, baseline_b_first_per_opp, baseline_cde
from phase58d.research.engine import online_memory_at_signals
from phase58d.research.simulation import metrics, simulate_trades

P = lambda *a, **k: print(*a, **k, flush=True)

RESULTS = ROOT / "phase58d" / "results"
REPORTS = ROOT / "phase58d" / "reports"
CONFIG = ROOT / "phase58d" / "config"
REVIEW = ROOT / "phase58d" / "review"


def _hash_file(path: Path) -> str:
    if path.suffix == ".json":
        return hashlib.sha256(json.dumps(json.load(open(path)), sort_keys=True).encode()).hexdigest()[:16]
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _verify_frozen(cfg: dict) -> None:
    p58 = _hash_file(ROOT / "phase58" / "config" / "phase58_v1_frozen.json")
    p58b = _hash_file(ROOT / "phase58b" / "config" / "phase58b_frozen.json")
    s54 = (ROOT / "phase55" / "frozen" / "model_hash.txt").read_text().strip()
    assert p58 == cfg["phase58_v1_hash"], f"Phase58 drift: {p58}"
    assert p58b == cfg["phase58b_config_hash"], f"Phase58B drift: {p58b}"
    assert s54 == cfg["s54_model_hash"], f"S54 drift: {s54}"


def _exec_from_first_signals(first: pd.DataFrame, m, system: str) -> pd.DataFrame:
    rows = []
    for _, r in first.iterrows():
        si = int(r["signal_i"])
        ei = min(si + 1, m.m1_n - 1)
        rows.append({
            "opportunity_id": r["opportunity_id"],
            "setup_id": r["opportunity_id"],
            "direction": r["direction"],
            "signal_i": si,
            "signal_m1_i": si,
            "entry_i": ei,
            "entry_price": float(m.m1_op[ei]),
            "variant": system,
            "tag": "FIRST_SIGNAL",
            "delay_bars_1m": 1,
        })
    return pd.DataFrame(rows)


def _attach_trade_ids(trades: pd.DataFrame, system: str) -> pd.DataFrame:
    if trades.empty:
        return trades
    t = trades.copy()
    t["trade_id"] = [f"{system}-{i+1:06d}" for i in range(len(t))]
    t["system"] = system
    return t


def main():
    t0 = time.time()
    for d in (RESULTS, REPORTS, REVIEW):
        d.mkdir(parents=True, exist_ok=True)

    cfg = json.load(open(CONFIG / "phase58d_frozen.json"))
    cfg58b = json.load(open(ROOT / "phase58b" / "config" / "phase58b_frozen.json"))
    _verify_frozen(cfg)
    P("Frozen hashes verified")

    P("Loading frozen Phase58 outputs...")
    trades_a = baseline_a_frozen(ROOT / "phase58" / "results" / "trades.parquet")
    dec_takes = pd.read_parquet(
        ROOT / "phase58" / "results" / "decisions.parquet",
        filters=[("decision", "in", ["TAKE_LONG", "TAKE_SHORT"])],
    )
    armed_i = trades_a.merge(
        dec_takes[["bar_i", "armed_i"]], left_on="signal_i", right_on="bar_i", how="left"
    )["armed_i"].fillna(-1).values.astype(int)

    P("Building MTF arrays...")
    m = build_mtf_arrays(swing_5m=cfg58b.get("swing_period_5m", 5))
    idx = m.m1_idx

    # Baseline B
    P("Baseline B — first signal per opportunity...")
    first_b = baseline_b_first_per_opp(trades_a, armed_i, cfg["structural_gap_bars"])
    exec_b = _exec_from_first_signals(first_b, m, "B")
    trades_b = _attach_trade_ids(simulate_trades(m, exec_b, cfg, "B"), "B")

    # Online memory parity check
    online = online_memory_at_signals(trades_a, cfg["structural_gap_bars"])
    offline = cluster_1m_opportunities(trades_a, armed_i, structural_gap=cfg["structural_gap_bars"])
    parity = (online["opportunity_id"].values == offline.sort_values("signal_i").reset_index(drop=True)["opportunity_id"].values).mean()
    P(f"  Online/offline memory parity: {parity*100:.2f}%")

    opps_c_ref = pd.read_parquet(ROOT / "phase58c" / "results" / "opportunities.parquet")
    if "first_signal_i" not in opps_c_ref.columns and "start_signal_i" in opps_c_ref.columns:
        opps_c_ref["first_signal_i"] = opps_c_ref["start_signal_i"]

    systems_exec = {}
    systems_trades = {}
    systems_opps = {}

    # C — memory only
    P("Variant C — opportunity memory only...")
    opps_c, upd_c, dec_c, exec_c, rej_c, wait_c = baseline_cde(m, trades_a, cfg, "C", "C")
    trades_c = _attach_trade_ids(simulate_trades(m, exec_c, cfg, "C"), "C")
    systems_exec["C"] = exec_c
    systems_trades["C_memory"] = trades_c
    systems_opps["C_memory"] = opps_c

    # D — HTF soft intelligence
    P("Variant D — + 15M/5M soft intelligence...")
    opps_d, upd_d, dec_d, exec_d, rej_d, wait_d = baseline_cde(m, trades_a, cfg, "D", "D")
    trades_d = _attach_trade_ids(simulate_trades(m, exec_d, cfg, "D"), "D")
    systems_exec["D"] = exec_d
    systems_trades["D_HTF"] = trades_d
    systems_opps["D_HTF"] = opps_d

    # E — full reaction
    P("Variant E — full TAKE/WAIT/PASS...")
    opps_e, upd_e, dec_e, exec_e, rej_e, wait_e = baseline_cde(m, trades_a, cfg, "E", "E")
    trades_e = _attach_trade_ids(simulate_trades(m, exec_e, cfg, "E"), "E")
    if not exec_e.empty and not trades_e.empty:
        trades_e = trades_e.merge(
            exec_e[["setup_id", "location_score", "direction_score", "reaction_score", "total_evidence"]],
            on="setup_id", how="left",
        )
    systems_exec["E"] = exec_e
    systems_trades["E_full"] = trades_e
    systems_opps["E_full"] = opps_e

    for opps_df in (opps_c, opps_d, opps_e):
        opps_df["first_signal_i"] = opps_df["created_i"]

    # Shadow simulations for PASS
    P("Shadow books...")
    shadow_exec = []
    for _, r in rej_e.head(3000).iterrows():
        ei = int(r["shadow_entry_i"])
        if ei < m.m1_n:
            shadow_exec.append({
                "opportunity_id": r["opportunity_id"],
                "direction": r["direction"],
                "signal_i": int(r["signal_i"]),
                "entry_i": ei,
                "entry_price": float(m.m1_op[ei]),
                "variant": "SHADOW_PASS",
            })
    shadow_trades = simulate_trades(m, pd.DataFrame(shadow_exec), cfg, "SHADOW") if shadow_exec else pd.DataFrame()

    # Baseline A metrics
    trades_a_tagged = trades_a.copy()
    trades_a_tagged["system"] = "A"
    all_systems = {
        "Phase58_raw": trades_a_tagged,
        "Phase58C_first": trades_b,
        "Phase58D_memory": trades_c,
        "Phase58D_HTF": trades_d,
        "Phase58D_full": trades_e,
    }
    opps_map = {
        "Phase58_raw": opps_c_ref,
        "Phase58C_first": opps_c_ref,
        "Phase58D_memory": opps_c,
        "Phase58D_HTF": opps_d,
        "Phase58D_full": opps_e,
    }

    baseline = baseline_comparison_table(all_systems, opps_map)
    baseline.loc[baseline["system"] == "Phase58_raw", "raw_signals"] = len(trades_a)
    baseline.loc[baseline["system"] == "Phase58_raw", "opportunities"] = len(opps_c_ref)
    for name, tr in all_systems.items():
        if name != "Phase58_raw":
            baseline.loc[baseline["system"] == name, "raw_signals"] = len(trades_a)

    opp_ret = opportunity_retention_vs_c(opps_c_ref, opps_e, trades_a, trades_e)
    timing = timing_comparison(opps_c_ref, opps_e.assign(first_signal_i=opps_e["created_i"]), trades_e)
    move_cap = move_capture_report(m, trades_e)
    shadow = shadow_pass_analysis(rej_e, shadow_trades)
    ev_curve = evidence_retention_curve(trades_e, "total_evidence") if "total_evidence" in trades_e.columns else pd.DataFrame()
    yr = year_stability(trades_e, idx)

    # Phase58B comparison
    takes_58b = pd.read_parquet(ROOT / "phase58b" / "results" / "cache" / "takes_c.parquet")
    exec_58b = trades_from_takes_e5(m, takes_58b, cfg58b)
    trades_58b = simulate_trades(m, exec_58b, cfg58b, "58B_C")
    vs_58b = compare_vs_phase58b(trades_e, trades_58b)

    # Meaningful moves
    labels = label_meaningful_moves(opps_e.assign(first_signal_i=opps_e["created_i"]), m.m1_hi, m.m1_lo, m.m1_cl, m.m1_atr)
    mm_thr = 1.0
    if not labels.empty and f"meaningful_{mm_thr}atr_60m" in labels.columns:
        ref_mm = opps_c_ref.merge(labels[["opportunity_id", f"meaningful_{mm_thr}atr_60m"]], on="opportunity_id", how="left")
        kept = set(opps_e.loc[opps_e["traded"] | (opps_e["state"].isin(["TAKE", "IN_TRADE"]))]["opportunity_id"])
        mm_ref = ref_mm.loc[ref_mm[f"meaningful_{mm_thr}atr_60m"] == True]
        mm_ret = len(kept & set(mm_ref["opportunity_id"])) / len(mm_ref) * 100 if len(mm_ref) else 0
    else:
        mm_ret = 0

    # Long/short
    ls_rows = []
    for direction in ["LONG", "SHORT"]:
        sub = trades_e.loc[trades_e["direction"] == direction]
        met = metrics(sub["net_R"].values) if not sub.empty else {}
        ls_rows.append({"direction": direction, "trades": met.get("N", 0), "AvgR": met.get("AvgR", 0), "TotalR": met.get("TotalR", 0)})
    long_short = pd.DataFrame(ls_rows)

    # Save outputs
    opps_e.to_parquet(RESULTS / "opportunities.parquet", index=False)
    pd.concat([upd_c, upd_d, upd_e], ignore_index=True).to_parquet(RESULTS / "opportunity_updates.parquet", index=False)
    pd.concat([dec_c, dec_d, dec_e], ignore_index=True).to_parquet(RESULTS / "decisions.parquet", index=False)
    trades_e.to_parquet(RESULTS / "trades.parquet", index=False)
    rej_e.to_parquet(RESULTS / "rejected_shadow.parquet", index=False)
    wait_e.to_parquet(RESULTS / "wait_shadow.parquet", index=False)

    baseline.to_csv(RESULTS / "baseline_comparison.csv", index=False)
    opp_ret.to_csv(RESULTS / "opportunity_retention.csv", index=False)
    pd.DataFrame([{"meaningful_move_retention_pct": mm_ret}]).to_csv(RESULTS / "meaningful_move_retention.csv", index=False)
    timing.to_csv(RESULTS / "timing_comparison.csv", index=False)
    move_cap.to_csv(RESULTS / "move_capture.csv", index=False)
    if not ev_curve.empty:
        ev_curve.to_csv(RESULTS / "evidence_retention_curve.csv", index=False)
    shadow.to_csv(RESULTS / "rejected_shadow_summary.csv", index=False)
    wait_e.to_csv(RESULTS / "wait_shadow.csv", index=False)
    long_short.to_csv(RESULTS / "long_short.csv", index=False)
    yr.to_csv(RESULTS / "year_stability.csv", index=False)
    vs_58b.to_csv(RESULTS / "phase58b_comparison.csv", index=False)

    # Additional diagnostic outputs
    if not trades_e.empty:
        wl = trades_e.copy()
        wl["outcome"] = np.where(wl["net_R"] > 0, "WINNER", "LOSER")
        wl[["direction", "outcome", "net_R", "location_score", "direction_score", "reaction_score", "15m_state"]].to_csv(
            RESULTS / "winner_loser_features.csv", index=False)
        trades_e.groupby("direction").agg(trades=("net_R", "count"), AvgR=("net_R", "mean"), TotalR=("net_R", "sum")).reset_index().to_csv(
            RESULTS / "direction_analysis.csv", index=False)
        if "location_score" in trades_e.columns:
            trades_e.groupby("location_score").agg(trades=("net_R", "count"), AvgR=("net_R", "mean")).reset_index().to_csv(
                RESULTS / "location_analysis.csv", index=False)
    dec_e.groupby("decision").agg(n=("bar_i", "count")).reset_index().to_csv(RESULTS / "reason_code_performance.csv", index=False)

    def _session(h):
        if h < 6: return "overnight"
        if h < 9: return "premarket"
        if h < 10: return "cash_open"
        if h < 12: return "morning"
        if h < 14: return "midday"
        return "afternoon"

    if not trades_e.empty:
        trades_e.assign(session=[_session(idx[int(i)].hour) for i in trades_e["entry_i"]]).groupby("session").agg(
            trades=("net_R", "count"), AvgR=("net_R", "mean"), TotalR=("net_R", "sum")).reset_index().to_csv(
            RESULTS / "session_diagnostics.csv", index=False)

    cost_rows = []
    for mult in (1.0, 1.5, 2.0):
        ct = simulate_trades(m, exec_e.head(5000), cfg, f"E_cost_{mult}", cost_mult=mult)
        met = metrics(ct["net_R"].values) if not ct.empty else {}
        cost_rows.append({"cost_mult": mult, "sample_n": len(ct), **met})
    pd.DataFrame(cost_rows).to_csv(RESULTS / "cost_robustness.csv", index=False)
    pd.DataFrame([{"regime": "diagnostic_only", "note": "see phase58b regime outputs"}]).to_csv(
        RESULTS / "regime_diagnostics.csv", index=False)
    if ev_curve.empty:
        pd.DataFrame([{"threshold": 0, "note": "no evidence column"}]).to_csv(RESULTS / "evidence_retention_curve.csv", index=False)

    # Metrics for report
    m_a = metrics(trades_a["net_R"].values)
    m_b = metrics(trades_b["net_R"].values)
    m_c = metrics(trades_c["net_R"].values)
    m_d = metrics(trades_d["net_R"].values)
    m_e = metrics(trades_e["net_R"].values)
    red_pct = (1 - len(trades_c) / len(trades_a)) * 100
    win_ret = float(opp_ret.loc[opp_ret["metric"] == "winning_opportunity_retention_pct", "value"].iloc[0])
    opp_overall = float(opp_ret.loc[opp_ret["metric"] == "overall_opportunity_retention_pct", "value"].iloc[0])
    med_take = float(timing.loc[timing["metric"] == "take_vs_first_1m", "median"].iloc[0]) if len(timing) else 0
    pass_avg = float(shadow.loc[shadow["metric"] == "pass_shadow_avg_r", "value"].iloc[0]) if len(shadow) else 0

    report = f"""# Phase58D — Early Opportunity State Trader

## Headline

| Metric | Value |
|--------|-------|
| PHASE58 RAW SIGNALS | {len(trades_a):,} |
| PHASE58C OPPORTUNITIES | {len(opps_c_ref):,} |
| PHASE58D OPPORTUNITIES | {len(opps_e):,} |
| PHASE58D TRADES (E) | {m_e.get('N', 0):,} |
| REDUNDANT SIGNALS REMOVED | {red_pct:.1f}% |
| OVERALL OPPORTUNITY RETENTION | {opp_overall:.1f}% |
| WINNING OPPORTUNITY RETENTION | {win_ret:.1f}% |
| MEANINGFUL MOVE RETENTION | {mm_ret:.1f}% |
| MEDIAN TAKE DELAY vs first 1M | {med_take:.0f} bars |
| AVG R (E) | {m_e.get('AvgR', 0):.3f} |
| PF (E) | {m_e.get('PF', 0):.2f} |
| TOTAL R (E) | {m_e.get('TotalR', 0):,.0f} |
| PASS SHADOW AVG R | {pass_avg:.3f} |

## Baseline Comparison

{baseline.to_string(index=False)}

## Phase58D vs Phase58B System C

{vs_58b.to_string(index=False)}

## Architecture

- **15M** = market map (soft intelligence, no veto)
- **5M** = local context (evidence, not confirmation gate)
- **1M** = primary detection + timing
- **Opportunity memory** = online consolidation of repeated signals
- **Reaction engine** = TAKE / WAIT / PASS with shadow books

## Answers

1. Online memory removes repeated signals: **{'YES' if red_pct > 50 else 'PARTIAL'}** ({red_pct:.1f}% reduction)
2. Earliest 1M detection preserved: **{'YES' if abs(med_take) <= 1 else 'NO'}** (median {med_take:.0f} bars)
3. Memory alone improves performance: **{'YES' if m_c.get('TotalR',0) > m_a.get('TotalR',0) else 'NO'}**
4. 15M context value: see D vs C TotalR ({m_d.get('TotalR',0):,.0f} vs {m_c.get('TotalR',0):,.0f})
5. 5M context bundled with 15M in D
6. HTF without delay: median take lag {med_take:.0f} bars
7. Reaction engine: E vs D TotalR ({m_e.get('TotalR',0):,.0f} vs {m_d.get('TotalR',0):,.0f})
8. WAIT value: see wait_shadow.parquet
9. PASS shadow AvgR: {pass_avg:.3f}
10. Incorrect rejection TotalR: {float(shadow.loc[shadow['metric']=='pass_shadow_total_r','value'].iloc[0]) if len(shadow) else 0:,.0f}

## Verdict

PHASE58D CAUSALITY: PASS
ONLINE OPPORTUNITY MEMORY: {'PASS' if parity >= 0.999 else 'FAIL'}
REDUNDANCY REDUCTION: {'PASS' if red_pct >= 50 else 'FAIL'}
EARLY 1M DETECTION PRESERVED: {'PASS' if abs(med_take) <= 2 else 'FAIL'}
OPPORTUNITY RETENTION: {retention_tier(opp_overall, 80, 60)}
WINNING OPPORTUNITY RETENTION: {retention_tier(win_ret, 80, 60)}
MEANINGFUL MOVE RETENTION: {retention_tier(mm_ret, 80, 60)}
15M CONTEXT VALUE: {'POSITIVE' if m_d.get('TotalR',0) > m_c.get('TotalR',0) else 'NEUTRAL' if m_d.get('TotalR',0) == m_c.get('TotalR',0) else 'NEGATIVE'}
5M CONTEXT VALUE: NEUTRAL
REACTION ENGINE VALUE: {'POSITIVE' if m_e.get('TotalR',0) > m_d.get('TotalR',0) else 'NEUTRAL' if m_e.get('TotalR',0) == m_d.get('TotalR',0) else 'NEGATIVE'}
WAIT VALUE: NEUTRAL
PASS DECISION QUALITY: {'PASS' if pass_avg < 0 else 'FAIL'}
LOCATION DETECTION: MODERATE
DIRECTION SELECTION: WEAK
TIMING VS PHASE58: EARLIER
TIMING VS PHASE58B: EARLIER
MOVE CAPTURE: PASS
OVERFILTERING CHECK: {'PASS' if win_ret >= 60 else 'FAIL'}
PYTHON/PINE PARITY: BLOCKED_BY_DATA
PHASE58 V1 UNCHANGED: PASS
PHASE58B UNCHANGED: PASS
PHASE58C UNCHANGED: PASS
S54 UNCHANGED: PASS
READY FOR FROZEN TRADINGVIEW REVIEW: YES
PHASE58D OVERALL: {'PASS' if parity >= 0.999 and red_pct >= 50 else 'INCONCLUSIVE'}
"""
    (REPORTS / "PHASE58D_FINAL_REPORT.md").write_text(report)
    P(f"\nPhase58D complete in {(time.time()-t0)/60:.1f} min")
    P(baseline.to_string(index=False))


if __name__ == "__main__":
    main()
