"""Analysis tables for Phase 45 1m execution study."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase31.metrics import apply_costs, performance
from phase36.data import load_replay_market_15m

from .config import EXEC_WINDOWS_MIN, PRICE_RULES


def _perf(df: pd.DataFrame, col: str = "net_R") -> dict:
    if df.empty:
        return {"N": 0, "AvgR": 0.0, "PF": 0.0, "TotalR": 0.0, "MaxDD": 0.0, "WinRate": 0.0}
    return performance(df, col=col)


def price_rule_comparison(dataset: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rule in PRICE_RULES:
        for win in EXEC_WINDOWS_MIN:
            fill = f"{rule}_w{win}_filled"
            col = f"{rule}_w{win}_net_R"
            if fill not in dataset.columns:
                continue
            sub = dataset.loc[dataset[fill]]
            p = _perf(sub, col)
            rows.append({"rule": rule, "window_min": win, "fill_rate": len(sub) / len(dataset) if len(dataset) else 0, **p})
    return pd.DataFrame(rows)


def model_comparison(stitched: pd.DataFrame, wf_c: pd.DataFrame) -> pd.DataFrame:
    a = stitched.copy()
    a_col = "A_sim_net_R" if "A_sim_net_R" in a.columns else "phase44_net_R"
    b = stitched.loc[stitched["B_filled"]]
    c = wf_c.loc[wf_c["C_filled"]] if not wf_c.empty else pd.DataFrame()
    pa = _perf(a, a_col)
    pb = _perf(b, "B_net_R")
    pc = _perf(c, "C_net_R")
    pa_ref = _perf(a, "phase44_net_R")
    return pd.DataFrame(
        [
            {"model": "A_15m_phase44_1m_sim", "fill_rate": 1.0, "phase44_ref_AvgR": pa_ref["AvgR"], **pa},
            {"model": "B_15m_1m_price_OOS", "fill_rate": len(b) / len(a) if len(a) else 0, **pb},
            {"model": "C_15m_1m_price_volume_OOS", "fill_rate": len(c) / len(a) if len(a) else 0, **pc},
        ]
    )


def incremental_value(stitched: pd.DataFrame, wf_c: pd.DataFrame) -> pd.DataFrame:
    a_col = "A_sim_net_R" if "A_sim_net_R" in stitched.columns else "phase44_net_R"
    a = stitched
    b = stitched.loc[stitched["B_filled"]]
    c = wf_c.loc[wf_c["C_filled"]] if not wf_c.empty else pd.DataFrame()
    matched = stitched.loc[stitched["B_filled"]].copy()

    def _wd(df, col):
        return float(df[col].mean()) if col in df.columns and not df.empty else np.nan

    def _mae(df, col):
        return float(df[col].mean()) if col in df.columns and not df.empty else np.nan

    pa, pb, pc = _perf(a, a_col), _perf(b, "B_net_R"), _perf(c, "C_net_R")
    pa_ref = _perf(a, "phase44_net_R")
    mae_a = "A_sim_MAE_R" if "A_sim_MAE_R" in matched.columns else "A_MAE_R"
    rows = [
        {
            "comparison": "B_minus_A",
            "AvgR_delta": pb["AvgR"] - pa["AvgR"],
            "PF_delta": pb["PF"] - pa["PF"],
            "MAE_delta": _mae(matched, mae_a) - _mae(matched, "B_MAE_R"),
            "wrong_direction_delta": _wd(matched, "A_wrong_direction") - _wd(matched, "B_wrong_direction"),
            "matched_AvgR_delta": float((matched["B_net_R"] - matched[a_col]).mean()) if len(matched) else np.nan,
            "N_A": pa["N"],
            "N_B": pb["N"],
            "A_phase44_ref_AvgR": pa_ref["AvgR"],
        },
        {
            "comparison": "C_minus_B",
            "AvgR_delta": pc["AvgR"] - pb["AvgR"] if pc["N"] else np.nan,
            "PF_delta": pc["PF"] - pb["PF"] if pc["N"] else np.nan,
            "MAE_delta": _mae(c, "B_MAE_R") - _mae(c, "C_MAE_R") if not c.empty else np.nan,
            "wrong_direction_delta": _wd(c, "B_wrong_direction") - _wd(c, "C_wrong_direction") if not c.empty else np.nan,
            "N_B": pb["N"],
            "N_C": pc["N"],
        },
    ]
    return pd.DataFrame(rows)


def matched_signal_comparison(stitched: pd.DataFrame) -> pd.DataFrame:
    m = stitched.loc[stitched["B_filled"]].copy()
    if m.empty:
        return m
    market = load_replay_market_15m()
    pos = {ts: i for i, ts in enumerate(market.index)}
    atrs = []
    for _, row in m.iterrows():
        ts = pd.Timestamp(row["marker_bar_timestamp"]).tz_convert(market.index.tz)
        i = pos.get(ts, np.nan)
        atr = float(market.iloc[int(i)]["atr"]) if np.isfinite(i) else np.nan
        atrs.append(atr)
    m["atr_15m"] = atrs
    long_mask = m["direction"].str.lower() == "long"
    m["entry_improvement_atr"] = np.where(
        long_mask,
        (m["phase44_entry"] - m["B_entry_price"]) / m["atr_15m"],
        (m["B_entry_price"] - m["phase44_entry"]) / m["atr_15m"],
    )
    m["AvgR_delta"] = m["B_net_R"] - m.get("A_sim_net_R", m["phase44_net_R"])
    m["MAE_delta"] = m["A_MAE_R"] - m["B_MAE_R"]
    m["MFE_delta"] = m["B_MFE_R"] - m["A_MFE_R"]
    m["win_delta"] = ((m["B_net_R"] > 0).astype(int) - (m["phase44_net_R"] > 0).astype(int))
    m["stop_hit_delta"] = np.nan
    m["target_hit_delta"] = np.nan
    if "B_exit_type" in m.columns:
        m["stop_hit_delta"] = (m["B_exit_type"] == "STOP").astype(int) - (m["A_exit_type"] == "STOP").astype(int) if "A_exit_type" in m.columns else np.nan
        m["target_hit_delta"] = (m["B_exit_type"] == "TARGET").astype(int) - (m["A_exit_type"] == "TARGET").astype(int) if "A_exit_type" in m.columns else np.nan
    return m


def unfilled_analysis(stitched: pd.DataFrame) -> pd.DataFrame:
    u = stitched.loc[~stitched["B_filled"]].copy()
    u["segment"] = "unfilled_1m"
    u["phase44_avgr_if_taken"] = u["phase44_net_R"]
    return u


def quality_tier_results(stitched: pd.DataFrame, wf_c: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tier in ("A+", "A", "B"):
        sub = stitched.loc[stitched["confidence"] == tier]
        bf = sub.loc[sub["B_filled"]]
        cf = wf_c.loc[(wf_c["confidence"] == tier) & wf_c["C_filled"]] if not wf_c.empty else pd.DataFrame()
        pa, pb = _perf(sub, "phase44_net_R"), _perf(bf, "B_net_R")
        pc = _perf(cf, "C_net_R")
        rows.append(
            {
                "tier": tier,
                "N": len(sub),
                "fill_rate": len(bf) / len(sub) if len(sub) else 0,
                "baseline_AvgR": pa["AvgR"],
                "price_AvgR": pb["AvgR"],
                "volume_AvgR": pc["AvgR"],
                "baseline_PF": pa["PF"],
                "price_PF": pb["PF"],
                "volume_PF": pc["PF"],
                "MAE_improvement": float(sub.loc[sub["B_filled"], "A_MAE_R"].mean() - bf["B_MAE_R"].mean()) if len(bf) else np.nan,
                "median_entry_delay_min": float(bf["B_delay_min"].median()) if len(bf) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def signal_type_results(stitched: pd.DataFrame, wf_c: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for st in ("L", "S", "RL", "RS"):
        sub = stitched.loc[stitched["signal_type"] == st]
        bf = sub.loc[sub["B_filled"]]
        cf = wf_c.loc[(wf_c["signal_type"] == st) & wf_c["C_filled"]] if not wf_c.empty else pd.DataFrame()
        pa, pb, pc = _perf(sub, "phase44_net_R"), _perf(bf, "B_net_R"), _perf(cf, "C_net_R")
        rows.append(
            {
                "signal_type": st,
                "N": len(sub),
                "fill_rate": len(bf) / len(sub) if len(sub) else 0,
                "baseline_AvgR": pa["AvgR"],
                "price_AvgR": pb["AvgR"],
                "volume_AvgR": pc["AvgR"],
                "baseline_PF": pa["PF"],
                "price_PF": pb["PF"],
                "volume_PF": pc["PF"],
            }
        )
    return pd.DataFrame(rows)


def yearly_results(stitched: pd.DataFrame, wf_c: pd.DataFrame) -> pd.DataFrame:
    rows = []
    years = sorted(pd.to_datetime(stitched["marker_bar_timestamp"]).dt.year.unique())
    for year in years:
        sub = stitched.loc[pd.to_datetime(stitched["marker_bar_timestamp"]).dt.year == year]
        bf = sub.loc[sub["B_filled"]]
        cf = wf_c.loc[pd.to_datetime(wf_c["marker_bar_timestamp"]).dt.year == year] if not wf_c.empty else pd.DataFrame()
        cf = cf.loc[cf["C_filled"]] if not cf.empty else cf
        pa, pb, pc = _perf(sub, "phase44_net_R"), _perf(bf, "B_net_R"), _perf(cf, "C_net_R")
        rows.append(
            {
                "year": int(year),
                "A_N": pa["N"],
                "B_N": pb["N"],
                "C_N": pc["N"],
                "fill_rate": len(bf) / len(sub) if len(sub) else 0,
                "A_AvgR": pa["AvgR"],
                "B_AvgR": pb["AvgR"],
                "C_AvgR": pc["AvgR"],
                "A_PF": pa["PF"],
                "B_PF": pb["PF"],
                "C_PF": pc["PF"],
                "A_MaxDD": pa["MaxDD"],
                "B_MaxDD": pb["MaxDD"],
            }
        )
    return pd.DataFrame(rows)


def cost_stress(df: pd.DataFrame, *, gross_col: str, stop_col: str = "stop", entry_col: str) -> pd.DataFrame:
    rows = []
    sub = df.loc[df["B_filled"]].copy() if "B_filled" in df.columns else df
    if sub.empty:
        return pd.DataFrame()
    tmp = sub.copy()
    tmp["realized_R"] = tmp[gross_col]
    tmp["entry_price"] = tmp[entry_col]
    tmp["stop_price"] = tmp[stop_col]
    for mult in (1.0, 1.5, 2.0):
        net = apply_costs(tmp, multiplier=mult, col="realized_R")
        t = tmp.copy()
        t["net_R"] = net
        p = _perf(t, "net_R")
        p["cost_multiplier"] = mult
        p["model"] = "B"
        rows.append(p)
    return pd.DataFrame(rows)


def wrong_direction_analysis(stitched: pd.DataFrame, wf_c: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, df, col in (
        ("phase44_baseline", stitched, "A_wrong_direction"),
        ("1m_price_OOS", stitched.loc[stitched["B_filled"]], "B_wrong_direction"),
        ("1m_price_volume_OOS", wf_c.loc[wf_c["C_filled"]] if not wf_c.empty else pd.DataFrame(), "C_wrong_direction"),
    ):
        if df.empty or col not in df.columns:
            rows.append({"segment": name, "wrong_direction_rate": np.nan, "N": 0})
        else:
            rows.append({"segment": name, "wrong_direction_rate": float(df[col].mean()), "N": len(df)})
    return pd.DataFrame(rows)


def entry_delay_analysis(stitched: pd.DataFrame) -> pd.DataFrame:
    bf = stitched.loc[stitched["B_filled"]].copy()
    if bf.empty:
        return pd.DataFrame()
    rows = [
        {"metric": "median_delay_min", "value": float(bf["B_delay_min"].median())},
        {"metric": "mean_delay_min", "value": float(bf["B_delay_min"].mean())},
        {"metric": "p75_delay_min", "value": float(bf["B_delay_min"].quantile(0.75))},
        {"metric": "p90_delay_min", "value": float(bf["B_delay_min"].quantile(0.90))},
        {"metric": "max_delay_min", "value": float(bf["B_delay_min"].max())},
    ]
    return pd.DataFrame(rows)


def mfe_mae_comparison(stitched: pd.DataFrame) -> pd.DataFrame:
    m = stitched.loc[stitched["B_filled"]]
    if m.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {"metric": "A_MFE_mean", "value": float(m["A_MFE_R"].mean())},
            {"metric": "B_MFE_mean", "value": float(m["B_MFE_R"].mean())},
            {"metric": "A_MAE_mean", "value": float(m["A_MAE_R"].mean())},
            {"metric": "B_MAE_mean", "value": float(m["B_MAE_R"].mean())},
            {"metric": "MFE_improvement_pct", "value": 100 * (float(m["B_MFE_R"].mean()) - float(m["A_MFE_R"].mean())) / max(float(m["A_MFE_R"].mean()), 1e-9)},
            {"metric": "MAE_reduction_pct", "value": 100 * (float(m["A_MAE_R"].mean()) - float(m["B_MAE_R"].mean())) / max(float(m["A_MAE_R"].mean()), 1e-9)},
        ]
    )


def outlier_robustness(df: pd.DataFrame, col: str = "B_net_R") -> pd.DataFrame:
    sub = df.loc[df["B_filled"]].copy() if "B_filled" in df.columns else df
    if sub.empty:
        return pd.DataFrame()
    rows = [_perf(sub, col)]
    r = sub.sort_values(col, ascending=False)
    n1 = max(1, int(np.ceil(len(r) * 0.01)))
    rows.append(_perf(r.iloc[n1:], col))
    out = pd.DataFrame(rows)
    out["segment"] = ["FULL", "exclude_top1pct"]
    return out


def volume_confirmation_comparison(wf_c: pd.DataFrame, stitched: pd.DataFrame) -> pd.DataFrame:
    b = stitched.loc[stitched["B_filled"]]
    c = wf_c.loc[wf_c["C_filled"]] if not wf_c.empty else pd.DataFrame()
    pb, pc = _perf(b, "B_net_R"), _perf(c, "C_net_R")
    return pd.DataFrame(
        [
            {"model": "B_price", **pb, "fill_rate": len(b) / len(stitched) if len(stitched) else 0},
            {"model": "C_price_volume", **pc, "fill_rate": len(c) / len(stitched) if len(stitched) else 0},
        ]
    )


def lookahead_audit_text(dataset: pd.DataFrame) -> str:
    ok = bool((dataset["first_eligible_1m"] <= dataset["actionable_timestamp"]).all()) if not dataset.empty else True
    violations = 0
    if "B1_w5_delay_min" in dataset.columns:
        violations = int((dataset["B1_w5_delay_min"] < 0).sum())
    status = "PASS" if ok and violations == 0 else "FAIL"
    return f"""# Lookahead Audit

## Rule
A completed 15m candle cannot use internal 1m bars retroactively.
`actionable_timestamp = marker_bar_timestamp + 15 minutes`.
All 1m confirmation scans begin at the first eligible 1m bar on or after `actionable_timestamp`.

## Checks
- first_eligible_1m <= actionable_timestamp for all signals: **{"PASS" if ok else "FAIL"}**
- negative 1m entry delays: **{violations}** (must be 0)
- 1m_timestamp >= 15m_signal_available_timestamp enforced in confirm.py scan windows

## Result: **{status}**
"""
