"""Phase 44B analysis: segments, bootstrap, Monte Carlo, stress tests."""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from phase31.metrics import apply_costs, performance

from .config import BOOTSTRAP_SIMS, MC_SIMS


def _perf(df: pd.DataFrame, label: str = "", *, col: str = "net_R") -> dict:
    p = performance(df, col=col)
    p["segment"] = label
    if not df.empty and "wrong_direction" in df.columns:
        p["wrong_direction_rate"] = float(df["wrong_direction"].mean())
    return p


def signal_type_results(baseline: pd.DataFrame, filtered: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for st in ("L", "S", "RL", "RS"):
        b = baseline.loc[baseline["signal_type"] == st]
        f = filtered.loc[filtered["signal_type"] == st]
        pb, pf = performance(b, col="net_R"), performance(f, col="net_R")
        rows.append(
            {
                "signal_type": st,
                "unfiltered_N": pb["N"],
                "filtered_N": pf["N"],
                "retention": pf["N"] / pb["N"] if pb["N"] else 0,
                "unfiltered_AvgR": pb["AvgR"],
                "filtered_AvgR": pf["AvgR"],
                "unfiltered_PF": pb["PF"],
                "filtered_PF": pf["PF"],
            }
        )
    return pd.DataFrame(rows)


def continuation_reversal(baseline: pd.DataFrame, filtered: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, types in (("CONTINUATION", ("L", "S")), ("REVERSAL", ("RL", "RS"))):
        for tag, df in (("baseline", baseline), ("filtered", filtered)):
            sub = df.loc[df["signal_type"].isin(types)]
            p = performance(sub, col="net_R")
            p["group"] = label
            p["variant"] = tag
            rows.append(p)
    return pd.DataFrame(rows)


def quality_deciles(oos: pd.DataFrame) -> pd.DataFrame:
    d = oos.copy()
    d["decile"] = pd.qcut(d["quality_score"].rank(method="first"), 10, labels=False) + 1
    rows = []
    for dec in sorted(d["decile"].unique()):
        sub = d.loc[d["decile"] == dec]
        rows.append(_perf(sub, f"D{int(dec)}"))
    return pd.DataFrame(rows)


def monotonicity(deciles: pd.DataFrame) -> dict:
    if deciles.empty:
        return {"classification": "NONE", "spearman": 0.0}
    x = np.arange(1, len(deciles) + 1)
    y = deciles["AvgR"].astype(float).values
    rho, _ = spearmanr(x, y)
    adj = sum(1 for i in range(len(y) - 1) if y[i + 1] > y[i])
    cls = "NONE"
    if rho >= 0.6 and adj >= 7:
        cls = "STRONG_MONOTONIC"
    elif rho >= 0.35 and adj >= 5:
        cls = "PARTIAL"
    return {"classification": cls, "spearman": float(rho), "adjacent_improvements": int(adj)}


def tail_buckets(oos: pd.DataFrame) -> pd.DataFrame:
    d = oos.copy()
    d["pct_rank"] = d["quality_score"].rank(pct=True)
    cuts = [
        ("bottom_20", d["pct_rank"] <= 0.20),
        ("top_20", d["pct_rank"] >= 0.80),
        ("top_10", d["pct_rank"] >= 0.90),
    ]
    return pd.DataFrame([_perf(d.loc[m], n) for n, m in cuts])


def confidence_tiers(oos: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tier in ("A+", "A", "B", "C"):
        sub = oos.loc[oos["confidence"] == tier]
        rows.append(_perf(sub, tier))
    return pd.DataFrame(rows)


def yearly_results(oos: pd.DataFrame, filtered: pd.DataFrame) -> pd.DataFrame:
    rows = []
    oos = oos.copy()
    oos["year"] = pd.to_datetime(oos["marker_bar_timestamp"]).dt.year
    filtered = filtered.copy()
    filtered["year"] = pd.to_datetime(filtered["marker_bar_timestamp"]).dt.year
    for year in sorted(oos["year"].unique()):
        base = oos.loc[oos["year"] == year]
        filt = filtered.loc[filtered["year"] == year]
        pb, pf = performance(base, col="net_R"), performance(filt, col="net_R")
        rows.append(
            {
                "year": int(year),
                "baseline_N": pb["N"],
                "filtered_N": pf["N"],
                "retention": pf["N"] / pb["N"] if pb["N"] else 0,
                "baseline_AvgR": pb["AvgR"],
                "filtered_AvgR": pf["AvgR"],
                "filtered_TotalR": pf["TotalR"],
                "filtered_PF": pf["PF"],
            }
        )
    return pd.DataFrame(rows)


def cost_stress(filtered: pd.DataFrame) -> pd.DataFrame:
    rows = []
    tmp = filtered.copy()
    if "stop_price" not in tmp.columns and "stop" in tmp.columns:
        tmp["stop_price"] = tmp["stop"]
    for mult in (1.0, 1.5, 2.0):
        net = apply_costs(tmp, multiplier=mult, col="realized_R")
        t = tmp.copy()
        t["net_R"] = net
        p = performance(t, col="net_R")
        p["cost_multiplier"] = mult
        rows.append(p)
    return pd.DataFrame(rows)


def outlier_robustness(filtered: pd.DataFrame) -> pd.DataFrame:
    rows = [_perf(filtered, "FULL")]
    if filtered.empty:
        return pd.DataFrame(rows)
    r = filtered.sort_values("net_R", ascending=False)
    rows.append(_perf(r.iloc[1:], "exclude_best"))
    rows.append(_perf(r.iloc[3:], "exclude_top3"))
    n1 = max(1, int(np.ceil(len(r) * 0.01)))
    rows.append(_perf(r.iloc[n1:], "exclude_top1pct"))
    return pd.DataFrame(rows)


def bootstrap_improvement(baseline: pd.DataFrame, filtered: pd.DataFrame, *, n: int = BOOTSTRAP_SIMS) -> dict:
    rng = np.random.default_rng(42)
    base_r = baseline["net_R"].astype(float).values
    filt_r = filtered["net_R"].astype(float).values
    diffs = []
    for _ in range(n):
        bi = rng.integers(0, len(base_r), len(base_r))
        fi = rng.integers(0, len(filt_r), len(filt_r))
        diffs.append(float(filt_r[fi].mean() - base_r[bi].mean()))
    diffs = np.array(diffs)
    lo, hi = np.quantile(diffs, [0.025, 0.975])
    return {
        "mean_improvement": float(diffs.mean()),
        "ci_lo": float(lo),
        "ci_hi": float(hi),
        "ci_excludes_zero": bool(lo > 0 or hi < 0),
    }


def monte_carlo(filtered: pd.DataFrame, *, n: int = MC_SIMS) -> dict:
    from phase17.analysis_core import max_drawdown

    if filtered.empty:
        return {}
    r = filtered["net_R"].astype(float).values
    rng = np.random.default_rng(42)
    terminals, maxdds, streaks = [], [], []
    for _ in range(n):
        seq = r[rng.integers(0, len(r), len(r))]
        terminals.append(float(seq.sum()))
        maxdds.append(max_drawdown(seq))
        ls, cur = 0, 0
        for x in seq:
            if x < 0:
                cur += 1
                ls = max(ls, cur)
            else:
                cur = 0
        streaks.append(ls)
    terminals = np.array(terminals)
    maxdds = np.array(maxdds)
    streaks = np.array(streaks)
    return {
        "P_terminal_R_positive": float((terminals > 0).mean()),
        "median_terminal_R": float(np.median(terminals)),
        "p5_terminal_R": float(np.quantile(terminals, 0.05)),
        "p95_terminal_R": float(np.quantile(terminals, 0.95)),
        "median_MaxDD": float(np.median(maxdds)),
        "p95_MaxDD": float(np.quantile(maxdds, 0.95)),
        "median_losing_streak": float(np.median(streaks)),
        "p95_losing_streak": float(np.quantile(streaks, 0.95)),
    }


def threshold_stability(folds: pd.DataFrame) -> pd.DataFrame:
    cols = ["train_threshold", "train_q05", "train_q95"]
    row = {c: folds[c].astype(float) for c in cols if c in folds.columns}
    out = {
        "metric": ["min", "max", "median", "std"],
    }
    for c in cols:
        if c in row:
            s = row[c]
            out[c] = [float(s.min()), float(s.max()), float(s.median()), float(s.std())]
    return pd.DataFrame(out)


def trades_per_day(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    from phase16.indicators import is_in_session
    from phase16.resample import cme_session_date
    from .config import RTH_SESSION

    dates = set()
    for ts in pd.to_datetime(df["marker_bar_timestamp"]):
        if is_in_session(ts, RTH_SESSION):
            dates.add(cme_session_date(pd.DatetimeIndex([ts]))[0])
    return len(df) / len(dates) if dates else 0.0


def apply_fixed_rule(dataset: pd.DataFrame) -> pd.DataFrame:
    from .config import (
        FIXED_Q_PASS_MIN,
        FIXED_Q_RAW_HI,
        FIXED_Q_RAW_LO,
        FIXED_Q_TIER_A,
        FIXED_Q_TIER_APLUS,
        FIXED_Q_TIER_B,
    )
    from .features import normalize_score

    out = dataset.copy()
    raw = out["pine_simple_raw"].astype(float).values
    score = normalize_score(raw, FIXED_Q_RAW_LO, FIXED_Q_RAW_HI)
    out["fixed_quality_score"] = score
    out["fixed_quality_pass"] = score >= FIXED_Q_PASS_MIN
    out["fixed_confidence"] = np.where(
        score < FIXED_Q_PASS_MIN,
        "C",
        np.where(
            score >= FIXED_Q_TIER_APLUS,
            "A+",
            np.where(score >= FIXED_Q_TIER_A, "A", "B"),
        ),
    )
    return out


def pine_parity_windows(dataset: pd.DataFrame, accepted: pd.DataFrame, rejected: pd.DataFrame) -> pd.DataFrame:
    market = None
    try:
        from phase36.data import load_replay_market_15m

        market = load_replay_market_15m()
    except Exception:
        pass
    pos = {ts: i for i, ts in enumerate(market.index)} if market is not None else {}

    def pick(df: pd.DataFrame, tier: str, st: str) -> pd.Series | None:
        sub = df.loc[(df.get("confidence", df.get("fixed_confidence")) == tier) & (df["signal_type"] == st)]
        return sub.iloc[0] if not sub.empty else None

    rows = []
    for label, df, tier, st in [
        ("A+ L", accepted, "A+", "L"),
        ("A+ S", accepted, "A+", "S"),
        ("A RL", accepted, "A", "RL"),
        ("A RS", accepted, "A", "RS"),
        ("B accepted", accepted, "B", "L"),
        ("quality rejected", rejected, "C", "L"),
    ]:
        row = pick(df, tier, st)
        if row is None:
            continue
        ts = pd.Timestamp(row["marker_bar_timestamp"])
        c0 = float(market.loc[ts, "close"]) if ts in pos else np.nan
        i = pos.get(ts, 0)
        c1 = float(market.iloc[i - 1]["close"]) if i >= 1 else np.nan
        c2 = float(market.iloc[i - 2]["close"]) if i >= 2 else np.nan
        c3 = float(market.iloc[i - 3]["close"]) if i >= 3 else np.nan
        rows.append(
            {
                "window": label,
                "timestamp": ts,
                "signal_type": st,
                "direction": row["direction"],
                "close": c0,
                "close_1": c1,
                "close_2": c2,
                "close_3": c3,
                "ret_1": row.get("pine_ret_1", row.get("ret_1_atr")),
                "ret_2": row.get("pine_ret_2", row.get("ret_2_atr")),
                "ret_3": row.get("pine_ret_3", row.get("ret_3_atr")),
                "simple_raw": row.get("simple_raw", row.get("pine_simple_raw")),
                "quality_score": row.get("quality_score", row.get("fixed_quality_score")),
                "tier": tier,
                "accepted": tier != "C",
            }
        )
    return pd.DataFrame(rows)
