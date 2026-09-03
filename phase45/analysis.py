"""Forward validation metrics, rolling summaries, checkpoints, drift monitoring."""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from phase17.analysis_core import max_drawdown
from phase31.metrics import apply_costs, performance
from phase31.dedupe import rth_trading_dates

from .config import (
    BENCHMARK_FILTERED,
    BENCHMARK_REJECTED,
    BENCHMARK_TIERS,
    CHECKPOINTS,
    DRIFT_WARN_AVGR,
    DRIFT_WARN_PF,
    PRIMARY_CHECKPOINTS,
    ROLLING_WINDOWS,
)


def _perf(df: pd.DataFrame, label: str = "", *, col: str = "net_R") -> dict:
    p = performance(df, col=col)
    p["segment"] = label
    if not df.empty and "wrong_direction_flag" in df.columns:
        p["wrong_direction_rate"] = float(df["wrong_direction_flag"].mean())
    elif not df.empty and "behavior_class" in df.columns:
        p["wrong_direction_rate"] = float((df["behavior_class"] == "WRONG_DIRECTION").mean())
    return p


def trades_per_day(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    from phase16.indicators import is_in_session
    from phase16.resample import cme_session_date
    from .config import RTH_SESSION

    dates = set()
    for ts in pd.to_datetime(df["timestamp"]):
        if is_in_session(ts, RTH_SESSION):
            dates.add(cme_session_date(pd.DatetimeIndex([ts]))[0])
    return len(df) / len(dates) if dates else 0.0


def signal_type_results(log: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for st in ("L", "S", "RL", "RS"):
        sub = log.loc[log["signal_type"] == st]
        acc = sub.loc[sub["accepted"]]
        rows.append(
            {
                "signal_type": st,
                "total_N": len(sub),
                "accepted_N": len(acc),
                "retention": len(acc) / len(sub) if len(sub) else 0,
                "all_AvgR": performance(sub, col="net_R").get("AvgR", 0) if "net_R" in sub.columns else np.nan,
                "accepted_AvgR": performance(acc, col="net_R").get("AvgR", 0) if len(acc) else np.nan,
                "accepted_PF": performance(acc, col="net_R").get("PF", 0) if len(acc) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def continuation_reversal(log: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, types in (("CONTINUATION", ("L", "S")), ("REVERSAL", ("RL", "RS"))):
        for tag, mask_col in (("all", slice(None)), ("accepted", True)):
            sub = log.loc[log["signal_type"].isin(types)]
            if tag == "accepted":
                sub = sub.loc[sub["accepted"]]
            p = performance(sub, col="net_R") if "net_R" in sub.columns else {"N": len(sub)}
            p["group"] = label
            p["variant"] = tag
            rows.append(p)
    return pd.DataFrame(rows)


def confidence_results(log: pd.DataFrame) -> pd.DataFrame:
    rows = []
    tiers = [
        ("REJECTED", log["confidence_tier"] == "REJECTED"),
        ("B", log["confidence_tier"] == "B"),
        ("A", log["confidence_tier"] == "A"),
        ("A+", log["confidence_tier"] == "A+"),
    ]
    for tier, mask in tiers:
        sub = log.loc[mask]
        p = _perf(sub, tier)
        if not sub.empty:
            p["MFE"] = float(sub["MFE_R"].mean()) if "MFE_R" in sub.columns else np.nan
            p["MAE"] = float(sub["MAE_R"].mean()) if "MAE_R" in sub.columns else np.nan
            p["benchmark_AvgR"] = BENCHMARK_TIERS.get(tier.replace("REJECTED", ""), BENCHMARK_REJECTED["AvgR"])
        rows.append(p)
    return pd.DataFrame(rows)


def quality_ordering(log: pd.DataFrame) -> str:
    if log.empty or log["accepted"].sum() < 30:
        return "INSUFFICIENT DATA"
    tiers = confidence_results(log)
    avgs = {r["segment"]: r.get("AvgR", np.nan) for _, r in tiers.iterrows()}
    if avgs.get("A+", np.nan) > avgs.get("A", np.nan) > avgs.get("B", np.nan) > avgs.get("REJECTED", np.nan):
        return "PASS"
    if avgs.get("A+", np.nan) > avgs.get("REJECTED", np.nan) and avgs.get("B", np.nan) > avgs.get("REJECTED", np.nan):
        return "PARTIAL"
    return "FAIL"


def period_results(log: pd.DataFrame, freq: str) -> pd.DataFrame:
    if log.empty:
        return pd.DataFrame()
    d = log.copy()
    d["period"] = pd.to_datetime(d["timestamp"]).dt.to_period(freq)
    rows = []
    for period, grp in d.groupby("period"):
        acc = grp.loc[grp["accepted"]]
        rows.append(
            {
                "period": str(period),
                "total_N": len(grp),
                "accepted_N": len(acc),
                "AvgR": performance(acc, col="net_R").get("AvgR", 0) if len(acc) else np.nan,
                "PF": performance(acc, col="net_R").get("PF", 0) if len(acc) else np.nan,
                "WinRate": performance(acc, col="net_R").get("WinRate", 0) if len(acc) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def rolling_results(log: pd.DataFrame) -> pd.DataFrame:
    acc = log.loc[log["accepted"]].sort_values("timestamp")
    if acc.empty:
        return pd.DataFrame()
    rows = []
    for w in ROLLING_WINDOWS:
        for i in range(w, len(acc) + 1):
            sub = acc.iloc[i - w : i]
            p = performance(sub, col="net_R")
            rows.append(
                {
                    "window": w,
                    "end_timestamp": sub["timestamp"].iloc[-1],
                    "N": w,
                    "AvgR": p["AvgR"],
                    "PF": p["PF"],
                    "WinRate": p["WinRate"],
                    "MaxDD": p["MaxDD"],
                    "mean_quality": float(sub["quality_score"].mean()),
                }
            )
    return pd.DataFrame(rows)


def cost_stress(log: pd.DataFrame) -> pd.DataFrame:
    acc = log.loc[log["accepted"]].copy()
    if acc.empty:
        return pd.DataFrame()
    if "stop_price" not in acc.columns:
        acc["stop_price"] = acc["stop"]
    rows = []
    for mult in (1.0, 1.5, 2.0):
        tmp = acc.copy()
        tmp["net_R"] = apply_costs(tmp.assign(realized_R=tmp["gross_R"]), multiplier=mult, col="realized_R")
        p = performance(tmp, col="net_R")
        p["cost_multiplier"] = mult
        rows.append(p)
    return pd.DataFrame(rows)


def validation_checkpoints(log: pd.DataFrame) -> pd.DataFrame:
    acc = log.loc[log["accepted"]].sort_values("timestamp")
    rows = []
    for cp in CHECKPOINTS:
        sub = acc.head(cp)
        if sub.empty:
            rows.append({"checkpoint": cp, "reached": False, "N": 0})
            continue
        p = performance(sub, col="net_R")
        rows.append(
            {
                "checkpoint": cp,
                "reached": len(acc) >= cp,
                "N": len(sub),
                "AvgR": p["AvgR"],
                "PF": p["PF"],
                "TotalR": p["TotalR"],
                "MaxDD": p["MaxDD"],
                "WinRate": p["WinRate"],
                "primary": cp in PRIMARY_CHECKPOINTS,
                "uncertainty_note": "HIGH" if cp < 100 else "MODERATE" if cp < 200 else "LOW",
            }
        )
    return pd.DataFrame(rows)


def current_checkpoint(log: pd.DataFrame) -> int:
    n = int(log.loc[log["accepted"]].shape[0])
    reached = [cp for cp in CHECKPOINTS if n >= cp]
    return reached[-1] if reached else 0


def drift_monitor(log: pd.DataFrame, *, benchmark: dict = BENCHMARK_FILTERED) -> pd.DataFrame:
    acc = log.loc[log["accepted"]]
    rej = log.loc[log["accepted"] == False]
    warnings: List[str] = []

    if not acc.empty:
        p = performance(acc, col="net_R")
        if p["PF"] < DRIFT_WARN_PF:
            warnings.append("PF_BELOW_1")
        if p["AvgR"] < DRIFT_WARN_AVGR:
            warnings.append("AVGR_NEGATIVE")
        if not rej.empty:
            rej_p = performance(rej.loc[rej["impulse_filter_pass"]], col="net_R")
            if rej_p["AvgR"] > p["AvgR"]:
                warnings.append("REJECTED_OUTPERFORMING_ACCEPTED")
        tier = confidence_results(log)
        aplus = tier.loc[tier["segment"] == "A+", "AvgR"]
        b = tier.loc[tier["segment"] == "B", "AvgR"]
        if not aplus.empty and not b.empty and float(aplus.iloc[0]) < float(b.iloc[0]) and len(acc) >= 20:
            warnings.append("APLUS_UNDERPERFORMING_B")

    freq = trades_per_day(acc) if not acc.empty else 0
    hist_freq = benchmark["N"] / (2788 / 3.19) if benchmark["N"] else 0  # rough benchmark tpd
    if freq > 0 and hist_freq > 0 and abs(freq - 3.19) / 3.19 > 0.5 and len(acc) >= 25:
        warnings.append("SIGNAL_FREQUENCY_SHIFT")

    mix = log["signal_type"].value_counts(normalize=True).to_dict() if not log.empty else {}
    rows = [
        {"metric": "forward_accepted_N", "value": len(acc), "benchmark": benchmark["N"]},
        {"metric": "forward_AvgR", "value": performance(acc, col="net_R").get("AvgR", np.nan) if not acc.empty else np.nan, "benchmark": benchmark["AvgR"]},
        {"metric": "forward_PF", "value": performance(acc, col="net_R").get("PF", np.nan) if not acc.empty else np.nan, "benchmark": benchmark["PF"]},
        {"metric": "trades_per_day", "value": freq, "benchmark": 3.19},
        {"metric": "mean_quality_score", "value": float(acc["quality_score"].mean()) if not acc.empty else np.nan, "benchmark": np.nan},
        {"metric": "warnings", "value": ";".join(warnings) if warnings else "NONE", "benchmark": ""},
        {"metric": "signal_mix", "value": str(mix), "benchmark": ""},
    ]
    return pd.DataFrame(rows)


def population_summary(log: pd.DataFrame) -> Dict[str, dict]:
    acc = log.loc[log["accepted"]]
    rej = log.loc[~log["accepted"]]
    impulse_pass = log.loc[log["impulse_filter_pass"]]
    return {
        "accepted": performance(acc, col="net_R") if not acc.empty else {"N": 0},
        "rejected": performance(rej.loc[rej["impulse_filter_pass"]], col="net_R") if not impulse_pass.empty else {"N": 0},
        "all_candidates": performance(impulse_pass, col="net_R") if not impulse_pass.empty else {"N": 0},
        "total_candidates": {"N": len(log)},
    }
