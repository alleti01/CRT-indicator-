"""Entry signal precision analysis — walk-forward quality ranking."""

from __future__ import annotations

import json
from math import sqrt
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from phase16.metrics import summarize_group as metric_summary
from phase17.analysis_core import max_drawdown

from .build_entry_dataset import build_master_dataset, load_baseline_trades
from .config import FEATURE_FAMILIES, RESULTS, RETENTION_FRACTIONS, WALK_FORWARD_FOLDS


def performance_table(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return {"N": 0, "win_rate": np.nan, "AvgR": np.nan, "TotalR": np.nan, "PF": np.nan, "MaxDD": np.nan}
    r = df["result_R"].astype(float)
    wins = r[r > 0].sum()
    losses = abs(r[r < 0].sum())
    return {
        "N": len(df),
        "win_rate": float((r > 0).mean()),
        "AvgR": float(r.mean()),
        "TotalR": float(r.sum()),
        "PF": float(wins / losses) if losses > 0 else float("inf"),
        "MaxDD": float(max_drawdown(r.to_numpy())),
        "mean_mfe_r": float(df["mfe_r"].astype(float).mean()) if "mfe_r" in df else np.nan,
        "mean_mae_r": float(df["mae_r"].astype(float).mean()) if "mae_r" in df else np.nan,
    }


def winner_loser_analysis(dataset: pd.DataFrame, features: List[str]) -> pd.DataFrame:
    rows = []
    winners = dataset.loc[dataset["result_R"] > 0]
    losers = dataset.loc[dataset["result_R"] < 0]
    big_win = dataset.loc[dataset["result_R"] >= 1.0]
    big_loss = dataset.loc[dataset["result_R"] <= -0.75]
    for feature in features:
        if feature not in dataset.columns:
            continue
        w = winners[feature].astype(float)
        l = losers[feature].astype(float)
        w = w[np.isfinite(w)]
        l = l[np.isfinite(l)]
        if len(w) < 20 or len(l) < 20:
            continue
        pooled_std = np.sqrt((w.var(ddof=1) + l.var(ddof=1)) / 2) if len(w) > 1 and len(l) > 1 else np.nan
        effect = (w.mean() - l.mean()) / pooled_std if pooled_std and pooled_std > 0 else np.nan
        try:
            auc = roc_auc_score(dataset["win"], dataset[feature].astype(float).fillna(dataset[feature].median()))
        except ValueError:
            auc = np.nan
        rows.append(
            {
                "feature": feature,
                "winner_mean": float(w.mean()),
                "loser_mean": float(l.mean()),
                "winner_median": float(w.median()),
                "loser_median": float(l.median()),
                "cohens_d": float(effect) if np.isfinite(effect) else np.nan,
                "auc_win": float(auc) if np.isfinite(auc) else np.nan,
                "big_winner_mean": float(big_win[feature].astype(float).mean()) if len(big_win) else np.nan,
                "big_loser_mean": float(big_loss[feature].astype(float).mean()) if len(big_loss) else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("auc_win", ascending=False, na_position="last")


def _model_pipelines(numeric: List[str], categorical: List[str]) -> Dict[str, Pipeline]:
    pre = ColumnTransformer(
        [
            ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), numeric),
            ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")), ("oh", OneHotEncoder(handle_unknown="ignore"))]), categorical),
        ]
    )
    return {
        "logistic": Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=1000, class_weight="balanced"))]),
        "tree": Pipeline([("pre", pre), ("clf", DecisionTreeClassifier(max_depth=4, min_samples_leaf=50, class_weight="balanced", random_state=24))]),
        "extra_trees": Pipeline([("pre", pre), ("clf", ExtraTreesClassifier(n_estimators=200, max_depth=6, min_samples_leaf=40, class_weight="balanced", random_state=24))]),
        "gbm": Pipeline([("pre", pre), ("clf", GradientBoostingClassifier(random_state=24))]),
    }


def _feature_lists(dataset: pd.DataFrame) -> Tuple[List[str], List[str]]:
    numeric = []
    categorical = []
    for cols in FEATURE_FAMILIES.values():
        for col in cols:
            if col not in dataset.columns:
                continue
            if dataset[col].dtype == object or str(dataset[col].dtype) == "category":
                categorical.append(col)
            else:
                numeric.append(col)
    numeric.extend(["model_code", "direction_code", "htf_regime", "session_bucket"])
    numeric = sorted(c for c in set(numeric) if c in dataset.columns)
    categorical = sorted(c for c in set(categorical) if c in dataset.columns)
    return numeric, categorical


