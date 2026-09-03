"""Walk-forward analysis and reporting for Phase 26."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from phase17.analysis_core import max_drawdown

from .config import (
    NQ_DOLLARS_PER_POINT,
    PRECISION_FRACTIONS,
    PRIMARY_LOSS_ATR,
    RESULTS,
    RISK_ATR_FOR_COST,
    ROUND_TURN_COST_USD,
    WALK_FORWARD_FOLDS,
)


FEATURE_EXCLUDE = {"atr_frozen", "close_frozen", "eligible"}


def gross_r_from_label(hit: bool, net_atr: float) -> float:
    if hit:
        return 1.0 / PRIMARY_LOSS_ATR  # +1 ATR / 0.5 ATR risk = 2R
    if net_atr <= -PRIMARY_LOSS_ATR * 0.99:
        return -1.0
    return float(net_atr / PRIMARY_LOSS_ATR)


def net_r(gross: float, atr: float) -> float:
    risk_pts = RISK_ATR_FOR_COST * atr
    cost = ROUND_TURN_COST_USD / (risk_pts * NQ_DOLLARS_PER_POINT)
    return gross - cost


def feature_columns(df: pd.DataFrame) -> List[str]:
    return [
        c
        for c in df.columns
        if c not in FEATURE_EXCLUDE
        and not c.startswith(("long_", "short_"))
        and df[c].dtype in ("float64", "int64", "float32", "int32", "bool")
    ]


def _model() -> Pipeline:
    return Pipeline(
        [
            ("imp", SimpleImputer(strategy="median")),
            ("sc", StandardScaler()),
            (
                "clf",
                ExtraTreesClassifier(
                    n_estimators=200,
                    max_depth=8,
                    min_samples_leaf=200,
                    max_features="sqrt",
                    class_weight="balanced",
                    random_state=26,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def walk_forward_predictions(dataset: pd.DataFrame) -> pd.DataFrame:
    feats = feature_columns(dataset)
    tz = dataset.index.tz
    rows = []
    for train_start, train_end, val_start, val_end in WALK_FORWARD_FOLDS:
        train = dataset.loc[(dataset.index >= pd.Timestamp(train_start, tz=tz)) & (dataset.index <= pd.Timestamp(train_end, tz=tz))]
        val = dataset.loc[(dataset.index >= pd.Timestamp(val_start, tz=tz)) & (dataset.index <= pd.Timestamp(val_end, tz=tz))]
        train = train.loc[train["eligible"]]
        val = val.loc[val["eligible"]]
        if len(train) < 5000 or len(val) < 1000:
            continue
        for side, target in (("long", "long_primary_hit"), ("short", "short_primary_hit")):
            pipe = _model()
            pipe.fit(train[feats], train[target].astype(int))
            prob = pipe.predict_proba(val[feats])[:, 1]
            for idx, p in zip(val.index, prob):
                rows.append({"timestamp": idx, "side": side, "p_hit": float(p), "fold_val_end": val_end})
    wide = pd.DataFrame(rows)
    if wide.empty:
        return wide
    long_p = wide.loc[wide.side == "long"].set_index("timestamp")[["p_hit", "fold_val_end"]].rename(columns={"p_hit": "p_long"})
    short_p = wide.loc[wide.side == "short"].set_index("timestamp")[["p_hit"]].rename(columns={"p_hit": "p_short"})
    merged = long_p.join(short_p, how="outer")
    merged["edge_score"] = merged[["p_long", "p_short"]].max(axis=1)
    merged["direction"] = np.where(merged["p_long"] >= merged["p_short"], "LONG", "SHORT")
    return merged.reset_index()


def stitch_dataset(dataset: pd.DataFrame, preds: pd.DataFrame) -> pd.DataFrame:
    base = dataset.reset_index().rename(columns={dataset.index.name or "index": "timestamp"})
    if "timestamp" not in base.columns:
        base = dataset.reset_index().rename(columns={"index": "timestamp"})
    out = preds.merge(base, on="timestamp", how="left")
    out["target_hit"] = np.where(
        out["direction"] == "LONG",
        out["long_primary_hit"],
        out["short_primary_hit"],
    )
    out["mfe_atr"] = np.where(out["direction"] == "LONG", out["long_mfe_atr"], out["short_mfe_atr"])
    out["mae_atr"] = np.where(out["direction"] == "LONG", out["long_mae_atr"], out["short_mae_atr"])
    out["net_atr"] = np.where(out["direction"] == "LONG", out["long_net_atr"], out["short_net_atr"])
    out["gross_r"] = [
        gross_r_from_label(bool(h), float(n))
        for h, n in zip(out["target_hit"], out["net_atr"])
    ]
    out["net_r"] = [net_r(g, float(a)) for g, a in zip(out["gross_r"], out["atr_frozen"])]
    return out


def performance(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return {"N": 0}
    r = df["net_r"].astype(float)
    wins = r[r > 0].sum()
    losses = abs(r[r < 0].sum())
    return {
        "N": len(df),
        "target_hit_rate": float(df["target_hit"].mean()),
        "win_rate": float((r > 0).mean()),
        "Avg_MFE": float(df["mfe_atr"].mean()),
        "Avg_MAE": float(df["mae_atr"].mean()),
        "median_MFE": float(df["mfe_atr"].median()),
        "median_MAE": float(df["mae_atr"].median()),
        "MFE_MAE": float((df["mfe_atr"] / df["mae_atr"].replace(0, np.nan)).mean()),
        "gross_AvgR": float(df["gross_r"].mean()),
        "net_AvgR": float(r.mean()),
        "net_TotalR": float(r.sum()),
        "net_PF": float(wins / losses) if losses > 0 else float("inf"),
        "MaxDD": float(max_drawdown(r.to_numpy())),
    }


def precision_curve(stitched: pd.DataFrame) -> pd.DataFrame:
    ordered = stitched.sort_values("edge_score", ascending=False)
    rows = []
    base = performance(stitched)
    rows.append({"top_fraction": 1.0, **base})
    n = len(ordered)
    years = (ordered["timestamp"].max() - ordered["timestamp"].min()).days / 365.25
    for frac in PRECISION_FRACTIONS:
        keep = max(1, int(n * frac))
        sub = ordered.iloc[:keep]
        perf = performance(sub)
        perf["top_fraction"] = frac
        perf["signals_per_year"] = keep / years if years > 0 else np.nan
        perf["false_signal_rate"] = 1.0 - perf.get("target_hit_rate", np.nan)
        rows.append(perf)
    return pd.DataFrame(rows)


def score_deciles(stitched: pd.DataFrame) -> pd.DataFrame:
    df = stitched.copy()
    df["decile"] = pd.qcut(df["edge_score"].rank(method="first"), 10, labels=False) + 1
    rows = []
    for decile, group in df.groupby("decile"):
        perf = performance(group)
        perf["decile"] = int(decile)
        rows.append(perf)
    out = pd.DataFrame(rows).sort_values("decile")
    if len(out) >= 3:
        out["monotonic_hint"] = out["net_AvgR"].corr(out["decile"])
    return out


def feature_diagnostics(dataset: pd.DataFrame) -> pd.DataFrame:
    feats = feature_columns(dataset)
    eligible = dataset.loc[dataset["eligible"]]
    rows = []
    for feat in feats:
        for side, target in (("long", "long_primary_hit"), ("short", "short_primary_hit")):
            x = eligible[feat].astype(float)
            y = eligible[target].astype(int)
            mask = np.isfinite(x)
            if mask.sum() < 1000:
                continue
            try:
                auc = roc_auc_score(y[mask], x[mask])
            except ValueError:
                auc = np.nan
            pos = eligible.loc[eligible[target], feat].astype(float)
            neg = eligible.loc[~eligible[target], feat].astype(float)
            d = (pos.mean() - neg.mean()) / np.sqrt((pos.var() + neg.var()) / 2) if len(pos) > 1 else np.nan
            rows.append({"feature": feat, "side": side, "auc": auc, "cohens_d": d, "pos_mean": pos.mean(), "neg_mean": neg.mean()})
    return pd.DataFrame(rows).sort_values("auc", ascending=False)


def feature_stability(preds: pd.DataFrame, dataset: pd.DataFrame) -> pd.DataFrame:
    feats = feature_columns(dataset)
    tz = dataset.index.tz
    rows = []
    for train_start, train_end, val_start, val_end in WALK_FORWARD_FOLDS:
        train = dataset.loc[(dataset.index >= pd.Timestamp(train_start, tz=tz)) & (dataset.index <= pd.Timestamp(train_end, tz=tz)) & dataset["eligible"]]
        if len(train) < 5000:
            continue
        for side, target in (("long", "long_primary_hit"), ("short", "short_primary_hit")):
            pipe = _model()
            pipe.fit(train[feats], train[target].astype(int))
            clf = pipe.named_steps["clf"]
            for feat, imp in sorted(zip(feats, clf.feature_importances_), key=lambda x: -x[1])[:10]:
                rows.append({"fold_val_end": val_end, "side": side, "feature": feat, "importance": float(imp)})
    return pd.DataFrame(rows)


def false_signal_analysis(stitched: pd.DataFrame, top_frac: float = 0.05) -> pd.DataFrame:
    top = stitched.sort_values("edge_score", ascending=False).iloc[: max(1, int(len(stitched) * top_frac))]
    success = top.loc[top["target_hit"]]
    fail = top.loc[~top["target_hit"]]
    rows = []
    compare_cols = [c for c in stitched.columns if c in feature_columns(stitched)]
    for col in compare_cols[:30]:
        rows.append(
            {
                "feature": col,
                "success_mean": float(success[col].astype(float).mean()) if len(success) else np.nan,
                "fail_mean": float(fail[col].astype(float).mean()) if len(fail) else np.nan,
                "delta": float(success[col].astype(float).mean() - fail[col].astype(float).mean()) if len(success) and len(fail) else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("delta", key=abs, ascending=False)


def extract_simple_rules(stitched: pd.DataFrame, diagnostics: pd.DataFrame, top_frac: float = 0.05) -> pd.DataFrame:
    top = stitched.sort_values("edge_score", ascending=False).iloc[: max(50, int(len(stitched) * top_frac))]
    rules = []
    for side in ("LONG", "SHORT"):
        sub = top.loc[top["direction"] == side]
        if len(sub) < 50:
            continue
        diag = diagnostics.loc[diagnostics["side"] == side.lower()].head(3)
        conds = []
        for _, row in diag.iterrows():
            feat = row["feature"]
            val = sub[feat].astype(float).median()
            if row["cohens_d"] > 0:
                conds.append(f"{feat} >= {val:.4f}")
            else:
                conds.append(f"{feat} <= {val:.4f}")
        rules.append({"direction": side, "conditions": " AND ".join(conds[:3]), "N_top": len(sub), "net_AvgR": performance(sub)["net_AvgR"]})
    return pd.DataFrame(rules)


def classify_result(stitched: pd.DataFrame, precision: pd.DataFrame) -> str:
    top10 = precision.loc[precision["top_fraction"] == 0.10]
    if top10.empty:
        return "D"
    perf = top10.iloc[0].to_dict()
    base_rate = stitched["target_hit"].mean()
    hit_rate = perf.get("target_hit_rate", 0)
    if perf.get("net_AvgR", -999) <= 0:
        return "D" if hit_rate <= base_rate + 0.03 else "C"
    if perf.get("N", 0) >= 200 and perf.get("net_AvgR", -999) >= 0.10 and perf.get("net_PF", 0) >= 1.20 and hit_rate > base_rate + 0.05:
        return "A"
    if perf.get("N", 0) >= 200 and perf.get("net_AvgR", -999) > 0.05 and perf.get("net_PF", 0) >= 1.15:
        return "B"
    return "C"


def run_phase26(*, output: Path = RESULTS) -> Dict[str, Any]:
    from .features import build_features, load_market
    from .labels import build_path_labels

    output.mkdir(parents=True, exist_ok=True)
    market = load_market()
    features = build_features(market)
    labels = build_path_labels(market)
    dataset = features.join(labels)
    dataset.to_csv(output / "entry_path_dataset.csv")

    (output / "feature_definitions.md").write_text(
        "# Phase 26 causal features\n\nAll features use information available at bar close only.\n\n"
        + "\n".join(f"- `{c}`" for c in feature_columns(dataset))
    )

    diag = feature_diagnostics(dataset)
    diag.to_csv(output / "feature_diagnostics.csv", index=False)

    preds = walk_forward_predictions(dataset)
    preds.to_csv(output / "walk_forward_predictions.csv", index=False)
    stitched = stitch_dataset(dataset, preds)
    precision = precision_curve(stitched)
    precision.to_csv(output / "precision_curve.csv", index=False)
    deciles = score_deciles(stitched)
    deciles.to_csv(output / "score_deciles.csv", index=False)

    long_short = []
    for direction in ("LONG", "SHORT"):
        sub = stitched.loc[stitched["direction"] == direction]
        long_short.append({"direction": direction, **performance(sub)})
    pd.DataFrame(long_short).to_csv(output / "long_short_comparison.csv", index=False)

    stab = feature_stability(preds, dataset)
    stab.to_csv(output / "feature_stability.csv", index=False)
    false_sig = false_signal_analysis(stitched)
    false_sig.to_csv(output / "false_signal_analysis.csv", index=False)
    rules = extract_simple_rules(stitched, diag)
    rules.to_csv(output / "candidate_rules.csv", index=False)

    eligible = dataset.loc[dataset["eligible"]]
    final_class = classify_result(stitched, precision)
    mono = deciles["net_AvgR"].corr(deciles["decile"]) if "decile" in deciles else np.nan

    manifest = {
        "phase": "Phase 26 — High-Expectancy Entry Trigger Discovery",
        "total_bars": len(market),
        "eligible_bars": int(dataset["eligible"].sum()),
        "unconditional_long_rate": float(eligible["long_primary_hit"].mean()),
        "unconditional_short_rate": float(eligible["short_primary_hit"].mean()),
        "stitched_walk_forward": performance(stitched),
        "precision_top10": precision.loc[precision.top_fraction == 0.10].to_dict("records"),
        "score_monotonicity_corr": float(mono) if np.isfinite(mono) else None,
        "final_classification": final_class,
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    with pd.ExcelWriter(output / "HIGH_EXPECTANCY_ENTRY.xlsx", engine="openpyxl") as writer:
        for name in ["feature_diagnostics", "precision_curve", "score_deciles", "long_short_comparison", "feature_stability"]:
            pd.read_csv(output / f"{name}.csv").to_excel(writer, sheet_name=name[:31], index=False)

    report = [
        "# High-Expectancy Entry Report",
        f"Classification: **{final_class}**",
        f"Unconditional long hit rate: {manifest['unconditional_long_rate']:.3f}",
        f"Unconditional short hit rate: {manifest['unconditional_short_rate']:.3f}",
        f"Stitched WF net AvgR: {manifest['stitched_walk_forward'].get('net_AvgR', 'n/a')}",
    ]
    (output / "HIGH_EXPECTANCY_ENTRY_REPORT.md").write_text("\n".join(report) + "\n")
    return manifest
