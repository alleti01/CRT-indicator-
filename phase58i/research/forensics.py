"""Part A — management forensics and loss classification."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58b.research.precompute import MTFArrays
from phase58b.research.simulation import metrics
from phase58i.research.path_analysis import (
    mae_before_threshold,
    path_excursions,
    post_exit_excursion,
    time_to_threshold,
    _risk_pts,
)


def classify_loss(row: pd.Series, post_stop_60: float, post_exit_30: float) -> str:
    """Evaluation-only loss classification."""
    if row["net_R"] > 0:
        return "WINNER"
    mfe = row.get("MFE_R", 0) or 0
    reason = row.get("exit_reason", "")
    mae = row.get("MAE_R", 0) or 0

    if mfe < 0.25 and post_stop_60 < 0.5:
        return "WRONG_DIRECTION"
    if reason == "STOP" and post_stop_60 >= 1.0:
        return "RIGHT_DIRECTION_BAD_STOP"
    if reason == "TIME" and post_exit_30 >= 1.0:
        return "RIGHT_DIRECTION_TOO_EARLY_EXIT"
    if reason == "TIME" and mfe >= 0.5 and row["net_R"] < 0.5:
        return "RIGHT_DIRECTION_SLOW_DEVELOPMENT"
    if reason == "TIME" and mfe < 0.25:
        return "NO_FOLLOW_THROUGH"
    if mae > 0.75 and mfe < 0.5:
        return "CHOP"
    return "AMBIGUOUS"


def run_forensics(m: MTFArrays, trades: pd.DataFrame, cfg: dict) -> dict:
    """Compute forensic tables for a trade population."""
    rows = []
    horizons = cfg.get("post_stop_horizons_min", [5, 15, 30, 60])
    recovery = cfg.get("recovery_thresholds_r", [0.5, 1.0, 1.5, 2.0, 2.5])

    stop_ix = trades.index[trades["exit_reason"] == "STOP"]
    time_ix = trades.index[trades["exit_reason"] == "TIME"]

    for idx in trades.index:
        t = trades.loc[idx]
        ei = int(t["entry_i"])
        ex = int(t["exit_i"])
        ep = float(t["entry_price"])
        risk = _risk_pts(ep, float(t["stop"]))
        d = t["direction"]

        post_stop_60 = 0.0
        post_exit_30 = 0.0
        if t["exit_reason"] == "STOP" and idx in stop_ix:
            post_stop_60 = post_exit_excursion(m, ei, ex, d, ep, risk, 60)
        if t["exit_reason"] == "TIME" and idx in time_ix:
            post_exit_30 = post_exit_excursion(m, ei, ex, d, ep, risk, 30)

        row = {
            "trade_id": t["trade_id"],
            "net_R": t["net_R"],
            "exit_reason": t["exit_reason"],
            "MFE_R": t.get("MFE_R", np.nan),
            "MAE_R": t.get("MAE_R", np.nan),
            "post_stop_60": post_stop_60,
            "post_exit_30": post_exit_30,
        }
        for thr in recovery:
            row[f"post_stop_reach_{thr}R"] = post_stop_60 >= thr if t["exit_reason"] == "STOP" else False
        row["loss_class"] = classify_loss(pd.Series(row), post_stop_60, post_exit_30)
        rows.append(row)

    detail = pd.DataFrame(rows)
    losers = detail.loc[detail["net_R"] <= 0]
    n_loss = len(losers)

    loss_summary = []
    for cls in [
        "WRONG_DIRECTION", "RIGHT_DIRECTION_BAD_STOP", "RIGHT_DIRECTION_TOO_EARLY_EXIT",
        "RIGHT_DIRECTION_SLOW_DEVELOPMENT", "NO_FOLLOW_THROUGH", "CHOP", "AMBIGUOUS",
    ]:
        sub = losers.loc[losers["loss_class"] == cls]
        if sub.empty:
            continue
        loss_summary.append({
            "loss_type": cls,
            "count": len(sub),
            "pct_of_losses": len(sub) / n_loss * 100 if n_loss else 0,
            "avg_pre_exit_mfe": sub["MFE_R"].mean(),
            "avg_post_exit_mfe": sub["post_stop_60"].where(sub["exit_reason"] == "STOP", sub["post_exit_30"]).mean(),
            "avg_mae": sub["MAE_R"].mean(),
            "avg_r": sub["net_R"].mean(),
        })

    mgmt_confusion = {}
    for thr in [1.0, 2.0, 2.5]:
        mgmt_confusion[f"later_{thr}R"] = (
            (losers["exit_reason"] == "STOP") & (losers["post_stop_60"] >= thr)
        ).sum() / n_loss * 100 if n_loss else 0

    stop_outs = detail.loc[detail["exit_reason"] == "STOP"]
    pre_stop_buckets = pd.cut(
        stop_outs["MFE_R"].fillna(0),
        bins=[-np.inf, 0.25, 0.5, 1.0, 1.5, 2.0, np.inf],
        labels=["<0.25R", "0.25-0.5R", "0.5-1.0R", "1.0-1.5R", "1.5-2.0R", ">2.0R"],
    )
    pre_stop = stop_outs.groupby(pre_stop_buckets, observed=True).size().reset_index(name="count")
    pre_stop.columns = ["bucket", "count"]

    recovery_rows = []
    for thr in recovery:
        recovery_rows.append({
            "threshold_r": thr,
            "stop_outs_reaching": int((stop_outs[f"post_stop_reach_{thr}R"]).sum()) if f"post_stop_reach_{thr}R" in stop_outs.columns else 0,
            "pct_of_stops": (stop_outs[f"post_stop_reach_{thr}R"]).mean() * 100 if len(stop_outs) else 0,
        })

    winners = trades.loc[trades["net_R"] > 0]
    winner_mae = []
    for thr in [0.5, 1.0, 2.0, 2.5]:
        maes = []
        for _, w in winners.head(5000).iterrows():
            ei = int(w["entry_i"])
            ep = float(w["entry_price"])
            risk = _risk_pts(ep, float(w["stop"]))
            maes.append(mae_before_threshold(m, ei, w["direction"], ep, risk, thr))
        winner_mae.append({"threshold_r": thr, "median_mae_before": float(np.median(maes)), "p75_mae_before": float(np.percentile(maes, 75))})

    time_fav = []
    for thr in [0.5, 1.0, 2.0, 2.5]:
        times = []
        for _, w in winners.head(3000).iterrows():
            ei = int(w["entry_i"])
            ep = float(w["entry_price"])
            risk = _risk_pts(ep, float(w["stop"]))
            t = time_to_threshold(m, ei, w["direction"], ep, risk, thr)
            if t is not None:
                times.append(t)
        time_fav.append({
            "threshold_r": thr,
            "median_bars": float(np.median(times)) if times else np.nan,
            "p25": float(np.percentile(times, 25)) if times else np.nan,
            "p75": float(np.percentile(times, 75)) if times else np.nan,
            "p90": float(np.percentile(times, 90)) if times else np.nan,
        })

    time_exits = detail.loc[detail["exit_reason"] == "TIME"].merge(
        trades[["trade_id", "entry_i", "exit_i", "entry_price", "stop", "direction"]], on="trade_id"
    )
    time_forensics = []
    for h in [15, 30, 60]:
        vals = []
        for _, tx in time_exits.head(3000).iterrows():
            ei = int(tx["entry_i"])
            ex = int(tx["exit_i"])
            ep = float(tx["entry_price"])
            risk = _risk_pts(ep, float(tx["stop"]))
            vals.append(post_exit_excursion(m, ei, ex, tx["direction"], ep, risk, h))
        time_forensics.append({"horizon_min": h, "median_post_exit_mfe": float(np.median(vals)) if vals else 0})

    targets = trades.loc[trades["exit_reason"] == "TARGET"]
    ext = []
    if not targets.empty and "MFE_R" in targets.columns:
        mfe = targets["MFE_R"]
        for lo, hi, label in [(2.5, 3, "2.5-3R"), (3, 4, "3-4R"), (4, 5, "4-5R"), (5, 999, "5R+")]:
            ext.append({"bucket": label, "count": int(((mfe >= lo) & (mfe < hi)).sum())})

    giveback_rows = []
    for thr in [0.5, 1.0, 1.5, 2.0]:
        reached = detail.loc[detail["MFE_R"] >= thr]
        if reached.empty:
            continue
        giveback_rows.append({
            "mfe_threshold": thr,
            "count": len(reached),
            "avg_realized_r": reached["net_R"].mean(),
            "avg_giveback": (reached["MFE_R"] - reached["net_R"]).mean(),
            "pct_stopped_after": (reached["exit_reason"] == "STOP").mean() * 100,
        })

    exc_rows = []
    mfe_bins = [0, 0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 999]
    mfe_labels = ["<0.25R", "0.25-0.5R", "0.5-1R", "1-1.5R", "1.5-2R", "2-2.5R", "2.5R+"]
    detail["mfe_bin"] = pd.cut(detail["MFE_R"].fillna(0), bins=mfe_bins, labels=mfe_labels)
    for mb in mfe_labels:
        sub = detail.loc[detail["mfe_bin"] == mb]
        if sub.empty:
            continue
        exc_rows.append({
            "mfe_bin": mb,
            "stop": (sub["exit_reason"] == "STOP").sum(),
            "time_exit": (sub["exit_reason"] == "TIME").sum(),
            "target": (sub["exit_reason"] == "TARGET").sum(),
            "total": len(sub),
        })

    dir_mgmt = []
    for dg, mg in [("GOOD", "GOOD"), ("GOOD", "BAD"), ("BAD", "GOOD"), ("BAD", "BAD")]:
        dir_ok = detail["net_R"] > 0 if dg == "GOOD" else detail["net_R"] <= 0
        mgmt_ok = ~detail["loss_class"].isin(["WRONG_DIRECTION", "RIGHT_DIRECTION_BAD_STOP", "RIGHT_DIRECTION_TOO_EARLY_EXIT"]) if mg == "GOOD" else detail["loss_class"].isin(["RIGHT_DIRECTION_BAD_STOP", "RIGHT_DIRECTION_TOO_EARLY_EXIT", "RIGHT_DIRECTION_SLOW_DEVELOPMENT"])
        sub = detail.loc[dir_ok & mgmt_ok]
        if len(sub) > 0:
            dir_mgmt.append({"direction_quality": dg, "management_quality": mg, "count": len(sub), "total_r": sub["net_R"].sum(), "avg_r": sub["net_R"].mean()})

    return {
        "detail": detail,
        "loss_summary": pd.DataFrame(loss_summary),
        "management_confusion": pd.DataFrame([mgmt_confusion]),
        "pre_stop_mfe": pre_stop,
        "post_stop_recovery": pd.DataFrame(recovery_rows),
        "winner_mae": pd.DataFrame(winner_mae),
        "time_to_favorable": pd.DataFrame(time_fav),
        "time_exit_forensics": pd.DataFrame(time_forensics),
        "target_forensics": pd.DataFrame(ext),
        "winner_giveback": pd.DataFrame(giveback_rows),
        "excursion_matrix": pd.DataFrame(exc_rows),
        "direction_management_matrix": pd.DataFrame(dir_mgmt),
    }


def population_forensics_summary(trades: pd.DataFrame, forensics_detail: pd.DataFrame) -> dict:
    losers = forensics_detail.loc[forensics_detail["net_R"] <= 0]
    n = len(losers)
    mgmt_like = losers["loss_class"].isin(["RIGHT_DIRECTION_BAD_STOP", "RIGHT_DIRECTION_TOO_EARLY_EXIT", "RIGHT_DIRECTION_SLOW_DEVELOPMENT"]).mean() * 100 if n else 0
    wrong_like = (losers["loss_class"] == "WRONG_DIRECTION").mean() * 100 if n else 0
    m = metrics(trades["net_R"].values)
    return {
        "trades": len(trades),
        "avg_r": m.get("AvgR", 0),
        "total_r": m.get("TotalR", 0),
        "management_loss_like_pct": mgmt_like,
        "wrong_direction_like_pct": wrong_like,
    }
