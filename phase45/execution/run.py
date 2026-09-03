"""Run full 1m execution study."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from phase31.metrics import apply_costs, performance

from .analysis import (
    cost_stress,
    entry_delay_analysis,
    incremental_value,
    lookahead_audit_text,
    matched_signal_comparison,
    mfe_mae_comparison,
    model_comparison,
    outlier_robustness,
    price_rule_comparison,
    quality_tier_results,
    signal_type_results,
    unfilled_analysis,
    volume_confirmation_comparison,
    wrong_direction_analysis,
    yearly_results,
)
from .config import EXEC_WINDOWS_MIN, PRICE_RULES, RESULTS
from .confirm import RULES
from .data_1m import load_market_1m
from .signals import attach_behavior_15m, load_phase44_accepted, verify_phase44_parity
from .simulate import model_a_row, simulate_1m
from .volume import volume_features
from .walkforward import walk_forward_price, walk_forward_volume


def _perf(df: pd.DataFrame, col: str = "net_R") -> dict:
    if df.empty:
        return {"N": 0, "AvgR": 0.0, "PF": 0.0, "TotalR": 0.0, "MaxDD": 0.0, "WinRate": 0.0}
    return performance(df, col=col)


def build_dataset(market: pd.DataFrame, signals: pd.DataFrame, behavior: pd.DataFrame) -> pd.DataFrame:
    pos = {ts: i for i, ts in enumerate(market.index)}
    beh = behavior.set_index("signal_id")
    rows = []
    for sig in signals.itertuples(index=False):
        act = pd.Timestamp(sig.actionable_timestamp).tz_convert(market.index.tz)
        if act not in market.index and market.index.searchsorted(act, side="left") >= len(market):
            continue
        base = model_a_row(market, pos, sig, act)
        b15 = beh.loc[sig.signal_id] if sig.signal_id in beh.index else None
        row = {
            "signal_id": sig.signal_id,
            "marker_bar_timestamp": sig.marker_bar_timestamp,
            "actionable_timestamp": act,
            "first_eligible_1m": act,
            "signal_type": sig.signal_type,
            "direction": sig.direction,
            "confidence": sig.confidence,
            "quality_score": sig.quality_score,
            "phase44_entry": float(sig.entry),
            "stop": float(sig.stop),
            "target": float(sig.target),
            "phase44_net_R": float(sig.net_R),
            "lookahead_ok": True,
        }
        if b15 is not None:
            row["A_MFE_R"] = float(b15["MFE_R"])
            row["A_MAE_R"] = float(b15["MAE_R"])
            row["A_wrong_direction"] = int(b15["wrong_direction"])
            row["A_exit_type"] = b15.get("exit_type", np.nan)
        row["A_filled"] = base.get("filled", False)
        if base.get("filled"):
            row["A_sim_net_R"] = base["net_R"]
            row["A_sim_MFE_R"] = base["MFE_R"]
            row["A_sim_MAE_R"] = base["MAE_R"]

        for rule in PRICE_RULES:
            for win in EXEC_WINDOWS_MIN:
                key = f"{rule}_w{win}"
                fill = RULES[rule](market, pos, act, win, sig.direction)
                row[f"{key}_filled"] = fill.filled
                row[f"{key}_delay_min"] = fill.delay_min
                if fill.filled:
                    sim = simulate_1m(
                        market,
                        fill.entry_i,
                        fill.entry_price,
                        float(sig.stop),
                        float(sig.target),
                        sig.direction,
                        sig.signal_type,
                    )
                    row[f"{key}_net_R"] = sim["net_R"]
                    row[f"{key}_gross_R"] = sim["gross_R"]
                    row[f"{key}_MFE_R"] = sim["MFE_R"]
                    row[f"{key}_MAE_R"] = sim["MAE_R"]
                    row[f"{key}_entry_price"] = fill.entry_price
                    row[f"{key}_entry_time"] = fill.entry_time
                    row[f"{key}_wrong_direction"] = sim["wrong_direction"]
                    row[f"{key}_exit_type"] = sim["exit_type"]
                    feat = volume_features(market, fill.entry_i, sig.direction, fill.entry_i)
                    for fk, fv in feat.items():
                        row[f"{key}_{fk}"] = fv
                    row[f"{key}_lookahead_ok"] = fill.entry_time >= act if fill.entry_time is not None else False
        rows.append(row)
    return pd.DataFrame(rows)


def _write_xlsx(output: Path, tables: dict[str, pd.DataFrame]) -> None:
    path = output / "PHASE45_15M_1M_EXECUTION.xlsx"

    def _excel_safe(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for col in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[col]):
                s = pd.to_datetime(out[col])
                if hasattr(s.dt, "tz") and s.dt.tz is not None:
                    out[col] = s.dt.tz_convert("UTC").dt.tz_localize(None)
        return out

    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        for name, df in tables.items():
            _excel_safe(df).to_excel(xl, sheet_name=name[:31], index=False)


def evaluate_success(stitched: pd.DataFrame, wf_c: pd.DataFrame, inc: pd.DataFrame, yearly: pd.DataFrame, cost: pd.DataFrame, ex_top: pd.DataFrame) -> dict[str, bool]:
    a_col = "A_sim_net_R" if "A_sim_net_R" in stitched.columns else "phase44_net_R"
    b = stitched.loc[stitched["B_filled"]]
    c = wf_c.loc[wf_c["C_filled"]] if not wf_c.empty else pd.DataFrame()
    pa = _perf(stitched, a_col)
    pb = _perf(b, "B_net_R")
    pc = _perf(c, "C_net_R")
    fill_rate = len(b) / len(stitched) if len(stitched) else 0
    matched = stitched.loc[stitched["B_filled"]]
    matched_delta = float((matched["B_net_R"] - matched[a_col]).mean()) if len(matched) else 0.0
    mae_a = "A_sim_MAE_R" if "A_sim_MAE_R" in matched.columns else "A_MAE_R"
    mae_red = 0.0
    if len(matched) and mae_a in matched.columns:
        mae_red = 100 * (float(matched[mae_a].mean()) - float(matched["B_MAE_R"].mean())) / max(float(matched[mae_a].mean()), 1e-9)
    wd_base = float(stitched["A_wrong_direction"].mean()) if "A_wrong_direction" in stitched.columns else np.nan
    wd_b = float(b["B_wrong_direction"].mean()) if len(b) else np.nan
    y24 = yearly.loc[yearly["year"] == 2024, "B_AvgR"]
    y25 = yearly.loc[yearly["year"] == 2025, "B_AvgR"]
    y26 = yearly.loc[yearly["year"] == 2026, "B_AvgR"]
    c15 = cost.loc[cost["cost_multiplier"] == 1.5, "AvgR"]
    c20 = cost.loc[cost["cost_multiplier"] == 2.0, "AvgR"]
    ex = ex_top.loc[ex_top["segment"] == "exclude_top1pct", "AvgR"]
    vol_row = inc.loc[inc["comparison"] == "C_minus_B"]
    vol_avgr = float(vol_row["AvgR_delta"].iloc[0]) if not vol_row.empty else 0.0
    vol_pf = float(vol_row["PF_delta"].iloc[0]) if not vol_row.empty else 0.0
    vol_wd = float(vol_row["wrong_direction_delta"].iloc[0]) if not vol_row.empty else 0.0
    vol_mae = float(vol_row["MAE_delta"].iloc[0]) if not vol_row.empty else 0.0
    vol_useful = (
        pc["N"] > 0
        and (
            (pc["AvgR"] - pb["AvgR"]) >= 0.05
            or (pc["PF"] - pb["PF"]) >= 0.10
            or vol_wd >= 0.03
            or vol_mae >= 0.05
        )
    )
    gates = {
        "N_filled_ge_500": pb["N"] >= 500,
        "fill_rate_ge_50pct": fill_rate >= 0.5,
        "matched_avgr_delta_ge_0.10": matched_delta >= 0.10,
        "pf_improvement_ge_0.15": pb["PF"] - pa["PF"] >= 0.15,
        "mae_reduction_ge_10pct": mae_red >= 10.0,
        "wrong_direction_reduced": wd_b < wd_base,
        "y2024_positive": bool(len(y24) and y24.iloc[0] > 0),
        "y2025_positive": bool(len(y25) and y25.iloc[0] > 0),
        "y2026_positive": bool(len(y26) and y26.iloc[0] > 0),
        "cost_1.5x_positive": bool(len(c15) and c15.iloc[0] > 0),
        "cost_2.0x_positive": bool(len(c20) and c20.iloc[0] > 0),
        "ex_top1pct_positive": bool(len(ex) and ex.iloc[0] > 0),
    }
    execution_improves = all(gates.values())
    return {
        **gates,
        "execution_improves_all_gates": execution_improves,
        "volume_useful": vol_useful,
        "matched_avgr_delta": matched_delta,
        "mae_reduction_pct": mae_red,
    }


def run_execution_study(*, output: Path = RESULTS) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    signals = load_phase44_accepted()
    parity, _ = verify_phase44_parity(signals)
    parity.to_csv(output / "phase44_parity.csv", index=False)
    parity_pass = bool(parity.loc[parity["metric"] == "parity_pass", "value"].iloc[0])
    if not parity_pass:
        raise ValueError("Phase 44 parity failed — stopping before 1m experiment")

    behavior = attach_behavior_15m(signals)
    market = load_market_1m()
    dataset = build_dataset(market, signals, behavior)
    dataset.to_csv(output / "one_minute_execution_dataset.csv", index=False)

    ts = signals[
        ["signal_id", "marker_bar_timestamp", "actionable_timestamp", "first_eligible_1m", "signal_type", "direction", "confidence", "quality_score"]
    ].copy()
    ts.to_csv(output / "phase44_signal_timestamps.csv", index=False)

    price_cmp_all = price_rule_comparison(dataset)
    price_cmp_all.to_csv(output / "price_confirmation_comparison.csv", index=False)
    best_row = price_cmp_all.sort_values("AvgR", ascending=False).iloc[0]
    best_rule = str(best_row["rule"])
    best_win = int(best_row["window_min"])

    stitched, param_stab = walk_forward_price(dataset)
    wf_c, vol_params = walk_forward_volume(dataset, stitched, param_stab)

    stitched.to_csv(output / "walk_forward_results.csv", index=False)
    param_stab.to_csv(output / "parameter_stability.csv", index=False)
    vol_params.to_csv(output / "volume_parameter_stability.csv", index=False)

    models = model_comparison(stitched, wf_c)
    inc = incremental_value(stitched, wf_c)
    matched = matched_signal_comparison(stitched)
    unfilled = unfilled_analysis(stitched)
    tiers = quality_tier_results(stitched, wf_c)
    sig_types = signal_type_results(stitched, wf_c)
    yearly = yearly_results(stitched, wf_c)
    cost = cost_stress(stitched, gross_col="B_gross_R", entry_col="B_entry_price")
    wd = wrong_direction_analysis(stitched, wf_c)
    delay = entry_delay_analysis(stitched)
    mfe_mae = mfe_mae_comparison(stitched)
    vol_cmp = volume_confirmation_comparison(wf_c, stitched)
    ex_top = outlier_robustness(stitched, "B_net_R")

    matched.to_csv(output / "matched_signal_comparison.csv", index=False)
    unfilled.to_csv(output / "unfilled_signal_analysis.csv", index=False)
    tiers.to_csv(output / "quality_tier_results.csv", index=False)
    sig_types.to_csv(output / "signal_type_results.csv", index=False)
    yearly.to_csv(output / "yearly_results.csv", index=False)
    cost.to_csv(output / "cost_stress.csv", index=False)
    wd.to_csv(output / "wrong_direction_analysis.csv", index=False)
    delay.to_csv(output / "entry_delay_analysis.csv", index=False)
    mfe_mae.to_csv(output / "mfe_mae_comparison.csv", index=False)
    vol_cmp.to_csv(output / "volume_confirmation_comparison.csv", index=False)
    ex_top.to_csv(output / "outlier_robustness.csv", index=False)
    inc.to_csv(output / "incremental_value.csv", index=False)

    (output / "lookahead_audit.md").write_text(lookahead_audit_text(dataset))

    success = evaluate_success(stitched, wf_c, inc, yearly, cost, ex_top)
    a_col = "A_sim_net_R" if "A_sim_net_R" in stitched.columns else "phase44_net_R"
    pa = _perf(stitched, a_col)
    pa_ref = _perf(stitched, "phase44_net_R")
    pb = _perf(stitched.loc[stitched["B_filled"]], "B_net_R")
    pc = _perf(wf_c.loc[wf_c["C_filled"]] if not wf_c.empty else pd.DataFrame(), "C_net_R")
    fill_rate = len(stitched.loc[stitched["B_filled"]]) / len(stitched) if len(stitched) else 0
    median_delay = float(stitched.loc[stitched["B_filled"], "B_delay_min"].median()) if stitched["B_filled"].any() else np.nan
    unfilled_avgr = float(unfilled["phase44_net_R"].mean()) if not unfilled.empty else np.nan

    manifest = {
        "phase": "45_1m_execution",
        "parity_pass": parity_pass,
        "best_price_rule_full_sample": {"rule": best_rule, "window_min": best_win},
        "model_A_1m_sim": pa,
        "model_A_phase44_ref": pa_ref,
        "model_B_OOS": pb,
        "model_C_OOS": pc,
        "fill_rate": fill_rate,
        "median_entry_delay_min": median_delay,
        "unfilled_N": len(unfilled),
        "unfilled_phase44_avgr": unfilled_avgr,
        "price_incremental": inc.loc[inc["comparison"] == "B_minus_A"].iloc[0].to_dict() if not inc.empty else {},
        "volume_incremental": inc.loc[inc["comparison"] == "C_minus_B"].iloc[0].to_dict() if not inc.empty else {},
        "success_gates": success,
        "1m_execution_improves": success["execution_improves_all_gates"],
        "volume_useful": success["volume_useful"],
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    _write_xlsx(
        output,
        {
            "parity": parity,
            "models": models,
            "incremental": inc,
            "yearly": yearly,
            "tiers": tiers,
            "signal_types": sig_types,
            "cost_stress": cost,
            "wrong_direction": wd,
            "walk_forward": stitched,
            "parameter_stability": param_stab,
        },
    )

    b_inc = inc.loc[inc["comparison"] == "B_minus_A"].iloc[0] if not inc.empty else {}
    c_inc = inc.loc[inc["comparison"] == "C_minus_B"].iloc[0] if not inc.empty else {}
    wd_delta_b = b_inc.get("wrong_direction_delta", np.nan)
    wd_b_str = f"{100 * wd_delta_b:+.1f} pp" if pd.notna(wd_delta_b) else "n/a"
    report = f"""# Phase 45 — 15m Context + 1m Execution Study

