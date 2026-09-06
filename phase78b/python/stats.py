"""Report helpers and structural risk audit."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase78.python.paths import risk_points

from .taxonomy import bucket_first_sweep, classify_level, report_label


def pctiles(s: pd.Series) -> dict:
    s = s.dropna()
    if len(s) == 0:
        return {}
    return {
        "median": float(s.median()),
        "p10": float(s.quantile(0.10)),
        "p25": float(s.quantile(0.25)),
        "p75": float(s.quantile(0.75)),
        "p90": float(s.quantile(0.90)),
    }


def performance_summary(df: pd.DataFrame) -> dict:
    if len(df) == 0:
        return {"n": 0}
    return {
        "n": len(df),
        "long_n": int((df["direction"] == "LONG").sum()),
        "short_n": int((df["direction"] == "SHORT").sum()),
        "plus_1": float(df["plus_1.0R_before_minus_1R"].mean()),
        "plus_2": float(df["plus_2.0R_before_minus_1R"].mean()),
        "plus_2_5": float(df["plus_2.5R_before_minus_1R"].mean()),
        "mfe_15m": float(df["mfe_15m"].mean()),
        "mae_15m": float(df["mae_15m"].mean()),
        "gross_avg_r": float(df["outcome_r"].mean()),
    }


def audit_structural_risk(entries: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for i, r in entries.iterrows():
        rp = risk_points(r["entry_price"], r["stop"], r["direction"])
        reason = "VALID"
        if rp < 0:
            reason = "STOP_WRONG_SIDE"
        elif rp == 0:
            reason = "ZERO_RISK"
        elif not np.isfinite(rp):
            reason = "OTHER"
        if reason != "VALID":
            rows.append(
                {
                    "idx": i,
                    "calendar_date": r["calendar_date"],
                    "window_id": r["window_id"],
                    "direction": r["direction"],
                    "entry_price": r["entry_price"],
                    "stop": r["stop"],
                    "risk_points": rp,
                    "liquidity_type": r["liquidity_type"],
                    "reason": reason,
                }
            )
    return pd.DataFrame(rows)


def entry_timing_audit(entries: pd.DataFrame) -> dict:
    e = entries.copy()
    for col in ("sweep_time", "displacement_time", "mss_time", "fvg_created", "retrace_time", "entry_time"):
        e[col] = pd.to_datetime(e[col])
    e["sweep_to_disp_m"] = (e["displacement_time"] - e["sweep_time"]).dt.total_seconds() / 60
    e["sweep_to_mss_m"] = (e["mss_time"] - e["sweep_time"]).dt.total_seconds() / 60
    e["sweep_to_fvg_m"] = (e["fvg_created"] - e["sweep_time"]).dt.total_seconds() / 60
    e["fvg_to_retrace_m"] = (e["retrace_time"] - e["fvg_created"]).dt.total_seconds() / 60
    e["sweep_to_entry_m"] = (e["entry_time"] - e["sweep_time"]).dt.total_seconds() / 60
    move_before = []
    for _, r in e.iterrows():
        atr = r.get("atr", np.nan)
        if not np.isfinite(atr) or atr <= 0:
            move_before.append(np.nan)
            continue
        if r["direction"] == "LONG":
            move_before.append(abs(r["entry_price"] - r["sweep_extreme"]) / atr)
        else:
            move_before.append(abs(r["sweep_extreme"] - r["entry_price"]) / atr)
    e["move_before_entry_atr"] = move_before
    e["remaining_mfe_atr"] = e["mfe_60m"] / e["atr"]
    return {
        "sweep_to_entry_m": pctiles(e["sweep_to_entry_m"]),
        "fvg_to_retrace_m": pctiles(e["fvg_to_retrace_m"]),
        "move_before_entry_atr": pctiles(e["move_before_entry_atr"]),
        "remaining_mfe_atr": pctiles(e["remaining_mfe_atr"]),
        "median_sweep_to_entry_m": float(e["sweep_to_entry_m"].median()),
    }


def enrich_entries(entries: pd.DataFrame) -> pd.DataFrame:
    out = entries.copy()
    out["liquidity_class"] = out["liquidity_type"].map(classify_level)
    out["liquidity_report"] = out["liquidity_type"].map(report_label)
    out["first_sweep_bucket"] = out["liquidity_type"].map(bucket_first_sweep)
    return out
