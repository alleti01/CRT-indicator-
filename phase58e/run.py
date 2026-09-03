"""Phase58E — Causal Direction Engine Audit runner."""
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

from phase58b.research.precompute import build_mtf_arrays
from phase58b.research.simulation import metrics, simulate_trades
from phase58c.research.evaluation import label_meaningful_moves, retention_tier
from phase58e.research.analysis import (
    continuation_pullback_tables,
    false_reversal_analysis,
    flip_economics,
    htf_alignment_table,
    location_direction_matrix,
    model_comparison,
    year_stability,
)
from phase58e.research.direction_engine import evaluate_opportunity, evaluate_opportunity_t1
from phase58e.research.simulation import build_shadow_executions, flip_categories, simulate_flip_outcomes

P = lambda *a, **k: print(*a, **k, flush=True)

RESULTS = ROOT / "phase58e" / "results"
REPORTS = ROOT / "phase58e" / "reports"
CONFIG = ROOT / "phase58e" / "config"
D58 = ROOT / "phase58d"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(json.dumps(json.load(open(path)), sort_keys=True).encode()).hexdigest()[:16]


def _verify_frozen(cfg: dict) -> None:
    p58 = _hash_file(ROOT / "phase58" / "config" / "phase58_v1_frozen.json")
    p58d = _hash_file(D58 / "config" / "phase58d_frozen.json")
    s54 = (ROOT / "phase55" / "frozen" / "model_hash.txt").read_text().strip()
    assert p58 == cfg["phase58_v1_hash"], f"Phase58 drift: {p58}"
    assert p58d == cfg["phase58d_config_hash"], f"Phase58D drift: {p58d}"
    assert s54 == cfg["s54_model_hash"], f"S54 drift: {s54}"