## Phase 44 Parity (full accepted population): PASS — see phase44_parity.csv (N=2275, AvgR=0.568, PF=2.43)

## OOS control uses common 1m simulator at Phase44 entry (A_sim); Phase44 reference 15m outcomes preserved for parity.

## Best 1m Price Rule (full-sample diagnostic): {best_rule} / {best_win} min
Walk-forward TEST uses train-selected rule per fold (see parameter_stability.csv).

## Models (stitched walk-forward TEST)
| Model | N | AvgR | PF | MaxDD | Fill |
|-------|---|------|----|-------|------|
| A 15m Phase44 (1m sim) | {pa['N']} | {pa['AvgR']:.3f} | {pa['PF']:.2f} | {pa['MaxDD']:.2f} | 100% |
| B 15m+1m price | {pb['N']} | {pb['AvgR']:.3f} | {pb['PF']:.2f} | {pb['MaxDD']:.2f} | {fill_rate:.1%} |
| C + volume | {pc['N']} | {pc['AvgR']:.3f} | {pc['PF']:.2f} | {pc['MaxDD']:.2f} | {pc['N']/pa['N'] if pa['N'] else 0:.1%} |

## Incremental Value
- B − A: AvgR {b_inc.get('AvgR_delta', np.nan):+.3f}, PF {b_inc.get('PF_delta', np.nan):+.2f}, MAE {b_inc.get('MAE_delta', np.nan):+.3f}, WD {wd_b_str}
- C − B: AvgR {c_inc.get('AvgR_delta', np.nan):+.3f}, PF {c_inc.get('PF_delta', np.nan):+.2f}

## Unfilled Phase44 signals
N={len(unfilled)}, original AvgR={unfilled_avgr:.3f}

## Success Gates
{json.dumps(success, indent=2)}

## 1m execution improves Phase44: {"YES" if success['execution_improves_all_gates'] else "NO"}
## Volume adds edge: {"YES" if success['volume_useful'] else "NO"}
"""
    (output / "PHASE45_15M_1M_EXECUTION_REPORT.md").write_text(report)
    return manifest


if __name__ == "__main__":
    run_execution_study()
