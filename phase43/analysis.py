"""Quality analysis: deciles, retention, rejection, monotonicity, Monte Carlo."""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from phase31.metrics import apply_costs, performance

from .config import HIGH_CONF_LEVELS, MC_SIMS, REJECTION_RATES, RETENTION_LEVELS, BOOTSTRAP_SIMS


def _perf_row(df: pd.DataFrame, label: str, *, col: str = "net_R") -> dict:
    p = performance(df, col=col)
    p["segment"] = label
    p["N"] = int(p.get("N", 0))
    if not df.empty:
        p["MFE"] = float(df["MFE_R"].mean())
        p["MAE"] = float(df["MAE_R"].mean())
        p["target_hit_rate"] = float(df["target_hit"].mean()) if "target_hit" in df.columns else np.nan
        p["stop_hit_rate"] = float(df["stop_hit"].mean()) if "stop_hit" in df.columns else np.nan
        p["wrong_direction_rate"] = float(df["wrong_direction"].mean()) if "wrong_direction" in df.columns else np.nan
    return p


def quality_deciles(oos: pd.DataFrame, *, score_col: str = "quality_score") -> pd.DataFrame:
    if oos.empty:
        return pd.DataFrame()
    d = oos.copy()
    d["decile"] = pd.qcut(d[score_col].rank(method="first"), 10, labels=False) + 1
    rows = []
    for dec in sorted(d["decile"].unique()):
        sub = d.loc[d["decile"] == dec]
        rows.append(_perf_row(sub, f"D{int(dec)}"))
    return pd.DataFrame(rows)


def quality_buckets(oos: pd.DataFrame, *, score_col: str = "quality_score") -> pd.DataFrame:
    if oos.empty:
        return pd.DataFrame()
    d = oos.copy()
    d["pct_rank"] = d[score_col].rank(pct=True)
    cuts = [
        ("bottom_20", d["pct_rank"] <= 0.20),
        ("20_40", (d["pct_rank"] > 0.20) & (d["pct_rank"] <= 0.40)),
        ("40_60", (d["pct_rank"] > 0.40) & (d["pct_rank"] <= 0.60)),
        ("60_80", (d["pct_rank"] > 0.60) & (d["pct_rank"] <= 0.80)),
        ("80_90", (d["pct_rank"] > 0.80) & (d["pct_rank"] <= 0.90)),
        ("90_95", (d["pct_rank"] > 0.90) & (d["pct_rank"] <= 0.95)),
        ("95_100", d["pct_rank"] > 0.95),
    ]
    return pd.DataFrame([_perf_row(d.loc[mask], name) for name, mask in cuts])


def monotonicity_test(deciles: pd.DataFrame) -> dict:
    if deciles.empty or "AvgR" not in deciles.columns:
        return {"classification": "NON_MONOTONIC", "spearman": 0.0, "adjacent_improvements": 0}
    x = np.arange(1, len(deciles) + 1)
    y = deciles["AvgR"].astype(float).values
    rho, _ = spearmanr(x, y)
    adj = sum(1 for i in range(len(y) - 1) if y[i + 1] > y[i])
    cls = "NON_MONOTONIC"
    if rho >= 0.6 and adj >= 7:
        cls = "STRONG_MONOTONIC"
    elif rho >= 0.35 and adj >= 5:
        cls = "PARTIAL_MONOTONIC"
    return {
        "classification": cls,
        "spearman": float(rho) if np.isfinite(rho) else 0.0,
        "adjacent_improvements": int(adj),
        "decile_AvgR": y.tolist(),
    }


def retention_curve(oos: pd.DataFrame, *, score_col: str = "quality_score") -> pd.DataFrame:
    if oos.empty:
        return pd.DataFrame()
    d = oos.sort_values(score_col, ascending=False)
    n_total = len(d)
    rows = []
    for keep in RETENTION_LEVELS:
        n = max(1, int(round(n_total * keep)))
        sub = d.head(n)
        p = _perf_row(sub, f"keep_{int(keep*100)}")
        p["retention"] = keep
        p["signals_rejected"] = n_total - n
        p["signals/day"] = n / _rth_days(d)
        rows.append(p)
    return pd.DataFrame(rows)