def walk_forward_predictions(dataset: pd.DataFrame) -> pd.DataFrame:
    numeric, categorical = _feature_lists(dataset)
    models = _model_pipelines(numeric, categorical)
    tz = dataset["entry_timestamp"].dt.tz
    rows = []
    for train_start, train_end, val_start, val_end in WALK_FORWARD_FOLDS:
        train = dataset.loc[
            (dataset["entry_timestamp"] >= pd.Timestamp(train_start, tz=tz))
            & (dataset["entry_timestamp"] <= pd.Timestamp(train_end, tz=tz))
        ]
        val = dataset.loc[
            (dataset["entry_timestamp"] >= pd.Timestamp(val_start, tz=tz))
            & (dataset["entry_timestamp"] <= pd.Timestamp(val_end, tz=tz))
        ]
        if len(train) < 200 or len(val) < 50:
            continue
        y_train = train["good_entry"].astype(int)
        y_bad_train = train["bad_entry"].astype(int)
        for model_name in models:
            cols = [c for c in numeric + categorical if c in train.columns]
            num = [c for c in numeric if c in train.columns]
            cat = [c for c in categorical if c in train.columns]
            pipe = _model_pipelines(num, cat)[model_name]
            pipe.fit(train[cols], y_train)
            quality = pipe.predict_proba(val[cols])[:, 1]
            pipe_bad = _model_pipelines(num, cat)[model_name]
            pipe_bad.fit(train[cols], y_bad_train)
            bad_score = pipe_bad.predict_proba(val[cols])[:, 1]
            for i, (_, row) in enumerate(val.iterrows()):
                rows.append(
                    {
                        "entry_timestamp": row["entry_timestamp"],
                        "model": row["model"],
                        "direction": row["direction"],
                        "fold_train_end": train_end,
                        "fold_val_end": val_end,
                        "ml_model": model_name,
                        "quality_score": float(quality[i]),
                        "bad_score": float(bad_score[i]),
                        "result_R": float(row["result_R"]),
                        "good_entry": bool(row["good_entry"]),
                        "bad_entry": bool(row["bad_entry"]),
                    }
                )
    preds = pd.DataFrame(rows)
    if preds.empty:
        return preds
    best = preds.loc[preds.groupby(["entry_timestamp", "model"])["quality_score"].idxmax()]
    return best.reset_index(drop=True)


def decile_analysis(predictions: pd.DataFrame, dataset: pd.DataFrame) -> pd.DataFrame:
    merged = predictions.merge(
        dataset[["entry_timestamp", "model", "mfe_r", "mae_r"]],
        on=["entry_timestamp", "model"],
        how="left",
    )
    rows = []
    for decile, group in merged.groupby(pd.qcut(merged["quality_score"].rank(method="first"), 10, labels=False), dropna=True):
        perf = performance_table(group.rename(columns={"result_R": "result_R"}))
        rows.append({"decile": int(decile) + 1, **perf})
    return pd.DataFrame(rows)


def retention_curve(predictions: pd.DataFrame, dataset: pd.DataFrame) -> pd.DataFrame:
    merged = predictions.sort_values("quality_score", ascending=False).copy()
    rows = []
    baseline = performance_table(merged)
    baseline["retention_pct"] = 100
    baseline["signals_rejected_pct"] = 0
    rows.append(baseline)
    n = len(merged)
    months = max((merged["entry_timestamp"].max() - merged["entry_timestamp"].min()).days / 30.44, 1)
    for frac in RETENTION_FRACTIONS:
        if frac >= 1.0:
            continue
        keep = max(1, int(round(n * frac)))
        subset = merged.iloc[:keep]
        perf = performance_table(subset)
        perf["retention_pct"] = round(frac * 100, 1)
        perf["signals_rejected_pct"] = round((1 - frac) * 100, 1)
        perf["trades_per_month"] = float(len(subset) / months)
        rows.append(perf)
    return pd.DataFrame(rows)


def bad_signal_rejection(predictions: pd.DataFrame, dataset: pd.DataFrame) -> pd.DataFrame:
    merged = predictions.copy()
    rows = []
    baseline = performance_table(merged)
    baseline["method"] = "baseline"
    baseline["reject_pct"] = 0
    rows.append(baseline)
    for reject in (0.2, 0.3, 0.4, 0.5):
        cutoff = merged["bad_score"].quantile(1 - reject)
        kept = merged.loc[merged["bad_score"] <= cutoff]
        perf = performance_table(kept)
        perf["method"] = "reject_high_bad_score"
        perf["reject_pct"] = reject * 100
        rows.append(perf)
    return pd.DataFrame(rows)


