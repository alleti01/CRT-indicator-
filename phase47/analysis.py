"""Analysis tables for Phase 47."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase31.metrics import apply_costs, performance


def _perf(df: pd.DataFrame, col: str = "final_r") -> dict:
    if df.empty:
        return {"N": 0, "AvgR": 0.0, "PF": 0.0, "TotalR": 0.0, "MaxDD": 0.0, "WinRate": 0.0}
    return performance(df, col=col)


def control_summary(control_features: pd.DataFrame, n_oos: int) -> dict:
    p = _perf(control_features, "final_r")
    return {
        "MODEL": "Phase45_B1_Control",
        "N": p["N"],
        "RETENTION": p["N"] / n_oos if n_oos else 0,
        "AvgR": p["AvgR"],
        "PF": p["PF"],
        "TotalR": p["TotalR"],
        "MaxDD": p["MaxDD"],
        "MAE": float(control_features["mae"].mean()),
        "MFE": float(control_features["mfe"].mean()),
        "WrongDir": float(control_features["wrong_direction"].mean()),
        "EntryDelay": float(control_features["b1_delay_min"].mean()),
    }


def variant_summary(wf: pd.DataFrame, n_oos: int) -> pd.DataFrame:
    rows = []
    for v in wf["variant"].unique():
        sub = wf.loc[wf["variant"] == v]
        filled = sub.loc[sub["V_pass"]]
        p = _perf(filled, "V_net_R")
        rows.append({
            "MODEL": v,
            "N": p["N"],
            "RETENTION": p["N"] / n_oos if n_oos else 0,
            "AvgR": p["AvgR"],
            "PF": p["PF"],
            "TotalR": p["TotalR"],
            "MaxDD": p["MaxDD"],
            "MAE": float(filled["V_MAE_R"].mean()) if "V_MAE_R" in filled.columns and len(filled) else np.nan,
            "MFE": float(filled["V_MFE_R"].mean()) if "V_MFE_R" in filled.columns and len(filled) else np.nan,
            "WrongDir": float(filled["V_wrong_direction"].mean()) if "V_wrong_direction" in filled.columns and len(filled) else np.nan,
            "EntryDelay": float(filled["V_delay_min"].mean()) if "V_delay_min" in filled.columns and len(filled) else float(filled["b1_delay_min"].mean()) if len(filled) else np.nan,
        })
    return pd.DataFrame(rows)


def incremental_table(summary: pd.DataFrame) -> pd.DataFrame:
    base = summary.loc[summary["MODEL"] == "Phase45_B1_Control"].iloc[0]
    rows = []
    for _, row in summary.iterrows():
        if row["MODEL"] == "Phase45_B1_Control":
            continue
        rows.append({
            "MODEL": row["MODEL"],
            "dAvgR": row["AvgR"] - base["AvgR"],
            "dPF": row["PF"] - base["PF"],
            "dTotalR": row["TotalR"] - base["TotalR"],
            "dMaxDD": row["MaxDD"] - base["MaxDD"],
            "dMAE": base["MAE"] - row["MAE"],
            "dMFE": row["MFE"] - base["MFE"],
            "dWrongDir": base["WrongDir"] - row["WrongDir"],
            "dDelay": row["EntryDelay"] - base["EntryDelay"],
            "Retention": row["RETENTION"],
        })
    return pd.DataFrame(rows)


def bucket_diagnostics(features: pd.DataFrame, col: str, bins, labels) -> pd.DataFrame:
    df = features.copy()
    df["bucket"] = pd.cut(df[col], bins=bins, labels=labels)
    rows = []
    for bucket, sub in df.groupby("bucket", observed=True):
        p = _perf(sub, "final_r")
        rows.append({"feature": col, "bucket": str(bucket), "N": p["N"], "AvgR": p["AvgR"], "MedianR": float(sub["final_r"].median()), "PF": p["PF"], "MAE": float(sub["mae"].mean()), "MFE": float(sub["mfe"].mean()), "wrong_direction_rate": float(sub["wrong_direction"].mean())})
    return pd.DataFrame(rows)


def matched_comparison(control: pd.DataFrame, variant: pd.DataFrame, vname: str) -> pd.DataFrame:
    m = control.merge(variant[["signal_id", "V_pass", "V_net_R", "V_MAE_R", "V_MFE_R", "V_wrong_direction", "V_delay_min"]], on="signal_id", how="inner", suffixes=("", "_v"))
    both = m.loc[m["V_pass"]]
    rows = []
    if not both.empty:
        rows.append({"model": vname, "segment": "matched", "N": len(both), "dAvgR": float((both["V_net_R"] - both["final_r"]).mean()), "dMAE": float((both["mae"] - both["V_MAE_R"]).mean()), "dMFE": float((both["V_MFE_R"] - both["mfe"]).mean()), "dWrongDir": float(both["wrong_direction"].mean() - both["V_wrong_direction"].mean())})
    rej = m.loc[~m["V_pass"]]
    if not rej.empty:
        p = _perf(rej, "final_r")
        rows.append({"model": vname, "segment": "rejected", "N": p["N"], "dAvgR": p["AvgR"], "dMAE": float(rej["mae"].mean()), "dMFE": float(rej["mfe"].mean()), "dWrongDir": float(rej["wrong_direction"].mean())})
    return pd.DataFrame(rows)


def stratified(wf: pd.DataFrame, control: pd.DataFrame, segment_col: str, segment_vals) -> pd.DataFrame:
    rows = []
    for v in wf["variant"].unique():
        vsub = wf.loc[wf["variant"] == v]
        for seg in segment_vals:
            cseg = control.loc[control[segment_col] == seg] if segment_col in control.columns else control.loc[control["signal_type"] == seg]
            vseg = vsub.loc[(vsub[segment_col] == seg if segment_col in vsub.columns else vsub["signal_type"] == seg) & vsub["V_pass"]]
            pb, pv = _perf(cseg, "final_r"), _perf(vseg, "V_net_R")
            rows.append({"model": v, "segment": seg, "B0_N": pb["N"], "V_N": pv["N"], "B0_AvgR": pb["AvgR"], "V_AvgR": pv["AvgR"]})
    return pd.DataFrame(rows)


def yearly(wf: pd.DataFrame, control: pd.DataFrame) -> pd.DataFrame:
    c = control.copy()
    c["year"] = pd.to_datetime(c["marker_bar_timestamp"]).dt.year
    rows = []
    for year in (2024, 2025, 2026):
        for v in wf["variant"].unique():
            vsub = wf.loc[wf["variant"] == v]
            vsub = vsub.copy()
            vsub["year"] = pd.to_datetime(vsub["marker_bar_timestamp"]).dt.year
            cb = c.loc[c["year"] == year]
            vf = vsub.loc[(vsub["year"] == year) & vsub["V_pass"]]
            pb, pv = _perf(cb, "final_r"), _perf(vf, "V_net_R")
            rows.append({"year": year, "model": v, "B0_N": pb["N"], "V_N": pv["N"], "B0_AvgR": pb["AvgR"], "V_AvgR": pv["AvgR"]})
    return pd.DataFrame(rows)


def wrong_direction_diagnostics(features: pd.DataFrame) -> pd.DataFrame:
    ok = features.loc[features["wrong_direction"] == 0]
    bad = features.loc[features["wrong_direction"] == 1]
    rows = []
    for col in ("break_strength_atr", "range_atr", "body_atr", "body_range_ratio", "close_quality", "opposing_wick_ratio", "b1_delay_min", "structure_age_bars"):
        if col not in features.columns:
            continue
        rows.append({"feature": col, "success_mean": float(ok[col].mean()), "wrong_dir_mean": float(bad[col].mean()), "success_N": len(ok), "wrong_N": len(bad)})
    return pd.DataFrame(rows)


def robustness(variant_wf: pd.DataFrame, vname: str) -> pd.DataFrame:
    sub = variant_wf.loc[(variant_wf["variant"] == vname) & variant_wf["V_pass"]]
    if sub.empty:
        return pd.DataFrame()
    rows = []
    for mult in (1.0, 1.5, 2.0):
        if mult == 1.0:
            p = _perf(sub, "V_net_R")
        else:
            t = sub.copy()
            t["entry_price"] = t.get("entry_price", t.get("B_entry_price", np.nan))
            t["stop_price"] = t["stop"]
            t["realized_R"] = t["V_net_R"]
            t["net_R"] = apply_costs(t.assign(result_R=t["realized_R"]), multiplier=mult, col="result_R")
            p = _perf(t, "net_R")
        p["cost_multiplier"] = mult
        p["model"] = vname
        rows.append(p)
    r = sub.sort_values("V_net_R", ascending=False)
    n1 = max(1, int(np.ceil(len(r) * 0.01)))
    rows.append({**_perf(r.iloc[n1:], "V_net_R"), "cost_multiplier": "ex_top1pct", "model": vname})
    return pd.DataFrame(rows)
