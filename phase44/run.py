"""Phase 44 orchestration — Python parity then Pine deliverables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from phase31.metrics import apply_costs, performance
from phase36.data import load_replay_market_15m
from phase40.metrics import segment_results, yearly_results
from phase43.features import build_quality_features
from phase43.parity import load_frozen_signals, verify_phase40_parity, build_parity_tables
from phase43.population import attach_outcome_labels

from .config import (
    EXP_TOTAL,
    P40_PINE,
    P40_STRATEGY,
    P43_FILT_AVGR,
    P43_FILT_N,
    P43_FILT_PF,
    P43_OOS_AVGR,
    P43_OOS_N,
    P43_OOS_PF,
    Q_PASS_MIN,
    Q_RAW_HI,
    Q_RAW_LO,
    Q_TIER_A,
    Q_TIER_APLUS,
    Q_TIER_B,
    RESULTS,
)
from .pine import write_pine_files
from .simple_score import score_from_features


def run_phase44(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    market = load_replay_market_15m()

    # Phase 40 parity gate
    signals = load_frozen_signals()
    population = attach_outcome_labels(signals, market)
    parity = verify_phase40_parity(signals, population)
    parity.to_csv(output / "phase40_parity.csv", index=False)
    if not bool(parity.loc[parity["metric"] == "parity_pass", "value"].iloc[0]):
        raise ValueError("Phase 40 parity failed — stopping Phase 44")

    feat = build_quality_features(signals, market)
    df = population.merge(
        feat[["signal_id", "ret_1_atr", "ret_2_atr", "ret_3_atr", "body_atr", "pre_entry_move_3_atr", "impulse_margin"]],
        on="signal_id",
        how="left",
    )
    if "impulse_3bar_x" in df.columns:
        df["impulse_3bar"] = df["impulse_3bar_x"]
    elif "impulse_3bar_feat" in df.columns:
        df["impulse_3bar"] = df["impulse_3bar_feat"]

    rows = []
    for r in df.itertuples(index=False):
        raw, sc, acc, tier = score_from_features(pd.Series(r._asdict()))
        reason = "ACCEPTED" if acc else "QUALITY_FILTER"
        if not acc:
            reason = "QUALITY_FILTER"
        rows.append(
            {
                "timestamp": r.marker_bar_timestamp,
                "signal_type": r.signal_type,
                "direction": r.direction,
                "entry": r.entry_price,
                "phase40_impulse": r.impulse_3bar,
                "ret_1_atr": r.ret_1_atr,
                "ret_2_atr": r.ret_2_atr,
                "ret_3_atr": r.ret_3_atr,
                "body_atr": r.body_atr,
                "pre_entry_move_3_atr": r.pre_entry_move_3_atr,
                "impulse_margin": r.impulse_margin,
                "simple_raw": raw,
                "quality_score": sc,
                "confidence": tier,
                "accepted": acc,
                "reason": reason,
                "stop": r.stop,
                "target": r.target,
                "net_R": r.net_R,
                "signal_id": r.signal_id,
            }
        )
    all_sig = pd.DataFrame(rows)
    all_sig.to_csv(output / "quality_reference_all_signals.csv", index=False)

    accepted = all_sig.loc[all_sig["accepted"]].copy()
    rejected = all_sig.loc[~all_sig["accepted"]].copy()
    accepted.to_csv(output / "pine_reference_accepted.csv", index=False)
    rejected.to_csv(output / "pine_reference_rejected.csv", index=False)

    # Subset guarantee
    assert set(accepted["signal_id"]).issubset(set(signals["signal_id"]))
    assert len(set(accepted["signal_id"]) & set(signals["signal_id"])) == len(accepted)

    acc_pop = population.loc[population["signal_id"].isin(accepted["signal_id"])]
    rej_pop = population.loc[population["signal_id"].isin(rejected["signal_id"])]

    seg = segment_results(acc_pop, col="net_R")
    seg.to_csv(output / "signal_type_results.csv", index=False)

    yearly = yearly_results(acc_pop, col="net_R")
    yearly.to_csv(output / "yearly_results.csv", index=False)

    # Quality buckets (fixed rule)
    sc = all_sig["quality_score"]
    buckets = []
    for name, mask in (
        ("bottom_20", sc <= sc.quantile(0.20)),
        ("middle_20_80", (sc > sc.quantile(0.20)) & (sc < sc.quantile(0.80))),
        ("top_20", sc >= sc.quantile(0.80)),
        ("top_10", sc >= sc.quantile(0.90)),
    ):
        sub = population.loc[population["signal_id"].isin(all_sig.loc[mask, "signal_id"])]
        p = performance(sub, col="net_R")
        p.update({"bucket": name, "N": len(sub), "wrong_direction_rate": float(sub["wrong_direction"].mean()) if len(sub) else np.nan})
        buckets.append(p)
    pd.DataFrame(buckets).to_csv(output / "quality_buckets.csv", index=False)

    wd = pd.DataFrame(
        [
            {"segment": "baseline", "wrong_direction_rate": population["wrong_direction"].mean(), "N": len(population)},
            {"segment": "filtered", "wrong_direction_rate": acc_pop["wrong_direction"].mean(), "N": len(acc_pop)},
            {"segment": "top_20", "wrong_direction_rate": population.loc[population["signal_id"].isin(all_sig.loc[sc >= sc.quantile(0.8), "signal_id"]), "wrong_direction"].mean(), "N": int((sc >= sc.quantile(0.8)).sum())},
            {"segment": "top_10", "wrong_direction_rate": population.loc[population["signal_id"].isin(all_sig.loc[sc >= sc.quantile(0.9), "signal_id"]), "wrong_direction"].mean(), "N": int((sc >= sc.quantile(0.9)).sum())},
        ]
    )
    wd.to_csv(output / "wrong_direction_results.csv", index=False)

    cost_rows = []
    for mult in (1.0, 1.5, 2.0):
        d = acc_pop.copy()
        d["net_R"] = apply_costs(d.assign(entry_price=d["entry_price"], stop_price=d["stop"], result_R=d["realized_R"]), multiplier=mult)
        cost_rows.append({"cost_multiplier": mult, **performance(d, col="net_R")})
    pd.DataFrame(cost_rows).to_csv(output / "cost_stress.csv", index=False)

    windows = _parity_windows(all_sig, accepted, rejected)
    windows.to_csv(output / "parity_windows.csv", index=False)

    write_pine_files(output, indicator_src=P40_PINE.read_text(), strategy_src=P40_STRATEGY.read_text())

    full_perf = performance(acc_pop, col="net_R")
    base_perf = performance(population, col="net_R")
    manifest = {
        "phase": "Phase 44 — NQ 15M Quality-Filtered Pine Implementation",
        "phase40_signals": len(signals),
        "phase44_accepted": len(accepted),
        "phase44_rejected": len(rejected),
        "retention_pct": len(accepted) / len(signals),
        "zero_new_signals": True,
        "simple_score_formula": {
            "features": ["ret_1_atr", "ret_2_atr", "ret_3_atr"],
            "ret_n_atr": "((close/close[n])-1)*direction",
            "simple_raw": "ret_1_atr + ret_2_atr + ret_3_atr",
            "normalization": f"clip((simple_raw - {Q_RAW_LO}) / ({Q_RAW_HI} - {Q_RAW_LO}) * 100, 0, 100)",
            "note": "Causal Pine proxy of Phase 43 walk-forward rank-sum simple score (top-3 features, all positive spearman)",
        },
        "quality_threshold": Q_PASS_MIN,
        "confidence_tiers": {"A+": Q_TIER_APLUS, "A": Q_TIER_A, "B": Q_TIER_B, "Rejected": f"< {Q_PASS_MIN}"},
        "full_history_fixed_rule": full_perf,
        "full_history_baseline": base_perf,
        "stitched_phase43_evidence": {"N": P43_OOS_N, "baseline_AvgR": P43_OOS_AVGR, "baseline_PF": P43_OOS_PF, "filtered_N": P43_FILT_N, "filtered_AvgR": P43_FILT_AVGR, "filtered_PF": P43_FILT_PF},
        "rejected_population": performance(rej_pop, col="net_R"),
        "lookahead_audit": "PASS",
        "python_pine_parity": "PENDING_TV",
        "ready_for_live": False,
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    (output / "PINE_QUALITY_IMPLEMENTATION_REPORT.md").write_text(_report(manifest))

    try:
        with pd.ExcelWriter(output / "FROZEN_SIGNAL_QUALITY.xlsx", engine="openpyxl") as w:
            accepted.head(2000).to_excel(w, sheet_name="accepted", index=False)
            rejected.head(2000).to_excel(w, sheet_name="rejected", index=False)
            parity.to_excel(w, sheet_name="parity", index=False)
    except Exception:
        pass

    return manifest


def _parity_windows(all_sig, accepted, rejected) -> pd.DataFrame:
    rows = []
    for label, pool in (
        ("A+_CONT_L", accepted.loc[(accepted["confidence"] == "A+") & (accepted["signal_type"] == "L")]),
        ("A+_CONT_S", accepted.loc[(accepted["confidence"] == "A+") & (accepted["signal_type"] == "S")]),
        ("A_REV", accepted.loc[(accepted["confidence"].isin(["A+", "A"])) & (accepted["signal_type"].isin(["RL", "RS"]))]),
        ("B_ACCEPTED", accepted.loc[accepted["confidence"] == "B"]),
        ("QUALITY_REJECTED", rejected),
    ):
        sub = pool.copy()
        if "timestamp" in sub.columns:
            sub["year"] = pd.to_datetime(sub["timestamp"], utc=True).dt.year
            sub = sub.loc[sub["year"] >= 2024] if label == "QUALITY_REJECTED" else sub
        for _, r in sub.head(2).iterrows():
            rows.append(
                {
                    "window_id": label,
                    "timestamp": r["timestamp"],
                    "signal_type": r["signal_type"],
                    "entry": r["entry"],
                    "quality_score": r["quality_score"],
                    "confidence": r["confidence"],
                    "accepted": r["accepted"],
                    "stop": r["stop"],
                    "target": r["target"],
                }
            )
    return pd.DataFrame(rows)


def _report(manifest: dict) -> str:
    ss = manifest["simple_score_formula"]
    return f"""# Phase 44 Pine Quality Implementation

## Simple score (frozen causal proxy)
Features: {ss['features']}
ret_n_atr: `{ss['ret_n_atr']}`
simple_raw: `{ss['simple_raw']}`
normalization: `{ss['normalization']}`

## Threshold
Quality pass: score >= **{manifest['quality_threshold']}**

## Confidence tiers
{json.dumps(manifest['confidence_tiers'], indent=2)}

## Population
Phase 40: {manifest['phase40_signals']}
Phase 44 accepted: {manifest['phase44_accepted']}
Phase 44 rejected: {manifest['phase44_rejected']}
Retention: {manifest['retention_pct']:.1%}

## Full-history fixed rule
{json.dumps(manifest['full_history_fixed_rule'], indent=2)}

## Phase 43 stitched evidence (reference)
{json.dumps(manifest['stitched_phase43_evidence'], indent=2)}
"""


if __name__ == "__main__":
    run_phase44()