def feature_ablation(predictions_base: pd.DataFrame, dataset: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base_auc = roc_auc_score(predictions_base["good_entry"].astype(int), predictions_base["quality_score"]) if len(predictions_base) > 10 else np.nan
    rows.append({"family": "all", "auc_good_entry": base_auc, "validation_n": len(predictions_base)})
    for family, cols in FEATURE_FAMILIES.items():
        reduced = dataset.copy()
        drop_cols = [c for c in cols if c in reduced.columns]
        if not drop_cols:
            continue
        reduced = reduced.drop(columns=drop_cols)
        preds = walk_forward_predictions(reduced)
        if preds.empty:
            continue
        auc = roc_auc_score(preds["good_entry"].astype(int), preds["quality_score"]) if len(preds) > 10 else np.nan
        rows.append({"family": family, "auc_good_entry": auc, "validation_n": len(preds), "delta_auc": auc - base_auc if np.isfinite(base_auc) else np.nan})
    return pd.DataFrame(rows)


def feature_importance(dataset: pd.DataFrame) -> pd.DataFrame:
    numeric, categorical = _feature_lists(dataset)
    pipe = _model_pipelines(numeric, categorical)["extra_trees"]
    train = dataset.loc[dataset["entry_timestamp"] < pd.Timestamp("2025-01-01", tz=dataset["entry_timestamp"].dt.tz)]
    cols = [c for c in numeric + categorical if c in train.columns]
    num = [c for c in numeric if c in train.columns]
    cat = [c for c in categorical if c in train.columns]
    pipe = _model_pipelines(num, cat)["extra_trees"]
    pipe.fit(train[cols], train["good_entry"].astype(int))
    clf = pipe.named_steps["clf"]
    pre = pipe.named_steps["pre"]
    names = pre.get_feature_names_out()
    importances = clf.feature_importances_
    return pd.DataFrame({"feature": names, "importance": importances}).sort_values("importance", ascending=False)


def cost_stress(dataset: pd.DataFrame, predictions: pd.DataFrame, *, top_frac: float = 0.5) -> pd.DataFrame:
    merged = predictions.sort_values("quality_score", ascending=False)
    keep = merged.iloc[: max(1, int(len(merged) * top_frac))]
    rows = []
    for mult in (1.0, 1.5, 2.0):
        adjusted = keep.copy()
        adjusted["result_R"] = adjusted["result_R"] - (0.05 * (mult - 1.0))
        perf = performance_table(adjusted)
        perf["cost_multiplier"] = mult
        rows.append(perf)
    return pd.DataFrame(rows)


def robustness_checks(dataset: pd.DataFrame, predictions: pd.DataFrame, *, top_frac: float = 0.5) -> pd.DataFrame:
    merged = predictions.sort_values("quality_score", ascending=False)
    top = merged.iloc[: max(1, int(len(merged) * top_frac))]
    rows = []
    for label, subset in (
        ("top_half", top),
        ("exclude_best_trade", top.nsmallest(len(top) - 1, "result_R") if len(top) > 1 else top),
        ("exclude_top3", top.nsmallest(max(1, len(top) - 3), "result_R")),
        ("exclude_top1pct", top.iloc[int(len(top) * 0.01) :]),
    ):
        rows.append({"scenario": label, **performance_table(subset)})
    top["year"] = top["entry_timestamp"].dt.year
    for year, group in top.groupby("year"):
        rows.append({"scenario": f"year_{year}", **performance_table(group)})
    return pd.DataFrame(rows)


def classify_study(baseline: Dict[str, float], best_region: Dict[str, float], monotonic: bool) -> str:
    if best_region.get("N", 0) < 150:
        return "D"
    if (
        best_region.get("PF", 0) >= 1.20
        and best_region.get("AvgR", 0) >= baseline.get("AvgR", 0) + 0.10
        and best_region.get("MaxDD", 0) > baseline.get("MaxDD", 0)
        and monotonic
    ):
        return "A"
    if best_region.get("PF", 0) >= 1.10 and best_region.get("AvgR", 0) > baseline.get("AvgR", 0):
        return "B"
    if best_region.get("AvgR", 0) > baseline.get("AvgR", 0):
        return "C"
    return "D"


def run_entry_precision_study(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    dataset, raw_trades = build_master_dataset()
    raw_trades.to_csv(output / "baseline_signal_population.csv", index=False)
    dataset.to_csv(output / "entry_feature_dataset.csv", index=False)

    all_features = sorted({c for cols in FEATURE_FAMILIES.values() for c in cols if c in dataset.columns})
    all_features += ["model_code", "direction_code", "htf_regime", "session_bucket", "score", "stop_distance_atr"]
    wl = winner_loser_analysis(dataset, sorted(set(all_features)))
    wl.to_csv(output / "winner_loser_analysis.csv", index=False)
    wl.head(30).to_csv(output / "feature_rankings.csv", index=False)

    predictions = walk_forward_predictions(dataset)
    predictions.to_csv(output / "walk_forward_predictions.csv", index=False)
    deciles = decile_analysis(predictions, dataset) if not predictions.empty else pd.DataFrame()
    deciles.to_csv(output / "quality_deciles.csv", index=False)
    retention = retention_curve(predictions, dataset) if not predictions.empty else pd.DataFrame()
    retention.to_csv(output / "retention_curve.csv", index=False)
    bad_reject = bad_signal_rejection(predictions, dataset) if not predictions.empty else pd.DataFrame()
    bad_reject.to_csv(output / "bad_signal_rejection.csv", index=False)

    long_short = pd.DataFrame(
        [
            {"direction": "Long", **performance_table(dataset.loc[dataset.direction == "Long"])},
            {"direction": "Short", **performance_table(dataset.loc[dataset.direction == "Short"])},
        ]
    )
    preds_long = predictions.copy()
    if not preds_long.empty:
        for direction in ("Long", "Short"):
            sub = preds_long.loc[preds_long.direction == direction].sort_values("quality_score", ascending=False)
            half = sub.iloc[: max(1, len(sub) // 2)]
            long_short.loc[long_short.direction == direction, "top_half_pf"] = performance_table(half)["PF"]
            long_short.loc[long_short.direction == direction, "top_half_avgr"] = performance_table(half)["AvgR"]
    long_short.to_csv(output / "long_short_analysis.csv", index=False)

    ablation = feature_ablation(predictions, dataset) if not predictions.empty else pd.DataFrame()
    ablation.to_csv(output / "feature_ablation.csv", index=False)
    importance = feature_importance(dataset)
    importance.to_csv(output / "feature_importance.csv", index=False)
    cost = cost_stress(dataset, predictions) if not predictions.empty else pd.DataFrame()
    cost.to_csv(output / "cost_stress.csv", index=False)
    robust = robustness_checks(dataset, predictions) if not predictions.empty else pd.DataFrame()
    robust.to_csv(output / "robustness.csv", index=False)

    baseline = performance_table(predictions if not predictions.empty else dataset)
    best_row = retention.sort_values("PF", ascending=False).iloc[0] if not retention.empty else baseline
    monotonic = False
    if not deciles.empty and len(deciles) >= 3:
        monotonic = bool(deciles["AvgR"].corr(pd.Series(deciles["decile"])) > 0.5)
    final_class = classify_study(baseline, best_row.to_dict(), monotonic)

    manifest = {
        "phase": "Phase 24 — Entry Signal Precision Optimization",
        "architecture": "Phase 14 Frozen CRT (FrozenConfig) — Control/BOS/Retest/Confirm",
        "baseline": baseline,
        "best_retention_region": best_row.to_dict() if not retention.empty else {},
        "decile_monotonic": monotonic,
        "final_classification": final_class,
        "top_features": importance.head(15).to_dict(orient="records"),
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    report = [
        "# Entry Signal Precision Report",
        "",
        f"Final classification: **{final_class}**",
        "",
        "## Baseline",
        f"- N={baseline['N']} WR={baseline['win_rate']:.3f} AvgR={baseline['AvgR']:.4f} PF={baseline['PF']:.3f} MaxDD={baseline['MaxDD']:.2f}",
        "",
        "## Best retention region",
        str(best_row.to_dict()) if not retention.empty else "n/a",
    ]
    (output / "ENTRY_SIGNAL_PRECISION_REPORT.md").write_text("\n".join(report) + "\n")

    with pd.ExcelWriter(output / "ENTRY_SIGNAL_PRECISION.xlsx", engine="openpyxl") as writer:
        for name, df in (
            ("dataset_head", dataset.head(3000)),
            ("winner_loser", wl.head(100)),
            ("deciles", deciles),
            ("retention", retention),
            ("importance", importance.head(50)),
        ):
            export = df.copy()
            for col in export.columns:
                if pd.api.types.is_datetime64_any_dtype(export[col]):
                    s = pd.to_datetime(export[col], errors="coerce")
                    if hasattr(s.dt, "tz") and s.dt.tz is not None:
                        export[col] = s.dt.tz_localize(None)
            export.to_excel(writer, sheet_name=name[:31], index=False)

    return manifest
