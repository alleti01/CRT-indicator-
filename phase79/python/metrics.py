"""Phase79 metrics and attribution."""
from __future__ import annotations

import numpy as np
import pandas as pd


def summarize(trades: pd.DataFrame, *, r_col: str = "net_r") -> dict:
    rs = trades[r_col].astype(float).values
    rs = rs[np.isfinite(rs)]
    if len(rs) == 0:
        return {"N": 0}
    eq = np.cumsum(rs)
    wins = rs[rs > 0]
    losses = rs[rs <= 0]
    pf = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else float("inf")
    reasons = trades.get("exit_reason", pd.Series(dtype=str))
    out = {
        "N": int(len(rs)),
        "LONG": int((trades["direction"] == "LONG").sum()) if "direction" in trades else 0,
        "SHORT": int((trades["direction"] == "SHORT").sum()) if "direction" in trades else 0,
        "WinRate": float((rs > 0).mean()),
        "AvgR": float(rs.mean()),
        "PF": pf,
        "TotalR": float(rs.sum()),
        "MaxDD": float((np.maximum.accumulate(eq) - eq).max()),
        "MedianR": float(np.median(rs)),
        "AvgHold": float(trades["hold_minutes"].mean()) if "hold_minutes" in trades else 0.0,
        "MedianHold": float(trades["hold_minutes"].median()) if "hold_minutes" in trades else 0.0,
        "GrossAvgR": float(trades["gross_r"].mean()) if "gross_r" in trades else float(rs.mean()),
        "GrossTotalR": float(trades["gross_r"].sum()) if "gross_r" in trades else float(rs.sum()),
    }
    if len(reasons):
        n = len(trades)
        out["INITIAL_STOP_PCT"] = float((reasons.isin(["INITIAL_STOP", "M0_STOP"])).mean())
        out["BE_STOP_PCT"] = float((reasons == "BREAKEVEN_STOP").mean())
        out["TARGET_PCT"] = float((reasons.isin(["TARGET", "M0_TARGET", "FIXED_TARGET"])).mean())
        out["TIME_EXIT_PCT"] = float((reasons.isin(["TIME_EXIT", "MAX_HOLD_60M"])).mean())
        out["INITIAL_STOPS"] = int(reasons.isin(["INITIAL_STOP", "M0_STOP"]).sum())
        out["BE_STOPS"] = int((reasons == "BREAKEVEN_STOP").sum())
        out["TARGETS"] = int(reasons.isin(["TARGET", "M0_TARGET", "FIXED_TARGET"]).sum())
        out["TIME_EXITS"] = int(reasons.isin(["TIME_EXIT", "MAX_HOLD_60M"]).sum())
    if "be_activated" in trades:
        out["BE_ACTIVATION_RATE"] = float(trades["be_activated"].mean())
    return out


def compare(baseline: dict, atm: dict) -> dict:
    return {
        "DeltaAvgR": atm.get("AvgR", 0) - baseline.get("AvgR", 0),
        "DeltaTotalR": atm.get("TotalR", 0) - baseline.get("TotalR", 0),
        "DeltaPF": atm.get("PF", 0) - baseline.get("PF", 0),
        "DeltaMaxDD": atm.get("MaxDD", 0) - baseline.get("MaxDD", 0),
        "DeltaGrossAvgR": atm.get("GrossAvgR", 0) - baseline.get("GrossAvgR", 0),
        "DeltaGrossTotalR": atm.get("GrossTotalR", 0) - baseline.get("GrossTotalR", 0),
    }


def normalize_exit(reason: str) -> str:
    r = str(reason)
    if r in ("M0_STOP", "INITIAL_STOP", "STOP"):
        return "STOP"
    if r == "BREAKEVEN_STOP":
        return "BE"
    if r in ("M0_TARGET", "TARGET", "FIXED_TARGET"):
        return "TARGET"
    if r in ("MAX_HOLD_60M", "TIME_EXIT"):
        return "TIME"
    return "OTHER"


def transition_table(base: pd.DataFrame, atm: pd.DataFrame) -> pd.DataFrame:
    m = base.merge(atm, on="trade_id", suffixes=("_base", "_atm"))
    m["base_bucket"] = m["exit_reason_base"].map(normalize_exit)
    m["atm_bucket"] = m["exit_reason_atm"].map(normalize_exit)
    rows = []
    for bb in ["STOP", "TARGET", "TIME"]:
        for ab in ["STOP", "BE", "TARGET", "TIME"]:
            sub = m[(m["base_bucket"] == bb) & (m["atm_bucket"] == ab)]
            if len(sub) == 0:
                continue
            rows.append({
                "transition": f"BASELINE_{bb} → ATM_{ab}",
                "N": len(sub),
                "baseline_TotalR": float(sub["net_r_base"].sum()),
                "ATM_TotalR": float(sub["net_r_atm"].sum()),
                "Delta_TotalR": float(sub["net_r_atm"].sum() - sub["net_r_base"].sum()),
            })
    return pd.DataFrame(rows)


def killed_winners_analysis(base: pd.DataFrame, atm: pd.DataFrame) -> dict:
    m = base.merge(atm, on="trade_id", suffixes=("_base", "_atm"))
    base_winners = m[m["exit_reason_base"].isin(["M0_TARGET", "TARGET", "FIXED_TARGET"])]
    killed = base_winners[base_winners["exit_reason_atm"] == "BREAKEVEN_STOP"]
    n_win = len(base_winners)
    r_lost = float(killed["net_r_base"].sum() - killed["net_r_atm"].sum()) if len(killed) else 0.0
    return {
        "N": int(len(killed)),
        "pct_of_baseline_winners": float(len(killed) / n_win) if n_win else 0.0,
        "R_lost_vs_baseline": r_lost,
        "TotalR_damage": float(killed["net_r_base"].sum() - killed["net_r_atm"].sum()) if len(killed) else 0.0,
    }


def saved_losers_analysis(base: pd.DataFrame, atm: pd.DataFrame) -> dict:
    m = base.merge(atm, on="trade_id", suffixes=("_base", "_atm"))
    base_losers = m[m["exit_reason_base"].isin(["M0_STOP", "INITIAL_STOP", "STOP"])]
    be_col = "be_activated_atm" if "be_activated_atm" in m.columns else "be_activated"
    saved = base_losers[(base_losers[be_col] == True) & (base_losers["net_r_atm"] > base_losers["net_r_base"] + 0.01)]
    n_loss = len(base_losers)
    r_saved = float(saved["net_r_atm"].sum() - saved["net_r_base"].sum()) if len(saved) else 0.0
    return {
        "N": int(len(saved)),
        "pct_of_baseline_losers": float(len(saved) / n_loss) if n_loss else 0.0,
        "R_saved": r_saved,
        "TotalR_improvement": r_saved,
    }


def year_breakdown(trades: pd.DataFrame, *, ts_col: str = "entry_ts") -> pd.DataFrame:
    t = trades.copy()
    t["year"] = pd.to_datetime(t[ts_col]).dt.year
    rows = []
    for y, g in t.groupby("year"):
        s = summarize(g)
        s["year"] = y
        rows.append(s)
    return pd.DataFrame(rows)