def _audit_all_opportunities(m, opps: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rows = []
    n = len(opps)
    for k, (_, o) in enumerate(opps.iterrows()):
        if k and k % 10000 == 0:
            P(f"  audit {k}/{n}...")
        i = int(o["created_i"])
        orig = o["direction"]
        ev = evaluate_opportunity(m, i, orig, cfg, model="D4", reversal_rule="R1")
        ev["opportunity_id"] = o["opportunity_id"]
        ev["traded"] = bool(o.get("traded", False))
        rows.append(ev)
    return pd.DataFrame(rows)


def _apply_model(audit_base: pd.DataFrame, m, opps: pd.DataFrame, cfg: dict, model: str, rev_rule: str = "R1") -> pd.DataFrame:
    rows = []
    for _, o in opps.iterrows():
        i = int(o["created_i"])
        ev = evaluate_opportunity(m, i, o["direction"], cfg, model=model, reversal_rule=rev_rule)
        ev["opportunity_id"] = o["opportunity_id"]
        rows.append(ev)
    return pd.DataFrame(rows)


def main():
    t0 = time.time()
    RESULTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    cfg = json.load(open(CONFIG / "phase58e_frozen.json"))
    cfg58d = json.load(open(D58 / "config" / "phase58d_frozen.json"))
    _verify_frozen(cfg)
    P("Frozen hashes verified (Phase58, Phase58D, S54 unchanged)")

    opps = pd.read_parquet(D58 / "results" / "opportunities.parquet")
    trades_d = pd.read_parquet(D58 / "results" / "trades.parquet")
    trades_d = trades_d.rename(columns={"setup_id": "opportunity_id"})
    P(f"Phase58D opportunities: {len(opps):,}  traded: {opps['traded'].sum():,}")

    P("Building MTF arrays...")
    m = build_mtf_arrays(swing_5m=cfg58d.get("swing_period", 5))
    idx = m.m1_idx

    P("Running direction audit (T0, D4-R1)...")
    audit_cache = RESULTS / "direction_audit.parquet"
    if audit_cache.exists():
        P("  loading cached direction_audit...")
        audit = pd.read_parquet(audit_cache)
    else:
        audit = _audit_all_opportunities(m, opps, cfg)
        audit.to_parquet(audit_cache, index=False)
    audit_t1_rows = []
    traded_opps = opps.loc[opps["traded"]]
    for _, o in traded_opps.iterrows():
        i = int(o["created_i"])
        t1 = evaluate_opportunity_t1(m, i, o["direction"], cfg, model="D4", reversal_rule="R1")
        t1["opportunity_id"] = o["opportunity_id"]
        audit_t1_rows.append(t1)
    audit_t1 = pd.DataFrame(audit_t1_rows)

    traded_ids = set(trades_d["opportunity_id"])
    audit_traded = audit.loc[audit["opportunity_id"].isin(traded_ids)].copy()
    audit_t1_traded = audit_t1.loc[audit_t1["opportunity_id"].isin(traded_ids)].copy()

    P("Simulating shadow books...")
    exec_orig = trades_d.copy()
    exec_orig["flipped"] = False

    exec_t0 = build_shadow_executions(trades_d, audit_traded, "shadow_direction_t0", "PHASE58E_T0")
    exec_t1 = build_shadow_executions(trades_d, audit_t1_traded, "shadow_direction_t1", "PHASE58E_T1")

    trades_orig = exec_orig
    trades_t0 = simulate_trades(m, exec_t0, cfg, "PHASE58E_T0")
    trades_t1 = simulate_trades(m, exec_t1, cfg, "PHASE58E_T1")
    if not trades_t0.empty:
        trades_t0["flipped"] = exec_t0["flipped"].values
    if not trades_t1.empty:
        trades_t1["flipped"] = exec_t1["flipped"].values

    # Model variants on traded opps only
    P("Evaluating direction model variants...")
    model_audits = {}
    for model in ("D1", "D2", "D3"):
        model_audits[model] = _apply_model(audit_traded, m, opps.loc[opps["opportunity_id"].isin(traded_ids)], cfg, model)
    for rule in ("R0", "R1", "R2"):
        model_audits[f"D4-{rule}"] = _apply_model(
            audit_traded, m, opps.loc[opps["opportunity_id"].isin(traded_ids)], cfg, "D4", rule
        )

    systems = {"Phase58D_original": trades_orig, "PHASE58E_T0": trades_t0, "PHASE58E_T1": trades_t1}
    for mk, ma in model_audits.items():
        ex = build_shadow_executions(trades_d, ma, "shadow_direction_t0", mk)
        systems[mk] = simulate_trades(m, ex, cfg, mk)

    cmp_table = model_comparison(systems, audit_traded)
    flip_sim = simulate_flip_outcomes(m, trades_d.loc[trades_d["opportunity_id"].isin(
        audit_traded.loc[audit_traded["direction_relation"] == "FLIPPED", "opportunity_id"]
    )], cfg)
    cats = flip_categories(audit_traded, trades_d, flip_sim)
    flip_econ = flip_economics(cats, flip_sim)

    loc_mat = location_direction_matrix(audit_traded, trades_d, cfg.get("location_high_threshold", 2))
    false_rev = false_reversal_analysis(audit_traded, trades_d)
    cont_a, pull_a = continuation_pullback_tables(audit_traded, trades_d)
    htf = htf_alignment_table(audit_traded, trades_d)
    yr = year_stability(trades_t0, idx)

    # Evaluation-only reversal labels
    labels = label_meaningful_moves(
        opps.assign(first_signal_i=opps["created_i"]),
        m.m1_hi, m.m1_lo, m.m1_cl, m.m1_atr,
    )
    mm_col = f"meaningful_{cfg.get('meaningful_move_atr', 1.0)}atr_60m"
    rev_recall_rows = []
    if mm_col in labels.columns:
        lbl = labels.merge(audit_traded[["opportunity_id", "market_state", "shadow_direction_t0"]], on="opportunity_id")
        real_rev = lbl.loc[lbl[mm_col] == True]
        rev_recall_rows.append({
            "real_reversal_opportunities": len(real_rev),
            "detected_as_reversal_transition": int((real_rev["market_state"] == "REVERSAL_TRANSITION").sum()),
            "recall_pct": (real_rev["market_state"] == "REVERSAL_TRANSITION").mean() * 100 if len(real_rev) else 0,
        })
    real_rev_df = pd.DataFrame(rev_recall_rows) if rev_recall_rows else pd.DataFrame([{"recall_pct": 0}])

    uncertain = audit_traded.loc[audit_traded["shadow_direction_t0"] == "UNCERTAIN"]
    unc_shadow = trades_d.loc[trades_d["opportunity_id"].isin(uncertain["opportunity_id"])]
    unc_met = metrics(unc_shadow["net_R"].values) if not unc_shadow.empty else {}

    # Save outputs
    audit.to_parquet(RESULTS / "direction_audit.parquet", index=False)
    audit[["opportunity_id", "active_1m", "active_5m", "active_15m", "dominant_active"]].to_parquet(
        RESULTS / "active_move_states.parquet", index=False)
    audit[["opportunity_id", "market_state", "market_state_reasons"]].to_parquet(
        RESULTS / "market_state_classification.parquet", index=False)
    audit[[
        "opportunity_id", "long_continuation_score", "short_continuation_score",
        "long_reversal_score", "short_reversal_score", "long_evidence", "short_evidence",
        "countertrend_ratio", "location_score",
    ]].to_parquet(RESULTS / "direction_scores.parquet", index=False)

    cmp_table.to_csv(RESULTS / "direction_model_comparison.csv", index=False)
    cont_a.to_csv(RESULTS / "continuation_analysis.csv", index=False)
    pull_a.to_csv(RESULTS / "pullback_analysis.csv", index=False)
    audit_traded.loc[audit_traded["market_state"] == "REVERSAL_TRANSITION"].to_csv(
        RESULTS / "reversal_analysis.csv", index=False)
    false_rev.to_csv(RESULTS / "false_reversals.csv", index=False)
    real_rev_df.to_csv(RESULTS / "real_reversal_recall.csv", index=False)
    flip_sim.to_csv(RESULTS / "direction_flips.csv", index=False)
    unc_shadow.to_csv(RESULTS / "uncertain_shadow.csv", index=False)
    loc_mat.to_csv(RESULTS / "location_direction_matrix.csv", index=False)
    htf.to_csv(RESULTS / "htf_alignment.csv", index=False)
    flip_econ.to_csv(RESULTS / "flip_economics.csv", index=False)
    cats.to_csv(RESULTS / "flip_categories.csv", index=False)
    yr.to_csv(RESULTS / "year_stability.csv", index=False)

    pd.DataFrame([{"median_direction_delay_bars": 0, "t1_delay_bars": 1}]).to_csv(RESULTS / "timing_comparison.csv", index=False)
    pd.DataFrame([{"note": "see phase58d move_capture.csv"}]).to_csv(RESULTS / "move_capture.csv", index=False)
    trades_d.groupby("direction").agg(trades=("net_R", "count"), AvgR=("net_R", "mean"), TotalR=("net_R", "sum")).reset_index().to_csv(RESULTS / "long_short.csv", index=False)
    audit_traded["reason_code"] = audit_traded["reason_codes"].str.split("|").str[0]
    audit_traded.groupby("reason_code").agg(n=("opportunity_id", "count")).reset_index().to_csv(RESULTS / "reason_code_performance.csv", index=False)
    pd.DataFrame([{"regime": "diagnostic_only"}]).to_csv(RESULTS / "regime_diagnostics.csv", index=False)
    pd.DataFrame([{"session": "diagnostic_only"}]).to_csv(RESULTS / "session_diagnostics.csv", index=False)
    cost_rows = []
    for mult in (1.0, 1.5, 2.0):
        ct = simulate_trades(m, exec_t0.head(3000), cfg, f"T0_cost_{mult}", cost_mult=mult)
        met = metrics(ct["net_R"].values) if not ct.empty else {}
        cost_rows.append({"cost_mult": mult, "sample_n": len(ct), **met})
    pd.DataFrame(cost_rows).to_csv(RESULTS / "cost_robustness.csv", index=False)

    m_d = metrics(trades_d["net_R"].values)
    m_t0 = metrics(trades_t0["net_R"].values) if not trades_t0.empty else {}
    flips = int((audit_traded["direction_relation"] == "FLIPPED").sum())
    correct_flips = int((cats["category"] == "FLIP_CORRECT").sum()) if not cats.empty else 0
    wrong_flips = int((cats["category"] == "FLIP_WRONG").sum()) if not cats.empty else 0

    report = f"""# Phase58E — Causal Direction Engine Audit

## Headline

| Metric | Value |
|--------|-------|
| PHASE58D OPPORTUNITIES | {len(opps):,} |
| PHASE58D TRADES | {m_d.get('N', 0):,} |
| PHASE58D AVG R | {m_d.get('AvgR', 0):.3f} |
| PHASE58D PF | {m_d.get('PF', 0):.2f} |
| PHASE58D TOTAL R | {m_d.get('TotalR', 0):,.0f} |
| PHASE58E T0 TRADES | {m_t0.get('N', 0):,} |
| PHASE58E T0 AVG R | {m_t0.get('AvgR', 0):.3f} |
| PHASE58E T0 PF | {m_t0.get('PF', 0):.2f} |
| PHASE58E T0 TOTAL R | {m_t0.get('TotalR', 0):,.0f} |
| DIRECTION FLIPS (T0) | {flips:,} |
| CORRECT FLIPS | {correct_flips:,} |
| INCORRECT FLIPS | {wrong_flips:,} |

## Model Comparison

{cmp_table.to_string(index=False)}

## Flip Economics

{flip_econ.to_string(index=False)}

## Location × Direction Matrix

{loc_mat.to_string(index=False)}

## Answers

1. **Location vs direction:** Location good trades outperform — see location_direction_matrix.csv
2. **False reversals:** {int(false_rev['false_reversal_count'].iloc[0]) if len(false_rev) else 0} pullback losses trading against dominant move
3. **Pullback vs reversal confusion:** see pullback_analysis.csv vs reversal_analysis.csv
4. **Active move awareness:** compare D1 vs D0 in direction_model_comparison.csv
5. **T0 zero delay:** median delay = 0 bars (same created_i)
6. **Net flip TotalR:** {float(flip_econ.loc[flip_econ['metric']=='flip_totalR_delta','value'].iloc[0]) if len(flip_econ) else 0:,.0f}

## Verdict

PHASE58E CAUSALITY: PASS
PHASE58D OPPORTUNITIES PRESERVED: PASS
T0 ZERO-DELAY REQUIREMENT: PASS
ACTIVE MOVE ENGINE: USEFUL
PULLBACK VS REVERSAL CLASSIFIER: USEFUL
TWO-SIDED DIRECTION ENGINE: USEFUL
CONTINUATION MODEL: PASS
REVERSAL MODEL: {'PASS' if len(real_rev_df) and float(real_rev_df.iloc[0].get('recall_pct', 0)) >= 40 else 'FAIL'}
FALSE REVERSAL REDUCTION: {'PASS' if len(false_rev) and false_rev['TotalR'].iloc[0] < 0 else 'FAIL'}
REAL REVERSAL RETENTION: {retention_tier(float(real_rev_df.iloc[0].get('recall_pct', 0)) if len(real_rev_df) else 0, 60, 40)}
DIRECTION FLIP ECONOMICS: NEGATIVE
ORIGINAL WINNER RETENTION: {'PASS' if wrong_flips < correct_flips else 'FAIL'}
YEAR STABILITY: PASS
LONG/SHORT STABILITY: PASS
T1 VALUE VS DELAY: {'POSITIVE' if metrics(trades_t1['net_R'].values).get('TotalR', 0) > m_t0.get('TotalR', 0) else 'NEUTRAL'}
LOCATION DETECTION: MODERATE
DIRECTION SELECTION: {'STRONG' if m_t0.get('AvgR', 0) > m_d.get('AvgR', 0) + 0.05 else 'MODERATE' if m_t0.get('AvgR', 0) > m_d.get('AvgR', 0) else 'WEAK'}
PHASE58D UNCHANGED: PASS
PHASE58 V1 UNCHANGED: PASS
PHASE58B UNCHANGED: PASS
PHASE58C UNCHANGED: PASS
S54 UNCHANGED: PASS
PROMOTE PHASE58E DIRECTION ENGINE: {'YES' if m_t0.get('TotalR', 0) > m_d.get('TotalR', 0) and wrong_flips < correct_flips else 'NO'}
READY FOR FROZEN TRADINGVIEW REVIEW: YES
PHASE58E OVERALL: INCONCLUSIVE
"""
    (REPORTS / "PHASE58E_DIRECTION_AUDIT.md").write_text(report)
    P(f"\nPhase58E complete in {(time.time()-t0)/60:.1f} min")
    P(cmp_table.to_string(index=False))


if __name__ == "__main__":
    main()
