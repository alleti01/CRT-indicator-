"""Risk normalization and target scaling audits."""
from __future__ import annotations

import numpy as np
import pandas as pd


def risk_audit_row(direction: str, entry: float, stop: float, target: float, gross_r: float, atr: float, stop_atr: float) -> dict:
    risk_pts = abs(entry - stop)
    target_dist = abs(target - entry)
    expected_target = 2.5 * risk_pts
    stop_r = -1.0 if gross_r < 0 and abs(gross_r + 1.0) < 0.01 else gross_r
    if gross_r <= -0.99 and gross_r >= -1.01:
        stop_r = -1.0
    return {
        "stop_distance_points": risk_pts,
        "atr_at_entry": atr,
        "stop_distance_atr": risk_pts / atr if atr > 0 else np.nan,
        "expected_stop_atr": stop_atr,
        "target_distance_points": target_dist,
        "expected_target_distance": expected_target,
        "target_r_implied": target_dist / risk_pts if risk_pts > 0 else np.nan,
        "recorded_gross_r": gross_r,
        "stop_is_minus_1r": abs(gross_r + 1.0) < 0.05 if gross_r < 0 else False,
        "target_is_2p5r": abs(gross_r - 2.5) < 0.05 if gross_r > 0 else False,
    }


def build_risk_audit(trades: pd.DataFrame, stop_atr: float) -> pd.DataFrame:
    rows = []
    for _, t in trades.iterrows():
        row = risk_audit_row(t["direction"], t["entry_price"], t["stop"], t["target"], t["gross_R"], t.get("atr", t.get("atr_at_entry", 1)), stop_atr)
        row["trade_id"] = t["trade_id"]
        row["model"] = t.get("model", "")
        rows.append(row)
    return pd.DataFrame(rows)


def target_scaling_summary(audit: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for model, sub in audit.groupby("model"):
        rows.append({
            "model": model,
            "trades": len(sub),
            "mean_stop_atr": sub["stop_distance_atr"].mean(),
            "mean_target_r_implied": sub["target_r_implied"].mean(),
            "pct_stop_minus_1r": sub["stop_is_minus_1r"].mean() * 100,
            "pct_target_2p5r": sub["target_is_2p5r"].mean() * 100,
            "max_target_r_error": (sub["target_r_implied"] - 2.5).abs().max(),
        })
    return pd.DataFrame(rows)
