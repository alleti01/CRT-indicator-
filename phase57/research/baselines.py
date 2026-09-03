"""Baseline computation — raw population performance for every event family.

B0: random directional baseline
B1-B6: raw FVG / ORB / leg-pullback / retest / reversal / continuation
B7: frozen S54 diagnostic  B8: frozen CORE diagnostic
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase53.research.metrics import max_dd, pf, summarize_r
from phase57.config import HOLDOUT_START, RESULTS, WALK_FORWARD_FOLDS
from phase57.research.outcomes import batch_simulate


def _split_train_oos(df: pd.DataFrame, ts_col: str = "timestamp_ct") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pre-holdout split: train = all, OOS = stitched WF test folds."""
    ts = pd.to_datetime(df[ts_col])
    tz = ts.iloc[0].tz if len(ts) and hasattr(ts.iloc[0], "tz") else None
    holdout = pd.Timestamp(HOLDOUT_START, tz=tz)
    pre = df.loc[ts < holdout]
    oos_parts = []
    for _, _, te_s, te_e in WALK_FORWARD_FOLDS:
        mask = (ts >= pd.Timestamp(te_s, tz=tz)) & (ts <= pd.Timestamp(te_e, tz=tz))
        oos_parts.append(df.loc[mask])
    oos = pd.concat(oos_parts, ignore_index=True) if oos_parts else pd.DataFrame()
    return pre, oos


def baseline_metrics(
    m1: pd.DataFrame,
    events: pd.DataFrame,
    label: str,
    *,
    entry_col: str = "entry_i",
    dir_col: str = "direction",
    ts_col: str = "timestamp_ct",
) -> dict:
    """Compute AvgR, PF, TotalR, MaxDD, win_rate, trades/day for a population."""
    if events.empty:
        return {"label": label, "N": 0}
    trades = batch_simulate(m1, events.rename(columns={entry_col: "entry_i", dir_col: "direction"}))
    if trades.empty:
        return {"label": label, "N": 0}
    trades["timestamp_ct"] = events[ts_col].values[:len(trades)]
    sm = summarize_r(trades)
    # Year stability
    trades["year"] = pd.to_datetime(trades["timestamp_ct"]).dt.year
    yr_stable = True
    for y, g in trades.groupby("year"):
        if len(g) >= 20 and g["net_R"].mean() <= 0:
            yr_stable = False
    return {
        "label": label,
        **sm,
        "year_stable": yr_stable,
    }


def year_breakdown(
    m1: pd.DataFrame,
    events: pd.DataFrame,
    *,
    entry_col: str = "entry_i",
    dir_col: str = "direction",
    ts_col: str = "timestamp_ct",
) -> pd.DataFrame:
    """Per-year AvgR, PF, N, TotalR, MaxDD, win_rate."""
    if events.empty:
        return pd.DataFrame()
    trades = batch_simulate(m1, events.rename(columns={entry_col: "entry_i", dir_col: "direction"}))
    if trades.empty:
        return pd.DataFrame()
    trades["timestamp_ct"] = events[ts_col].values[:len(trades)]
    trades["year"] = pd.to_datetime(trades["timestamp_ct"]).dt.year
    rows = []
    for y, g in trades.groupby("year"):
        sm = summarize_r(g)
        long = g.loc[g["direction"] == "LONG"]
        short = g.loc[g["direction"] == "SHORT"]
        rows.append({
            "year": y,
            **sm,
            "LONG_AvgR": float(long["net_R"].mean()) if len(long) else np.nan,
            "SHORT_AvgR": float(short["net_R"].mean()) if len(short) else np.nan,
        })
    return pd.DataFrame(rows)


def cliff_detection(
    m1: pd.DataFrame,
    events: pd.DataFrame,
    var_col: str,
    *,
    n_bins: int = 10,
    entry_col: str = "entry_i",
    dir_col: str = "direction",
) -> pd.DataFrame:
    """Decile analysis for continuous variable — detect threshold cliffs."""
    if events.empty or var_col not in events.columns:
        return pd.DataFrame()
    ev = events.dropna(subset=[var_col]).copy()
    if len(ev) < n_bins * 10:
        return pd.DataFrame()
    ev["decile"] = pd.qcut(ev[var_col].astype(float), n_bins, labels=False, duplicates="drop") + 1
    rows = []
    for d, g in ev.groupby("decile"):
        trades = batch_simulate(m1, g.rename(columns={entry_col: "entry_i", dir_col: "direction"}))
        if trades.empty:
            continue
        rows.append({"decile": int(d), "N": len(trades), "AvgR": float(trades["net_R"].mean()), "PF": pf(trades["net_R"]), "var_mean": float(g[var_col].mean())})
    out = pd.DataFrame(rows)
    if len(out) >= 3:
        avg_rs = out["AvgR"].values
        diffs = np.diff(avg_rs)
        max_jump = float(np.max(np.abs(diffs))) if len(diffs) else 0.0
        out.attrs["max_cliff"] = max_jump
        out.attrs["cliff_flag"] = max_jump > 1.5 * np.std(avg_rs) if np.std(avg_rs) > 0 else False
    return out


def opportunity_preservation(
    m1: pd.DataFrame,
    baseline_events: pd.DataFrame,
    selected_events: pd.DataFrame,
    *,
    entry_col: str = "entry_i",
    dir_col: str = "direction",
) -> dict:
    """Measure retention rate, good-trade capture, over-filtering risk."""
    if baseline_events.empty:
        return {"retention_pct": 0, "over_filtering_risk": False}
    base_trades = batch_simulate(m1, baseline_events.rename(columns={entry_col: "entry_i", dir_col: "direction"}))
    sel_trades = batch_simulate(m1, selected_events.rename(columns={entry_col: "entry_i", dir_col: "direction"})) if not selected_events.empty else pd.DataFrame()
    retention = len(sel_trades) / len(base_trades) if len(base_trades) else 0
    base_wins = base_trades.loc[base_trades["net_R"] > 0] if not base_trades.empty else pd.DataFrame()
    sel_entries = set(sel_trades["entry_i"].values) if not sel_trades.empty else set()
    captured_wins = sum(1 for _, r in base_wins.iterrows() if r["entry_i"] in sel_entries) if not base_wins.empty else 0
    good_capture = captured_wins / len(base_wins) if len(base_wins) else 0
    # Rejected trades: baseline minus selected
    rej_entries = set(base_trades["entry_i"].values) - sel_entries
    rej = base_trades.loc[base_trades["entry_i"].isin(rej_entries)]
    rej_avgr = float(rej["net_R"].mean()) if len(rej) else np.nan
    over_filter = retention < 0.3 and not np.isnan(rej_avgr) and rej_avgr > 0.3
    return {
        "baseline_N": len(base_trades),
        "selected_N": len(sel_trades),
        "retention_pct": retention * 100,
        "good_trade_capture_pct": good_capture * 100,
        "rejected_AvgR": rej_avgr,
        "rejected_TotalR": float(rej["net_R"].sum()) if len(rej) else 0,
        "over_filtering_risk": over_filter,
    }
