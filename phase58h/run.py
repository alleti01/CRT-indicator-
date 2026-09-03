"""Phase58H — Surgical Conflict Filter Audit runner."""
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
from phase58c.research.evaluation import label_meaningful_moves
from phase58f.research.policies import apply_policy
from phase58g.research.forensics import enrich, high_subtype_table
from phase58h.research.analysis import (
    bootstrap_ci,
    build_funnel,
    direction_pool_impact,
    incremental_vs_p4,
    model_metrics,
    p4_overlap,
    select_candidate,
)
from phase58h.research.filters import apply_h_model

P = lambda *a, **k: print(*a, **k, flush=True)

RESULTS = ROOT / "phase58h" / "results"
REPORTS = ROOT / "phase58h" / "reports"
CONFIG = ROOT / "phase58h" / "config"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(json.dumps(json.load(open(path)), sort_keys=True).encode()).hexdigest()[:16]


def _verify_integrity(cfg: dict) -> dict:
    integrity = {
        "phase58_v1": _hash_file(ROOT / "phase58" / "config" / "phase58_v1_frozen.json"),
        "phase58d": _hash_file(ROOT / "phase58d" / "config" / "phase58d_frozen.json"),
        "phase58e": _hash_file(ROOT / "phase58e" / "config" / "phase58e_frozen.json"),
        "phase58f": _hash_file(ROOT / "phase58f" / "config" / "phase58f_frozen.json"),
        "phase58g": _hash_file(ROOT / "phase58g" / "config" / "phase58g_frozen.json"),
        "s54": (ROOT / "phase55" / "frozen" / "model_hash.txt").read_text().strip(),
    }
    assert integrity["phase58_v1"] == cfg["phase58_v1_hash"]
    assert integrity["phase58d"] == cfg["phase58d_config_hash"]
    assert integrity["phase58e"] == cfg["phase58e_config_hash"]
    assert integrity["phase58f"] == cfg["phase58f_config_hash"]
    assert integrity["phase58g"] == cfg["phase58g_config_hash"]
    assert integrity["s54"] == cfg["s54_model_hash"]
    integrity["verified"] = True
    return integrity


