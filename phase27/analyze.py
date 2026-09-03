"""Phase 27 walk-forward order-flow edge analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from phase17.analysis_core import max_drawdown
from phase26.labels import build_path_labels

from .config import (
    NQ_DOLLARS_PER_POINT,
    PRECISION_FRACTIONS,
    PRIMARY_HORIZON_BARS,
    PRIMARY_LOSS_ATR,
    PRIMARY_PROFIT_ATR,
    RESULTS,
    RISK_ATR_FOR_COST,
    ROUND_TURN_COST_USD,
    WALK_FORWARD_FOLDS,
)
from .process_trades import aggregate_flow_to_5m, add_price_response, build_ohlcv_control, load_pilot_5m, load_trades


def gross_r(hit: bool, net_atr: float) -> float:
    if hit:
        return PRIMARY_PROFIT_ATR / PRIMARY_LOSS_ATR
    if net_atr <= -PRIMARY_LOSS_ATR * 0.99:
        return -1.0
    return float(net_atr / PRIMARY_LOSS_ATR)


def net_r(g: float, atr: float, *, cost_mult: float = 1.0) -> float:
    cost = (ROUND_TURN_COST_USD * cost_mult) / (RISK_ATR_FOR_COST * atr * NQ_DOLLARS_PER_POINT)
    return g - cost


def _pipe() -> Pipeline:
    return Pipeline(
        [
            ("imp", SimpleImputer(strategy="median")),
            ("sc", StandardScaler()),
            ("clf", ExtraTreesClassifier(n_estimators=200, max_depth=8, min_samples_leaf=50, class_weight="balanced", random_state=27, n_jobs=-1)),
        ]
    )


def performance(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return {"N": 0}
    r = df["net_r"].astype(float)
    gp, gl = r[r > 0].sum(), abs(r[r < 0].sum())
    return {
        "N": len(df),
        "target_hit_rate": float(df["target_hit"].mean()),
        "Avg_MFE": float(df["mfe_atr"].mean()),
        "Avg_MAE": float(df["mae_atr"].mean()),
        "MFE_MAE": float((df["mfe_atr"] / df["mae_atr"].replace(0, np.nan)).mean()),
        "gross_AvgR": float(df["gross_r"].mean()),
        "net_AvgR": float(r.mean()),
        "net_TotalR": float(r.sum()),
        "net_PF": float(gp / gl) if gl > 0 else float("inf"),
        "MaxDD": float(max_drawdown(r.to_numpy())),
    }


def walk_forward_models(dataset: pd.DataFrame, ohlcv_cols: List[str], flow_cols: List[str]) -> Dict[str, pd.DataFrame]:
    outputs = {}
    tz = dataset.index.tz
    for name, cols in (("A_ohlcv", ohlcv_cols), ("B_flow", flow_cols), ("C_combined", ohlcv_cols + flow_cols)):
        rows = []
        for train_start, train_end, val_start, val_end in WALK_FORWARD_FOLDS:
            train = dataset.loc[(dataset.index >= pd.Timestamp(train_start, tz=tz)) & (dataset.index <= pd.Timestamp(train_end, tz=tz))]
            val = dataset.loc[(dataset.index >= pd.Timestamp(val_start, tz=tz)) & (dataset.index <= pd.Timestamp(val_end, tz=tz))]
            if len(train) < 500 or len(val) < 200:
                continue
            use_cols = [c for c in cols if c in train.columns]
            for side, target in (("long", "long_primary_hit"), ("short", "short_primary_hit")):
                pipe = _pipe()
                pipe.fit(train[use_cols], train[target].astype(int))
                prob = pipe.predict_proba(val[use_cols])[:, 1]
                for ts, p in zip(val.index, prob):
                    rows.append({"timestamp": ts, "model": name, "side": side, "p_hit": float(p), "fold_val_end": val_end})
        outputs[name] = pd.DataFrame(rows)
    return outputs


def stitch_predictions(dataset: pd.DataFrame, preds: pd.DataFrame) -> pd.DataFrame:
    long_p = preds.loc[preds.side == "long"].set_index("timestamp")[["p_hit", "model"]].rename(columns={"p_hit": "p_long"})
    short_p = preds.loc[preds.side == "short"].set_index("timestamp")[["p_hit"]].rename(columns={"p_hit": "p_short"})
    merged = long_p.join(short_p, how="outer")
    merged["edge_score"] = merged[["p_long", "p_short"]].max(axis=1)
    merged["direction"] = np.where(merged["p_long"] >= merged["p_short"], "LONG", "SHORT")
    out = merged.reset_index().merge(dataset.reset_index().rename(columns={"index": "timestamp"}), on="timestamp", how="left")
    out["target_hit"] = np.where(out["direction"] == "LONG", out["long_primary_hit"], out["short_primary_hit"])
    out["mfe_atr"] = np.where(out["direction"] == "LONG", out["long_mfe_atr"], out["short_mfe_atr"])
    out["mae_atr"] = np.where(out["direction"] == "LONG", out["long_mae_atr"], out["short_mae_atr"])
    out["net_atr"] = np.where(out["direction"] == "LONG", out["long_net_atr"], out["short_net_atr"])
    out["gross_r"] = [gross_r(bool(h), float(n)) for h, n in zip(out["target_hit"], out["net_atr"])]
    out["net_r"] = [net_r(g, float(a)) for g, a in zip(out["gross_r"], out["atr"].fillna(out.get("atr_frozen", np.nan)))]
    return out


def precision_curve(stitched: pd.DataFrame, baseline_rate: float) -> pd.DataFrame:
    ordered = stitched.sort_values("edge_score", ascending=False)
    rows = []
    n = len(ordered)
    days = max((ordered["timestamp"].max() - ordered["timestamp"].min()).days, 1)
    for frac in PRECISION_FRACTIONS:
        keep = max(1, int(n * frac))
        sub = ordered.iloc[:keep]
        perf = performance(sub)
        perf["top_fraction"] = frac
        perf["signals_per_day"] = keep / days
        perf["precision_lift_pp"] = (perf.get("target_hit_rate", 0) - baseline_rate) * 100
        rows.append(perf)
    return pd.DataFrame(rows)


def classify(inc_auc: float, top10_lift: float, top10_net: float, mono: float) -> str:
    if top10_net >= 0.10 and top10_lift >= 7 and mono > 0.3:
        return "A"
    if top10_net > 0.05 and top10_lift >= 4 and inc_auc >= 0.02:
        return "B"
    if top10_lift >= 2 or inc_auc >= 0.01:
        return "C"
    return "D"


def run_phase27(*, trades_path: Path, output: Path = RESULTS) -> Dict:
    output.mkdir(parents=True, exist_ok=True)
    trades = load_trades(trades_path)
    market = load_pilot_5m()
    flow = aggregate_flow_to_5m(trades, market.index)
    flow = add_price_response(flow, market)
    ohlcv = build_ohlcv_control(market)
    labels = build_path_labels(market)
    dataset = ohlcv.join(flow).join(labels).join(market[["atr", "close", "high", "low"]])
    dataset = dataset.loc[dataset["eligible"]].copy()
    dataset.to_csv(output / "order_flow_features.csv")

    ohlcv_cols = list(build_ohlcv_control(market).columns)
    flow_cols = [c for c in flow.columns if c in dataset.columns]
    model_preds = walk_forward_models(dataset, ohlcv_cols, flow_cols)

    comp_rows = []
    stitched_all = {}
    baseline = float(dataset["long_primary_hit"].mean())  # direction-specific handled per model
    for name, preds in model_preds.items():
        if preds.empty:
            continue
        stitched = stitch_predictions(dataset, preds)
        stitched_all[name] = stitched
        prec = precision_curve(stitched, baseline_rate=float(stitched["target_hit"].mean()))
        prec.to_csv(output / f"precision_curve_{name}.csv", index=False)
        top10 = prec.loc[prec["top_fraction"] == 0.10]
        top5 = prec.loc[prec["top_fraction"] == 0.05]
        top1 = prec.loc[prec["top_fraction"] == 0.01]
        try:
            auc = roc_auc_score(stitched["target_hit"].astype(int), stitched["edge_score"])
            brier = brier_score_loss(stitched["target_hit"].astype(int), stitched["edge_score"])
        except ValueError:
            auc, brier = np.nan, np.nan
        comp_rows.append(
            {
                "model": name,
                "AUC": auc,
                "Brier": brier,
                "top10_hit_rate": float(top10["target_hit_rate"].iloc[0]) if len(top10) else np.nan,
                "top5_hit_rate": float(top5["target_hit_rate"].iloc[0]) if len(top5) else np.nan,
                "top1_hit_rate": float(top1["target_hit_rate"].iloc[0]) if len(top1) else np.nan,
                "top10_net_AvgR": float(top10["net_AvgR"].iloc[0]) if len(top10) else np.nan,
                **performance(stitched),
            }
        )
    comp = pd.DataFrame(comp_rows)
    comp.to_csv(output / "model_comparison.csv", index=False)

    # primary stitched = combined model C
    primary = stitched_all.get("C_combined", pd.DataFrame())
    if not primary.empty:
        primary.to_csv(output / "walk_forward_predictions.csv", index=False)
        deciles = primary.copy()
        deciles["decile"] = pd.qcut(deciles["edge_score"].rank(method="first"), 10, labels=False) + 1
        dec_rows = [performance(g) | {"decile": int(d)} for d, g in deciles.groupby("decile")]
        pd.DataFrame(dec_rows).to_csv(output / "score_deciles.csv", index=False)
        prec = precision_curve(primary, baseline_rate=float(primary["target_hit"].mean()))
        prec.to_csv(output / "precision_curve.csv", index=False)
        mono = pd.DataFrame(dec_rows)["net_AvgR"].corr(pd.DataFrame(dec_rows)["decile"]) if dec_rows else 0
    else:
        mono = 0

    if len(comp) >= 2 and "A_ohlcv" in comp.model.values and "C_combined" in comp.model.values:
        inc_auc = float(comp.loc[comp.model == "C_combined", "AUC"].iloc[0] - comp.loc[comp.model == "A_ohlcv", "AUC"].iloc[0])
        top10_lift = (float(comp.loc[comp.model == "C_combined", "top10_hit_rate"].iloc[0]) - float(comp.loc[comp.model == "A_ohlcv", "top10_hit_rate"].iloc[0])) * 100
        top10_net = float(comp.loc[comp.model == "C_combined", "top10_net_AvgR"].iloc[0])
    else:
        inc_auc, top10_lift, top10_net = 0.0, 0.0, -999.0

    final = classify(inc_auc, top10_lift, top10_net, mono if np.isfinite(mono) else 0)

    manifest = {
        "phase": "Phase 27",
        "microstructure_events": len(trades),
        "decision_points": len(dataset),
        "unconditional_long_rate": float(dataset["long_primary_hit"].mean()),
        "unconditional_short_rate": float(dataset["short_primary_hit"].mean()),
        "model_comparison": comp.to_dict("records"),
        "incremental_auc_C_minus_A": inc_auc,
        "incremental_top10_lift_pp": top10_lift,
        "score_monotonicity": "NO" if mono < 0.2 else "PARTIAL" if mono < 0.5 else "YES",
        "final_classification": final,
        "pilot_passed": final in {"A", "B"},
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    (output / "data_validation.md").write_text(
        f"# Data validation\n\nTrade rows: {len(trades):,}\n5m bars: {len(market):,}\nEligible: {len(dataset):,}\n"
        f"Buy/sell sides present: B/A counts validated at ingest.\n"
    )
    (output / "ORDER_FLOW_ENTRY_EDGE_REPORT.md").write_text(
        f"# Order Flow Entry Edge Report\n\nClassification: **{final}**\n\nSee model_comparison.csv and data_cost_audit.md.\n"
    )
    return manifest