def rejection_analysis(oos: pd.DataFrame, *, score_col: str = "quality_score") -> pd.DataFrame:
    if oos.empty:
        return pd.DataFrame()
    d = oos.sort_values(score_col, ascending=True)
    n = len(d)
    rows = []
    for rate in REJECTION_RATES:
        n_rej = int(round(n * rate))
        rejected = d.head(n_rej)
        retained = d.iloc[n_rej:]
        losers = d.loc[d["net_R"] < 0]
        winners = d.loc[d["net_R"] > 0]
        rows.append(
            {
                "reject_rate": rate,
                "signals_removed": n_rej,
                "losers_removed": int((rejected["net_R"] < 0).sum()),
                "winners_incorrectly_removed": int((rejected["net_R"] > 0).sum()),
                "retained_AvgR": performance(retained, col="net_R").get("AvgR", 0),
                "retained_PF": performance(retained, col="net_R").get("PF", 0),
                "baseline_AvgR": performance(d, col="net_R").get("AvgR", 0),
                "AvgR_change": performance(retained, col="net_R").get("AvgR", 0) - performance(d, col="net_R").get("AvgR", 0),
                "rejected_AvgR": performance(rejected, col="net_R").get("AvgR", 0) if not rejected.empty else np.nan,
                "rejected_PF": performance(rejected, col="net_R").get("PF", 0) if not rejected.empty else np.nan,
                "bad_signal_rejection_precision": float((rejected["net_R"] < 0).mean()) if not rejected.empty else np.nan,
                "good_signal_retention_rate": float((retained["net_R"] > 0).sum() / max(len(winners), 1)),
            }
        )
    return pd.DataFrame(rows)


def high_confidence_analysis(oos: pd.DataFrame, *, score_col: str = "quality_score") -> pd.DataFrame:
    if oos.empty:
        return pd.DataFrame()
    d = oos.sort_values(score_col, ascending=False)
    n = len(d)
    rows = []
    for top in HIGH_CONF_LEVELS:
        k = max(1, int(round(n * top)))
        sub = d.head(k)
        p = _perf_row(sub, f"top_{int(top*100)}")
        p["top_pct"] = top
        p["trades/day"] = k / _rth_days(d)
        rows.append(p)
    return pd.DataFrame(rows)


def wrong_direction_analysis(oos: pd.DataFrame, *, score_col: str = "quality_score") -> pd.DataFrame:
    if oos.empty or "wrong_direction" not in oos.columns:
        return pd.DataFrame()
    base = float(oos["wrong_direction"].mean())
    rows = [{"segment": "baseline", "wrong_direction_rate": base, "N": len(oos)}]
    q = oos[score_col]
    for name, mask in (
        ("bottom_20", q <= q.quantile(0.20)),
        ("top_20", q >= q.quantile(0.80)),
        ("top_10", q >= q.quantile(0.90)),
    ):
        sub = oos.loc[mask]
        rows.append({"segment": name, "wrong_direction_rate": float(sub["wrong_direction"].mean()), "N": len(sub)})
    d = oos.copy()
    d["decile"] = pd.qcut(d[score_col].rank(method="first"), 10, labels=False) + 1
    for dec in sorted(d["decile"].unique()):
        sub = d.loc[d["decile"] == dec]
        rows.append({"segment": f"D{int(dec)}", "wrong_direction_rate": float(sub["wrong_direction"].mean()), "N": len(sub)})
    return pd.DataFrame(rows)