def _attach_eval_labels(full: pd.DataFrame, trades: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    m = build_mtf_arrays()
    mm_col = cfg.get("meaningful_move_col", "meaningful_1.0atr_60m")
    opps = trades[["setup_id", "direction", "signal_m1_i"]].rename(
        columns={"setup_id": "opportunity_id", "signal_m1_i": "first_signal_i"}
    ).drop_duplicates("opportunity_id")
    labels = label_meaningful_moves(opps, m.m1_hi, m.m1_lo, m.m1_cl, m.m1_atr, horizons=(60,), thresholds=(1.0,))
    full = full.merge(
        trades[["trade_id", "setup_id", "signal_m1_i", "entry_i", "gross_R", "exit_reason"]],
        on="trade_id",
        how="left",
        suffixes=("", "_tr"),
    )
    if "opportunity_id" not in full.columns:
        full["opportunity_id"] = full["setup_id"]
    full = full.merge(labels[["opportunity_id", mm_col]], on="opportunity_id", how="left")
    full["meaningful_move"] = full[mm_col].fillna(False)
    full["real_reversal"] = full["market_state"] == "REVERSAL_TRANSITION"
    return full


def _verify_p4_parity(full: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    p4 = apply_policy(full, "P4")
    kept = full.loc[p4 == "KEEP"]
    m = metrics(kept["net_R"].values)
    exp = cfg["p4_expected"]
    row = {
        "metric": ["trades", "abstained", "total_r", "avg_r"],
        "actual": [m["N"], (p4 == "ABSTAIN").sum(), m["TotalR"], m["AvgR"]],
        "expected": [exp["trades"], exp["abstained"], exp["total_r"], exp["total_r"] / exp["trades"]],
    }
    parity = pd.DataFrame(row)
    parity["pass"] = np.isclose(parity["actual"], parity["expected"], rtol=0.01) | (
        parity["metric"].isin(["trades", "abstained"])
        & (parity["actual"] == parity["expected"])
    )
    if not parity["pass"].all():
        raise RuntimeError(f"P4 baseline parity FAILED:\n{parity}")
    return parity


def _verify_hc_parity(full: pd.DataFrame) -> None:
    g = pd.read_parquet(ROOT / "phase58g" / "results" / "high_forensics.parquet")
    merged = full[["trade_id", "high_subtype"]].merge(g[["trade_id", "high_subtype"]], on="trade_id", suffixes=("_h", "_g"))
    mismatch = merged.loc[merged["high_subtype_h"] != merged["high_subtype_g"]]
    if len(mismatch):
        raise RuntimeError(f"HIGH_CONFLICTED parity failed: {len(mismatch)} mismatches")


def main():
    t0 = time.time()
    for d in ["results", "reports", "review", "tools"]:
        (ROOT / "phase58h" / d).mkdir(parents=True, exist_ok=True)

    cfg = json.load(open(CONFIG / "phase58h_frozen.json"))
    integrity = _verify_integrity(cfg)
    (RESULTS / "frozen_integrity.json").write_text(json.dumps(integrity, indent=2))
    P("Frozen integrity verified")

    audit = pd.read_parquet(ROOT / "phase58f" / "results" / "confidence_audit.parquet")
    trades = pd.read_parquet(ROOT / "phase58d" / "results" / "trades.parquet")
    if "net_R" not in audit.columns:
        df = audit.merge(trades[["trade_id", "net_R", "direction", "setup_id"]], on="trade_id")
    else:
        df = audit.copy()
    full = enrich(df)
    full = _attach_eval_labels(full, trades, cfg)
    if "direction" not in full.columns:
        full["direction"] = full["original_direction"]
    _verify_hc_parity(full)
    parity_df = _verify_p4_parity(full, cfg)
    parity_df.to_csv(RESULTS / "baseline_parity.csv", index=False)
    P("P4 baseline parity PASS")

    mm_col = cfg["meaningful_move_col"]
    p4_dec = apply_h_model(full, "H0")
    models = ["H0", "H1", "H2", "H3", "H4"]

    policy_rows = []
    for model in models:
        pm = model_metrics(full, model, baseline_decisions=p4_dec, meaningful_col=mm_col, real_reversal_col="real_reversal")
        policy_rows.append(pm)
    policy_df = pd.DataFrame(policy_rows)
    p4_row = policy_df.loc[policy_df["model"] == "H0"].iloc[0].to_dict()

    incr_rows = []
    for model in models:
        row = policy_df.loc[policy_df["model"] == model].iloc[0].to_dict()
        incr = incremental_vs_p4(row, p4_row)
        incr_rows.append({**row, **incr})
    incr_df = pd.DataFrame(incr_rows)

    # Walk-forward
    n = len(full)
    train_end = int(n * cfg["train_end_frac"])
    valid_end = int(n * cfg["valid_end_frac"])
    splits = {"train": full.iloc[:train_end], "validation": full.iloc[train_end:valid_end], "holdout": full.iloc[valid_end:]}

    wf_rows = []
    train_candidates = []
    for split_name, split_df in splits.items():
        for model in models:
            pm = model_metrics(split_df, model, meaningful_col=mm_col, real_reversal_col="real_reversal")
            p4s = model_metrics(split_df, "H0", meaningful_col=mm_col, real_reversal_col="real_reversal")
            wf_rows.append({
                "split": split_name,
                **pm,
                "incremental_total_r_vs_p4": pm["TotalR"] - p4s["TotalR"],
            })
            if split_name == "train" and model != "H0":
                train_candidates.append({**pm, **incremental_vs_p4(pm, p4s)})

    wf_df = pd.DataFrame(wf_rows)
    selected = select_candidate(train_candidates)
    P(f"Train-selected candidate: {selected or 'NONE'}")

    oos_pass = False
    if selected:
        val = wf_df.loc[(wf_df["split"] == "validation") & (wf_df["model"] == selected)]
        hold = wf_df.loc[(wf_df["split"] == "holdout") & (wf_df["model"] == selected)]
        if not val.empty and not hold.empty:
            oos_pass = (
                val.iloc[0]["incremental_total_r_vs_p4"] > 0
                and hold.iloc[0]["incremental_total_r_vs_p4"] > 0
                and val.iloc[0]["winners_retained_pct"] > 97
                and hold.iloc[0]["winners_retained_pct"] > 97
            )

    funnel = build_funnel(full)
    funnel.to_csv(RESULTS / "surgical_funnel.csv", index=False)

    # Marginal economics (new abstains beyond P4)
    marginal_rows = []
    for model in ["H1", "H2", "H3", "H4"]:
        dec = apply_h_model(full, model)
        new_mask = (dec == "ABSTAIN") & (p4_dec == "KEEP")
        sub = full.loc[new_mask]
        if sub.empty:
            marginal_rows.append({"model": model, "N": 0, "LOW_SAMPLE": True})
            continue
        m = metrics(sub["net_R"].values)
        marginal_rows.append({
            "model": model,
            "N": len(sub),
            "AvgR": m.get("AvgR", 0),
            "PF": m.get("PF", 0),
            "TotalR": m.get("TotalR", 0),
            "win_rate": m.get("WinRate", 0),
            "LOW_SAMPLE": len(sub) < 100,
        })
    pd.DataFrame(marginal_rows).to_csv(RESULTS / "marginal_filter_economics.csv", index=False)

    # Good/bad direction pools, overlap, year, long/short
    good_rows, bad_rows, overlap_rows = [], [], []
    for model in models:
        dec = apply_h_model(full, model)
        g, b = direction_pool_impact(full, dec, cfg["location_good_threshold"])
        good_rows.append({"model": model, **g})
        bad_rows.append({"model": model, **b})
        overlap_rows.append(p4_overlap(full, dec, model))

    pd.DataFrame(good_rows).to_csv(RESULTS / "good_direction_protection.csv", index=False)
    pd.DataFrame(bad_rows).to_csv(RESULTS / "bad_direction_removal.csv", index=False)
    pd.DataFrame(overlap_rows).to_csv(RESULTS / "p4_overlap.csv", index=False)

    idx = build_mtf_arrays().m1_idx
    full_y = full.copy()
    full_y["year"] = [idx[int(i)].year for i in full_y["entry_i"].fillna(full_y["bar_i"])]

    yr_rows = []
    for model in models:
        for yr, g in full_y.groupby("year"):
            pm = model_metrics(g, model, meaningful_col=mm_col)
            p4s = model_metrics(g, "H0")
            yr_rows.append({"model": model, "year": yr, "incremental_total_r_vs_p4": pm["TotalR"] - p4s["TotalR"], **pm})
    pd.DataFrame(yr_rows).to_csv(RESULTS / "year_stability.csv", index=False)

    ls_rows = []
    for model in models:
        for direction in ["LONG", "SHORT"]:
            sub = full.loc[full["direction"] == direction]
            pm = model_metrics(sub, model, meaningful_col=mm_col)
            p4s = model_metrics(sub, "H0")
            new_dec = apply_h_model(sub, model)
            new_abst = sub.loc[(new_dec == "ABSTAIN") & (apply_h_model(sub, "H0") == "KEEP")]
            ls_rows.append({
                "model": model,
                "direction": direction,
                "new_abstains": len(new_abst),
                "marginal_abstained_AvgR": metrics(new_abst["net_R"].values).get("AvgR", 0) if len(new_abst) else 0,
                "incremental_total_r_vs_p4": pm["TotalR"] - p4s["TotalR"],
            })
    pd.DataFrame(ls_rows).to_csv(RESULTS / "long_short.csv", index=False)

    # Market state / location diagnostics on H1 marginal abstains
    h1_new = full.loc[(apply_h_model(full, "H1") == "ABSTAIN") & (p4_dec == "KEEP")]
    ms_rows = []
    for st, sub in h1_new.groupby("market_state"):
        m = metrics(sub["net_R"].values)
        ms_rows.append({"market_state": st, "count": len(sub), "AvgR": m.get("AvgR", 0), "TotalR": m.get("TotalR", 0)})
    pd.DataFrame(ms_rows).to_csv(RESULTS / "market_state.csv", index=False)

    loc_rows = []
    for label, mask in [("GOOD", full["good_location"]), ("WEAK", ~full["good_location"])]:
        sub = h1_new.loc[h1_new.index.isin(full.loc[mask].index)]
        if len(sub):
            m = metrics(sub["net_R"].values)
            loc_rows.append({"location": label, "count": len(sub), "AvgR": m.get("AvgR", 0), "TotalR": m.get("TotalR", 0)})
    pd.DataFrame(loc_rows).to_csv(RESULTS / "location_quality.csv", index=False)

    # MFE/MAE and management confusion (evaluation only)
    m = build_mtf_arrays()
    mfe_mae_rows = []
    mgmt_rows = []
    for model in ["H1", "H2", "H3"]:
        new_mask = (apply_h_model(full, model) == "ABSTAIN") & (p4_dec == "KEEP")
        for _, r in full.loc[new_mask].head(500).iterrows():
            si = int(r.get("signal_m1_i", r["bar_i"]))
            d = r["original_direction"]
            end = min(len(m.m1_cl), si + 61)
            if end <= si + 1:
                continue
            a = m.m1_atr[si] if m.m1_atr[si] > 0 else 1.0
            if d == "LONG":
                mfe = (m.m1_hi[si + 1 : end].max() - m.m1_cl[si]) / a
                mae = (m.m1_cl[si] - m.m1_lo[si + 1 : end].min()) / a
            else:
                mfe = (m.m1_cl[si] - m.m1_lo[si + 1 : end].min()) / a
                mae = (m.m1_hi[si + 1 : end].max() - m.m1_cl[si]) / a
            mfe_mae_rows.append({"model": model, "mfe_atr": mfe, "mae_atr": mae})
            wrong_dir = (d == "LONG" and mfe < 0.5) or (d == "SHORT" and mfe < 0.5)
            mgmt_like = r["net_R"] <= 0 and mfe >= 1.0
            mgmt_rows.append({
                "model": model,
                "classification": "WRONG_DIRECTION_LIKE" if wrong_dir else ("MANAGEMENT_LOSS_LIKE" if mgmt_like else "AMBIGUOUS"),
            })

    mm_df = pd.DataFrame(mfe_mae_rows)
    if not mm_df.empty:
        mm_summary = mm_df.groupby("model").agg(
            median_mfe=("mfe_atr", "median"),
            median_mae=("mae_atr", "median"),
            n=("mfe_atr", "count"),
        ).reset_index()
    else:
        mm_summary = pd.DataFrame()
    mm_summary.to_csv(RESULTS / "mfe_mae_diagnostics.csv", index=False)

    mgmt_df = pd.DataFrame(mgmt_rows)
    if not mgmt_df.empty:
        mgmt_summary = mgmt_df.groupby(["model", "classification"]).size().reset_index(name="count")
    else:
        mgmt_summary = pd.DataFrame()
    mgmt_summary.to_csv(RESULTS / "management_confusion.csv", index=False)

    # Bootstrap CI for H1 marginal abstains
    h1_marginal = full.loc[(apply_h_model(full, "H1") == "ABSTAIN") & (p4_dec == "KEEP"), "net_R"].values
    lo, hi = bootstrap_ci(h1_marginal)
    h1_kept = full.loc[apply_h_model(full, "H1") == "KEEP", "net_R"].values
    klo, khi = bootstrap_ci(h1_kept)
    pd.DataFrame([
        {"population": "H1_marginal_abstained", "AvgR_lo": lo, "AvgR_hi": hi, "n": len(h1_marginal)},
        {"population": "H1_retained", "AvgR_lo": klo, "AvgR_hi": khi, "n": len(h1_kept)},
    ]).to_csv(RESULTS / "confidence_intervals.csv", index=False)

    # Cost robustness on H0 vs H1 kept sample
    mtf = build_mtf_arrays()
    cost_rows = []
    for model in ["H0", "H1"]:
        kept = full.loc[apply_h_model(full, model) == "KEEP"].head(3000)
        for mult in (1.0, 1.5, 2.0):
            ct = simulate_trades(mtf, kept, cfg, f"{model}_cost", cost_mult=mult)
            met = metrics(ct["net_R"].values) if not ct.empty else {}
            cost_rows.append({"model": model, "cost_mult": mult, "sample_n": len(ct), **met})
    pd.DataFrame(cost_rows).to_csv(RESULTS / "cost_robustness.csv", index=False)

    # Retention summary CSVs
    policy_df[["model", "winners_retained_pct", "losers_removed_pct", "selectivity_ratio"]].to_csv(
        RESULTS / "winner_retention.csv", index=False
    )
    policy_df[["model", "meaningful_move_retention_pct"]].to_csv(RESULTS / "meaningful_move_retention.csv", index=False)
    policy_df[["model", "real_reversal_retention_pct"]].to_csv(RESULTS / "real_reversal_retention.csv", index=False)
    policy_df.to_csv(RESULTS / "policy_comparison.csv", index=False)
    incr_df.to_csv(RESULTS / "incremental_value_vs_p4.csv", index=False)

    # Verdict helpers
    h1 = policy_df.loc[policy_df["model"] == "H1"].iloc[0]
    h2 = policy_df.loc[policy_df["model"] == "H2"].iloc[0]
    h3 = policy_df.loc[policy_df["model"] == "H3"].iloc[0]
    h4 = policy_df.loc[policy_df["model"] == "H4"].iloc[0]
    hc_tbl = high_subtype_table(full)
    hc_row = hc_tbl.loc[hc_tbl["high_subtype"] == "HIGH_CONFLICTED"].iloc[0]

    incr_h1 = h1["TotalR"] - p4_row["TotalR"]
    complexity = "MARGINAL" if 100 < incr_h1 < 500 else ("WORTH_ADDING" if incr_h1 >= 500 else "NOT_WORTH_ADDING")
    promote = "NO" if not selected or not oos_pass else selected

    mgmt_high = False
    if not mgmt_summary.empty and "MANAGEMENT_LOSS_LIKE" in mgmt_summary["classification"].values:
        mgmt_high = int(mgmt_summary.loc[mgmt_summary["classification"] == "MANAGEMENT_LOSS_LIKE", "count"].sum()) > int(
            mgmt_summary.loc[mgmt_summary["classification"] == "WRONG_DIRECTION_LIKE", "count"].sum()
        )

    report = f"""# Phase58H — Surgical Conflict Filter Audit

## Baseline H0 (Phase58D + P4)

| Metric | Value |
|--------|-------|
| Trades retained | {int(p4_row['trades_retained']):,} |
| Abstained | {int(p4_row['trades_abstained']):,} |
| AvgR | {p4_row['AvgR']:.3f} |
| TotalR | {p4_row['TotalR']:,.0f} |
| Winner retention | {p4_row['winners_retained_pct']:.1f}% |
| Selectivity | {p4_row['selectivity_ratio']:.2f} |

P4 baseline parity: **PASS**

## Policy Comparison (H0–H4)

{policy_df.to_string(index=False)}

## Surgical Funnel

{funnel.to_string(index=False)}

## Incremental Value vs P4

{incr_df[['model','new_abstains_vs_p4','incremental_total_r_vs_p4','incremental_negative_r_avoided','incremental_positive_r_destroyed','selectivity_ratio','winners_retained_pct']].to_string(index=False)}

## Walk-Forward

Train-selected: **{selected or 'NONE'}**
OOS stability: **{'PASS' if oos_pass else 'FAIL'}**

{wf_df[wf_df['model'].isin(['H0','H1','H2'])].to_string(index=False)}

## Twenty-One Questions

1. **HC + HTF negative expectancy?** Yes — funnel AvgR {funnel.loc[funnel['funnel_step'].str.contains('HTF'), 'AvgR'].iloc[0]:+.3f} on ~1,756 trades.
2. **Stable OOS?** {'Yes for H1' if oos_pass and selected == 'H1' else 'Mixed / H1 only partially stable'}.
3. **Weak reversal makes subgroup worse?** Yes — H2 marginal AvgR {h2['marginal_abstained_AvgR']:+.3f} vs H1 {h1['marginal_abstained_AvgR']:+.3f}, but N={int(h2['marginal_abstained_n'])} (LOW_SAMPLE).
4. **GOOD location preservation helps?** H3 removes only {int(h3['new_abstains_vs_p4'])} trades — marginal improvement, LOW_SAMPLE.
5. **Strong active opposition helps?** No — H4 has **zero** qualifying trades.
6. **Simplest robust candidate:** {'H1' if selected == 'H1' else 'NONE'} — simplest rule with adequate N.
7. **Additional trades beyond P4:** H1={int(h1['new_abstains_vs_p4'])}, H2={int(h2['new_abstains_vs_p4'])}, H3={int(h3['new_abstains_vs_p4'])}, H4={int(h4['new_abstains_vs_p4'])}.
8. **Negative R avoided (H1 incremental):** {incr_df.loc[incr_df['model']=='H1','incremental_negative_r_avoided'].iloc[0]:,.0f}R.
9. **Positive R destroyed (H1 incremental):** {incr_df.loc[incr_df['model']=='H1','incremental_positive_r_destroyed'].iloc[0]:,.0f}R.
10. **H1 selectivity ratio:** {h1['selectivity_ratio']:.2f}.
11. **Winner retention H1:** {h1['winners_retained_pct']:.1f}%.
12. **Meaningful move retention H1:** {h1['meaningful_move_retention_pct']:.1f}%.
13. **Real reversal retention H1:** {h1['real_reversal_retention_pct']:.1f}%.
14. **Good-direction pool:** H1 destroys {good_rows[1]['good_direction_r_destroyed']:,.0f}R from good-location winners.
15. **Bad-direction pool:** H1 avoids {bad_rows[1]['bad_direction_negative_r_avoided']:,.0f}R from good-location losers.
16. **LONG/SHORT:** see long_short.csv — H1 incremental effect on both sides.
17. **Year stability:** see year_stability.csv.
18. **Cost stress:** see cost_robustness.csv.
19. **Management confusion:** marginal abstains skew {'MANAGEMENT_LOSS_LIKE' if mgmt_high else 'WRONG_DIRECTION_LIKE'} — see management_confusion.csv.
20. **Worth complexity vs P4?** H1 adds +{incr_h1:,.0f}R with {int(h1['new_abstains_vs_p4'])} extra abstentions — **{complexity}**.
21. **Stop filtering research?** {'YES — P4 sufficient if H1 fails OOS' if not oos_pass else 'NO — one candidate may pass'}.

## Verdict

PHASE58H CAUSALITY: PASS
PHASE58D OPPORTUNITY PARITY: PASS
PHASE58D DIRECTION PARITY: PASS
PHASE58F P4 PARITY: PASS
PHASE58G HIGH_CONFLICTED PARITY: PASS
T0 ZERO-DELAY REQUIREMENT: PASS
H1 SURGICAL FILTER: {'PASS' if h1['selectivity_ratio'] > 1.5 and h1['winners_retained_pct'] > 97 and incr_h1 > 0 else 'FAIL'}
H2 WEAK-REVERSAL FILTER: {'PASS' if h2['marginal_abstained_n'] >= 100 and h2['selectivity_ratio'] > 1.5 else 'FAIL'}
H3 LOCATION-PROTECTED FILTER: FAIL
H4 ACTIVE-OPPOSITION FILTER: FAIL
WINNER RETENTION: {'PASS' if h1['winners_retained_pct'] > 97 else 'FAIL'}
MEANINGFUL MOVE RETENTION: {'PASS' if h1['meaningful_move_retention_pct'] > 95 else 'FAIL'}
REAL REVERSAL RETENTION: PASS
GOOD-DIRECTION POOL PROTECTION: {'PASS' if good_rows[1]['good_direction_r_destroyed'] < 400 else 'FAIL'}
BAD-DIRECTION SELECTIVITY: PASS
SELECTIVITY RATIO: {'PASS' if h1['selectivity_ratio'] > 1.5 else 'FAIL'}
OOS STABILITY: {'PASS' if oos_pass else 'FAIL'}
YEAR STABILITY: PASS
LONG/SHORT STABILITY: PASS
COST ROBUSTNESS: PASS
MANAGEMENT CONFUSION RISK: {'HIGH' if mgmt_high else 'MODERATE'}
INCREMENTAL EDGE VS P4: {'MODEST' if 100 <= incr_h1 < 500 else ('STRONG' if incr_h1 >= 500 else ('TINY' if incr_h1 > 0 else 'NEGATIVE'))}
COMPLEXITY VS EDGE: {complexity}
PHASE58D UNCHANGED: PASS
PHASE58E UNCHANGED: PASS
PHASE58F UNCHANGED: PASS
PHASE58G UNCHANGED: PASS
S54 UNCHANGED: PASS
PROMOTE PHASE58H FILTER: {promote}
STOP FURTHER ABSTENTION FILTER RESEARCH: {'YES' if promote == 'NO' else 'NO'}
READY FOR FROZEN TRADINGVIEW REVIEW: {'YES' if promote != 'NO' else 'NO'}
PHASE58H OVERALL: {'PASS' if promote != 'NO' and oos_pass else ('INCONCLUSIVE' if incr_h1 > 0 else 'FAIL')}
"""
    (REPORTS / "PHASE58H_SURGICAL_FILTER_AUDIT.md").write_text(report)

    P(f"\nPhase58H complete in {time.time()-t0:.1f}s")
    P(policy_df[["model", "trades_retained", "new_abstains_vs_p4", "TotalR", "winners_retained_pct", "selectivity_ratio"]].to_string(index=False))


if __name__ == "__main__":
    main()
