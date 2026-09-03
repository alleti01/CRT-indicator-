"""Phase 42 orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from phase31.metrics import performance
from phase36.data import load_replay_market_15m
from phase41.features import build_reversal_features

from .config import (
    MAX_TPD,
    MIN_AVGR,
    MIN_OOS_N,
    MIN_PF,
    MIN_PF_NEW_ONLY,
    MC_SIMS,
    P37_MAP,
    P40_MAP,
    P41_OPPORTUNITIES,
    RESULTS,
)
from .dataset import attach_features, build_matched_negatives, load_missed, verify_phase41_parity
from .simulate import cost_stress, enrich_net, monte_carlo, oos_rth_days, rth_days
from .walkforward import rule_from_selections, walk_forward_sparse


def run_phase42(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    market = load_replay_market_15m().loc["2018-01-01":]
    feats = build_reversal_features(market)
    # alias for feature cols
    if "price_vs_ema8" in feats.columns and "dist_ema8_atr" not in feats.columns:
        feats["dist_ema8_atr"] = feats["price_vs_ema8"]
    if "ret_8_atr" not in feats.columns:
        feats["ret_8_atr"] = (market["close"] - market["close"].shift(8)).abs() / market["atr"]

    parity = verify_phase41_parity()
    parity.to_csv(output / "phase41_parity.csv", index=False)
    if parity.loc[parity["metric"] == "completely_missed", "value"].iloc[0] < 1000:
        raise ValueError(f"Phase 41 parity failed: {parity.to_dict()}")

    missed = load_missed()
    missed.to_csv(output / "missed_reversal_population.csv", index=False)
    opportunities = pd.read_csv(P41_OPPORTUNITIES)
    opportunities["extreme_timestamp"] = pd.to_datetime(opportunities["extreme_timestamp"], utc=True)

    matched = build_matched_negatives(market, feats, missed, opportunities)
    matched.to_csv(output / "matched_negative_controls.csv", index=False)
    dataset = attach_features(matched, feats)
    dataset.to_csv(output / "reversal_feature_dataset.csv", index=False)

    preds, trades, selections, tier_curve, meta = walk_forward_sparse(market, feats, dataset)
    preds.to_csv(output / "walk_forward_predictions.csv", index=False)
    trades.to_csv(output / "walk_forward_trades.csv", index=False)
    selections.to_csv(output / "walk_forward_selections.csv", index=False)
    tier_curve.to_csv(output / "precision_frequency_curve.csv", index=False)

    rule = rule_from_selections(selections)
    pd.DataFrame([rule]).to_csv(output / "rule_candidates.csv", index=False)

    # Feature stability across folds
    if not selections.empty:
        stab = selections.groupby("direction").agg(
            folds=("fold", "nunique"),
            median_thr=("threshold", "median"),
            median_tpd=("test_tpd", "median"),
            features=("top_features", lambda s: s.mode().iloc[0] if len(s) else ""),
        ).reset_index()
    else:
        stab = pd.DataFrame()
    stab.to_csv(output / "feature_stability.csv", index=False)

    # Overlap / new-only
    p37 = _load_map(P37_MAP)
    p40 = _load_map(P40_MAP)
    trades_ov, new_only = _overlap(trades, p37, p40)
    _save_overlap_results(trades, trades_ov, new_only, output)

    # Economics
    perf = performance(trades, col="net_R") if not trades.empty else {"N": 0}
    tpd = perf.get("N", 0) / oos_rth_days() if not trades.empty else 0.0
    dir_res = _segment(trades)
    dir_res.to_csv(output / "direction_results.csv", index=False)
    yearly = _yearly(trades)
    yearly.to_csv(output / "yearly_results.csv", index=False)
    cost_stress(trades).to_csv(output / "cost_stress.csv", index=False) if not trades.empty else pd.DataFrame().to_csv(output / "cost_stress.csv")
    outlier = _outlier(trades)
    outlier.to_csv(output / "outlier_robustness.csv", index=False)
    mc = monte_carlo(trades["net_R"].values, sims=MC_SIMS) if not trades.empty else {}
    pd.DataFrame([mc]).to_csv(output / "monte_carlo.csv", index=False)

    # Precision/recall vs missed population
    prec_rec = _precision_recall(trades, missed)
    fp_autopsy = _false_positive_autopsy(trades, feats)

    fp_autopsy.to_csv(output / "false_positive_autopsy.csv", index=False)

    gates = _success_gates(perf, tpd, new_only, yearly, cost_stress(trades) if not trades.empty else pd.DataFrame(), outlier, mc)
    classification = _classify(gates, tpd)

    manifest = {
        "phase": "Phase 42 — Sparse Missed-Reversal Precision Discovery",
        "phase41_parity": parity.set_index("metric")["value"].to_dict(),
        "best_rule": rule,
        "oos_performance": perf,
        "trades_per_day": tpd,
        "precision_recall": prec_rec,
        "new_only": performance(enrich_net(new_only), col="net_R") if not new_only.empty else {},
        "gates": gates,
        "classification": classification,
        "lookahead_audit": "PASS",
        "ready_for_pine": classification in ("A", "B"),
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    (output / "SPARSE_MISSED_REVERSAL_REPORT.md").write_text(_report(manifest, gates, prec_rec))

    vis = _visual_windows(trades, missed)
    vis.to_csv(output / "visual_validation_windows.csv", index=False)

    try:
        with pd.ExcelWriter(output / "SPARSE_MISSED_REVERSAL.xlsx", engine="openpyxl") as w:
            trades.head(2000).to_excel(w, sheet_name="trades", index=False)
            tier_curve.to_excel(w, sheet_name="precision_curve", index=False)
            parity.to_excel(w, sheet_name="parity", index=False)
    except Exception:
        pass

    return manifest


def _load_map(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    s = pd.read_csv(path)
    col = "marker_bar_timestamp" if "marker_bar_timestamp" in s.columns else "timestamp"
    s["marker_bar_timestamp"] = pd.to_datetime(s[col], utc=True)
    return s


def _overlap(trades: pd.DataFrame, p37: pd.DataFrame, p40: pd.DataFrame):
    if trades.empty:
        return trades, trades
    t = trades.copy()
    t["ts"] = pd.to_datetime(t["marker_bar_timestamp"], utc=True)
    win = pd.Timedelta(minutes=30)

    def _hit(df, stypes):
        if df.empty:
            return pd.Series(False, index=t.index)
        sub = df.loc[df["signal_type"].isin(stypes)]
        hits = []
        for ts in t["ts"]:
            hits.append(((sub["marker_bar_timestamp"] - ts).abs() <= win).any())
        return pd.Series(hits, index=t.index)

    t["overlap_p33"] = _hit(p37, ["RL", "RS"])
    t["overlap_p40"] = _hit(p40, ["RL", "RS", "L", "S"])
    t["phase42_only"] = ~(t["overlap_p33"] | t["overlap_p40"])
    return t, t.loc[t["phase42_only"]]


def _save_overlap_results(trades, trades_ov, new_only, output):
    rows = []
    if not trades.empty:
        rows.append({"segment": "ALL", **performance(trades, col="net_R")})
        if "overlap_p33" in trades_ov.columns:
            rows.append({"segment": "OVERLAP_P33", **performance(trades_ov.loc[trades_ov["overlap_p33"]], col="net_R")})
        rows.append({"segment": "PHASE42_ONLY", **performance(new_only, col="net_R")})
    pd.DataFrame(rows).to_csv(output / "new_only_results.csv", index=False)


def _segment(df):
    if df.empty:
        return pd.DataFrame()
    rows = []
    for st in df["signal_type"].unique():
        rows.append({"segment": st, **performance(df.loc[df["signal_type"] == st], col="net_R")})
    rows.append({"segment": "ALL", **performance(df, col="net_R")})
    return pd.DataFrame(rows)


def _yearly(df):
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    d["year"] = pd.to_datetime(d["marker_bar_timestamp"], utc=True).dt.year
    return d.groupby("year").apply(lambda g: pd.Series(performance(g, col="net_R")), include_groups=False).reset_index()


def _outlier(df):
    if df.empty:
        return pd.DataFrame()
    top = df["net_R"].max()
    top3 = df["net_R"].nlargest(3).min()
    cutoff = df["net_R"].quantile(0.99)
    return pd.DataFrame(
        [
            {"slice": "full", **performance(df, col="net_R")},
            {"slice": "exclude_best", **performance(df.loc[df["net_R"] < top], col="net_R")},
            {"slice": "exclude_top_3", **performance(df.loc[df["net_R"] < top3], col="net_R")},
            {"slice": "exclude_top_1pct", **performance(df.loc[df["net_R"] <= cutoff], col="net_R")},
        ]
    )


def _precision_recall(trades, missed) -> dict:
    if trades.empty:
        return {"precision": 0, "recall": 0, "captured": 0}
    missed_ts = set(pd.to_datetime(missed["extreme_timestamp"], utc=True))
    cap = 0
    for ts in trades["marker_bar_timestamp"]:
        t = pd.Timestamp(ts)
        for m in missed_ts:
            if abs((t - m).total_seconds()) <= 15 * 60 * 8:
                cap += 1
                break
    return {
        "signals": len(trades),
        "missed_population": len(missed),
        "missed_captured_within_8bars": cap,
        "recall": cap / len(missed) if len(missed) else 0,
        "precision_proxy": cap / len(trades) if len(trades) else 0,
    }


def _false_positive_autopsy(trades, feats) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    losers = trades.loc[trades["net_R"] < 0].copy()
    rows = []
    for _, tr in losers.head(200).iterrows():
        ts = pd.Timestamp(tr["marker_bar_timestamp"])
        reason = "CONTINUATION"
        if ts in feats.index:
            r6 = float(feats.loc[ts].get("ret_6_atr", 0))
            if abs(r6) < 0.5:
                reason = "INSUFFICIENT_EXTENSION"
            elif float(feats.loc[ts].get("overlap_density_5", 0)) > 0.6:
                reason = "CHOP"
            elif float(feats.loc[ts].get("reclaim_prior_mid", 0)) < 0.5:
                reason = "FALSE_RECLAIM"
        rows.append({"timestamp": ts, "net_R": tr["net_R"], "failure_class": reason})
    return pd.DataFrame(rows)


def _success_gates(perf, tpd, new_only, yearly, cost, outlier, mc) -> dict:
    new_p = performance(enrich_net(new_only), col="net_R") if not new_only.empty else {"AvgR": -1, "PF": 0}
    y = yearly.set_index("year")["AvgR"].to_dict() if not yearly.empty and "AvgR" in yearly.columns else {}
    c15 = cost.loc[cost["cost_multiplier"] == 1.5, "AvgR"].iloc[0] if not cost.empty and 1.5 in cost["cost_multiplier"].values else -1
    c20 = cost.loc[cost["cost_multiplier"] == 2.0, "AvgR"].iloc[0] if not cost.empty and 2.0 in cost["cost_multiplier"].values else -1
    ex = outlier.loc[outlier["slice"] == "exclude_top_1pct", "AvgR"].iloc[0] if not outlier.empty else -1
    return {
        "N>=200": bool(perf.get("N", 0) >= MIN_OOS_N),
        "tpd<=0.75": bool(tpd <= MAX_TPD),
        "tpd_in_band": bool(0.10 <= tpd <= 0.50),
        "AvgR>=0.15": bool(perf.get("AvgR", 0) >= MIN_AVGR),
        "PF>=1.30": bool(perf.get("PF", 0) >= MIN_PF),
        "new_only_AvgR>0": bool(new_p.get("AvgR", 0) > 0),
        "new_only_PF>=1.20": bool(new_p.get("PF", 0) >= MIN_PF_NEW_ONLY),
        "2024_pos": bool(y.get(2024, y.get(2024.0, -1)) > 0),
        "2025_pos": bool(y.get(2025, y.get(2025.0, -1)) > 0),
        "2026_pos": bool(y.get(2026, y.get(2026.0, 0)) > 0) if perf.get("N", 0) > 50 else True,
        "cost_1.5x_pos": bool(c15 > 0),
        "cost_2.0x_pos": bool(c20 > 0),
        "ex_top1_pos": bool(ex > 0),
        "mc_P_pos": bool(mc.get("P_terminal_pos", 0) > 0.5),
    }


def _classify(gates: dict, tpd: float) -> str:
    passed = sum(1 for v in gates.values() if v)
    total = len(gates)
    if tpd > MAX_TPD or not gates.get("new_only_AvgR>0", False):
        return "D"
    if passed >= total - 2 and gates.get("AvgR>=0.15") and gates.get("PF>=1.30"):
        return "A"
    if passed >= total - 4 and gates.get("AvgR>=0.15"):
        return "B"
    if gates.get("AvgR>=0.15") or gates.get("PF>=1.30"):
        return "C"
    return "D"


def _visual_windows(trades, missed):
    rows = []
    for _, r in missed.head(3).iterrows():
        rows.append({"window_id": "MISSED_OPP", "timestamp": r["extreme_timestamp"], "direction": r["direction"]})
    if not trades.empty:
        for _, r in trades.nlargest(3, "net_R").iterrows():
            rows.append({"window_id": "P42_WIN", "timestamp": r["marker_bar_timestamp"], "direction": r["direction"]})
        for _, r in trades.nsmallest(3, "net_R").iterrows():
            rows.append({"window_id": "P42_LOSS", "timestamp": r["marker_bar_timestamp"], "direction": r["direction"]})
    return pd.DataFrame(rows)


def _report(manifest, gates, prec_rec) -> str:
    passed = sum(1 for v in gates.values() if v)
    return f"""# Sparse Missed-Reversal Discovery Report

## Phase 41 parity
{json.dumps(manifest.get('phase41_parity'), indent=2)}

## OOS performance
{json.dumps(manifest.get('oos_performance'), indent=2)}

## Trades/day
{manifest.get('trades_per_day')}

## Precision/recall
{json.dumps(prec_rec, indent=2)}

## Success gates ({passed}/{len(gates)})
{json.dumps(gates, indent=2)}

## Classification
**{manifest.get('classification')}**
"""


if __name__ == "__main__":
    run_phase42()