def cost_stress(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for mult in (1.0, 1.5, 2.0):
        d = df.copy()
        d["net_R"] = apply_costs(
            d.assign(entry_price=d["entry_price"], stop_price=d["stop"], result_R=d["realized_R"]),
            multiplier=mult,
        )
        rows.append({"cost_multiplier": mult, **_perf_row(d, f"cost_{mult}")})
    return pd.DataFrame(rows)


def outlier_robustness(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    top = df["net_R"].max()
    top3 = df["net_R"].nlargest(3).min()
    cutoff = df["net_R"].quantile(0.99)
    return pd.DataFrame(
        [
            _perf_row(df, "full"),
            _perf_row(df.loc[df["net_R"] < top], "exclude_best"),
            _perf_row(df.loc[df["net_R"] < top3], "exclude_top_3"),
            _perf_row(df.loc[df["net_R"] <= cutoff], "exclude_top_1pct"),
        ]
    )


def monte_carlo(r: np.ndarray, *, sims: int = MC_SIMS, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    n = len(r)
    if n == 0:
        return {}
    terminals, max_dds, streaks = [], [], []
    for _ in range(sims):
        sample = r[rng.integers(0, n, size=n)]
        cum = np.cumsum(sample)
        terminals.append(float(cum[-1]))
        peak = np.maximum.accumulate(cum)
        max_dds.append(float(np.max(peak - cum)))
    for _ in range(min(1000, sims)):
        sample = r[rng.integers(0, n, size=n)]
        cur = mx = 0
        for x in sample:
            cur = cur + 1 if x < 0 else 0
            mx = max(mx, cur)
        streaks.append(mx)
    terminals = np.array(terminals)
    max_dds = np.array(max_dds)
    return {
        "P_terminal_pos": float((terminals > 0).mean()),
        "median_terminal_R": float(np.median(terminals)),
        "p5_terminal_R": float(np.percentile(terminals, 5)),
        "p95_terminal_R": float(np.percentile(terminals, 95)),
        "median_maxDD": float(np.median(max_dds)),
        "p95_maxDD": float(np.percentile(max_dds, 95)),
        "median_losing_streak": float(np.median(streaks)),
        "p95_losing_streak": float(np.percentile(streaks, 95)),
    }


def bootstrap_uncertainty(baseline_r: np.ndarray, filtered_r: np.ndarray, *, sims: int = BOOTSTRAP_SIMS, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(sims):
        idx_b = rng.integers(0, len(baseline_r), size=len(baseline_r))
        idx_f = rng.integers(0, len(filtered_r), size=len(filtered_r))
        diffs.append(float(np.mean(filtered_r[idx_f]) - np.mean(baseline_r[idx_b])))
    diffs = np.array(diffs)
    return {
        "baseline_AvgR_ci_low": float(np.percentile([np.mean(baseline_r[rng.integers(0, len(baseline_r), len(baseline_r))]) for _ in range(200)], 2.5)),
        "baseline_AvgR_ci_high": float(np.percentile([np.mean(baseline_r[rng.integers(0, len(baseline_r), len(baseline_r))]) for _ in range(200)], 97.5)),
        "filtered_AvgR_ci_low": float(np.percentile([np.mean(filtered_r[rng.integers(0, len(filtered_r), len(filtered_r))]) for _ in range(200)], 2.5)),
        "filtered_AvgR_ci_high": float(np.percentile([np.mean(filtered_r[rng.integers(0, len(filtered_r), len(filtered_r))]) for _ in range(200)], 97.5)),
        "AvgR_diff_ci_low": float(np.percentile(diffs, 2.5)),
        "AvgR_diff_ci_high": float(np.percentile(diffs, 97.5)),
        "AvgR_diff_median": float(np.median(diffs)),
    }


def simple_score_comparison(oos: pd.DataFrame) -> pd.DataFrame:
    if oos.empty:
        return pd.DataFrame()
    rows = []
    for col, name in (("quality_score", "ML_RIDGE"), ("quality_score_simple", "SIMPLE_RANK")):
        top20 = oos.loc[oos[col] >= oos[col].quantile(0.80)]
        bot20 = oos.loc[oos[col] <= oos[col].quantile(0.20)]
        rows.append({"model": name, "segment": "top_20", **performance(top20, col="net_R")})
        rows.append({"model": name, "segment": "bottom_20", **performance(bot20, col="net_R")})
        mono = monotonicity_test(quality_deciles(oos, score_col=col))
        rows.append({"model": name, "segment": "monotonicity", "spearman": mono["spearman"], "classification": mono["classification"]})
    return pd.DataFrame(rows)


def select_best_filter(oos: pd.DataFrame, rejection_df: pd.DataFrame) -> Tuple[pd.DataFrame, float, dict]:
    """Pick train-calibrated rejection rate with best OOS AvgR improvement."""
    if rejection_df.empty:
        return oos, 0.0, {}
    best = rejection_df.sort_values("AvgR_change", ascending=False).iloc[0]
    rate = float(best["reject_rate"])
    d = oos.sort_values("quality_score")
    n_rej = int(round(len(d) * rate))
    filtered = d.iloc[n_rej:]
    return filtered, rate, best.to_dict()


def segment_results(df: pd.DataFrame, col: str = "signal_type") -> pd.DataFrame:
    rows = []
    for val in df[col].unique():
        rows.append(_perf_row(df.loc[df[col] == val], str(val)))
    for seg, mask in (
        ("continuation", df["signal_type"].isin(["L", "S"])),
        ("reversal", df["signal_type"].isin(["RL", "RS"])),
        ("long", df["direction"].astype(str).str.lower() == "long"),
        ("short", df["direction"].astype(str).str.lower() == "short"),
        ("ALL", pd.Series(True, index=df.index)),
    ):
        sub = df.loc[mask]
        if not sub.empty:
            rows.append(_perf_row(sub, seg))
    return pd.DataFrame(rows)


def yearly_results(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    d["year"] = pd.to_datetime(d["marker_bar_timestamp"], utc=True).dt.year
    return d.groupby("year").apply(lambda g: pd.Series(_perf_row(g, str(g.name))), include_groups=False).reset_index()


def _rth_days(df: pd.DataFrame) -> float:
    if df.empty:
        return 1.0
    ts = pd.to_datetime(df["marker_bar_timestamp"], utc=True)
    days = (ts.max() - ts.min()).days
    return max(days / 365.0 * 252.0, 1.0)
