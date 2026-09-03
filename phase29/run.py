#!/usr/bin/env python3
"""Phase 29 — CRT V2 @ 15m focused trade architecture optimization."""

from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase17.analysis_core import max_drawdown

from phase29.config import (
    BASELINE_HOLD_MINUTES,
    BASELINE_STOP_ATR,
    BASELINE_TARGET_R,
    COMMON_END,
    COMMON_START,
    ENTRY_MODELS,
    ERAS,
    HOLD_MINUTES,
    MANAGEMENT_MODELS,
    NQ_DOLLARS_PER_POINT,
    PARITY,
    RESULTS,
    ROUND_TURN_COST_USD,
    STOP_ATRS,
    TARGET_RS,
    WALK_FORWARD_FOLDS,
    hold_bars,
)
from phase29.data import extract_signals, load_market_15m
from phase29.simulator import SimConfig, first_passage_probs, simulate_trade


def apply_costs(df: pd.DataFrame, *, multiplier: float = 1.0, gross_col: str = "result_R") -> pd.Series:
    risk = (df["entry_price"].astype(float) - df["stop_price"].astype(float)).abs()
    cost_r = (ROUND_TURN_COST_USD * multiplier) / (risk * NQ_DOLLARS_PER_POINT)
    return df[gross_col].astype(float) - cost_r


def enrich_net(df: pd.DataFrame, *, multiplier: float = 1.0) -> pd.DataFrame:
    out = df.copy()
    out["gross_R"] = out["result_R"].astype(float)
    out["net_R"] = apply_costs(out, multiplier=multiplier)
    return out


def performance(df: pd.DataFrame, *, net: bool = True, col: str | None = None) -> Dict[str, float]:
    if df.empty:
        return {"N": 0, "win_rate": np.nan, "AvgR": np.nan, "TotalR": np.nan, "PF": np.nan, "MaxDD": np.nan, "Return_over_DD": np.nan}
    working = enrich_net(df) if net and col is None else df.copy()
    rcol = col or ("net_R" if net else "gross_R")
    if rcol not in working.columns:
        working["net_R"] = apply_costs(working)
        rcol = "net_R"
    r = working[rcol].astype(float)
    gp, gl = r[r > 0].sum(), abs(r[r < 0].sum())
    mdd = max_drawdown(r.to_numpy())
    return {
        "N": int(len(working)),
        "win_rate": float((r > 0).mean()),
        "AvgR": float(r.mean()),
        "TotalR": float(r.sum()),
        "PF": float(gp / gl) if gl > 0 else (99.9 if gp > 0 else 0.0),
        "MaxDD": float(mdd),
        "Return_over_DD": float(r.sum() / mdd) if mdd > 0 else float("inf"),
    }


def simulate_all(signals: pd.DataFrame, market: pd.DataFrame, config: SimConfig) -> pd.DataFrame:
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    rows = [simulate_trade(row, market, pos_map, config).__dict__ for row in signals.itertuples(index=False)]
    out = pd.DataFrame(rows)
    meta = signals[["signal_id", "direction", "confirm_timestamp", "bos_timestamp", "session_bucket", "score"]]
    return out.merge(meta, on="signal_id", how="left")


def verify_parity(signals: pd.DataFrame, market: pd.DataFrame) -> Dict[str, float]:
    from phase16.sequential_bos import apply_costs as engine_costs

    enriched = engine_costs(signals.sort_values("entry_timestamp"))
    net = enriched["net_R"].astype(float)
    perf = {
        "N": len(enriched),
        "net_AvgR": float(net.mean()),
        "net_TotalR": float(net.sum()),
        "net_PF": float(net[net > 0].sum() / abs(net[net < 0].sum())) if (net < 0).any() else 99.9,
        "MaxDD": float(max_drawdown(net.to_numpy())),
    }
    sim = simulate_all(
        signals,
        market,
        SimConfig(
            entry_model="CURRENT",
            stop_atr=BASELINE_STOP_ATR,
            target_r=BASELINE_TARGET_R,
            max_bars=hold_bars(BASELINE_HOLD_MINUTES),
            management="FIXED",
        ),
    )
    sim_filled = sim.loc[sim.filled]
    sim_perf = performance(sim_filled)
    failures = []
    if abs(perf["N"] - PARITY["N"]) > PARITY["tol_N"]:
        failures.append(f"N engine={perf['N']} expected≈{PARITY['N']}")
    if abs(perf["net_AvgR"] - PARITY["net_AvgR"]) > PARITY["tol_AvgR"]:
        failures.append(f"net_AvgR engine={perf['net_AvgR']:.4f}")
    if failures:
        raise RuntimeError("Baseline parity failed:\n" + "\n".join(failures))
    return perf


def trade_paths(signals: pd.DataFrame, market: pd.DataFrame, sim: pd.DataFrame) -> pd.DataFrame:
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    profit_levels = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
    loss_levels = (0.5, 1.0)
    rows = []
    filled = sim.loc[sim.filled]
    for row in filled.itertuples(index=False):
        ts = row.entry_timestamp
        if ts not in pos_map:
            continue
        i = pos_map[ts]
        risk = abs(float(row.entry_price) - float(row.stop_price))
        if risk <= 0:
            continue
        hi = market["high"].to_numpy()[i + 1 : i + 37]
        lo = market["low"].to_numpy()[i + 1 : i + 37]
        probs = first_passage_probs(row.direction, float(row.entry_price), risk, hi, lo, profit_levels, loss_levels)
        rows.append(
            {
                "signal_id": row.signal_id,
                "direction": row.direction,
                "mfe_r": row.mfe_r,
                "mae_r": row.mae_r,
                "result_R": row.result_R,
                **probs,
            }
        )
    return pd.DataFrame(rows)


def entry_study(signals, market, base_cfg):
    rows, matched, limit = [], [], []
    current = simulate_all(signals, market, base_cfg)
    cur_f = current.loc[current.filled].set_index("signal_id")
    for model in ENTRY_MODELS:
        cfg = SimConfig(
            entry_model=model,
            stop_atr=base_cfg.stop_atr,
            target_r=base_cfg.target_r,
            max_bars=base_cfg.max_bars,
            management=base_cfg.management,
        )
        sim = simulate_all(signals, market, cfg)
        filled = sim.loc[sim.filled]
        rows.append({"entry_model": model, "signals": len(signals), "fills": len(filled), "fill_rate": len(filled) / max(len(signals), 1), **performance(filled)})
        if model != "CURRENT":
            common = filled.set_index("signal_id").index.intersection(cur_f.index)
            if len(common):
                c, a = cur_f.loc[common], filled.set_index("signal_id").loc[common]
                pc, pa = performance(c.reset_index()), performance(a.reset_index())
                matched.append(
                    {
                        "entry_model": model,
                        "matched_N": len(common),
                        "current_net_AvgR": pc["AvgR"],
                        "alt_net_AvgR": pa["AvgR"],
                        "delta_net_AvgR": pa["AvgR"] - pc["AvgR"],
                        "current_net_PF": pc["PF"],
                        "alt_net_PF": pa["PF"],
                        "delta_net_PF": pa["PF"] - pc["PF"],
                        "current_MaxDD": pc["MaxDD"],
                        "alt_MaxDD": pa["MaxDD"],
                    }
                )
            filled_ids = set(filled.signal_id)
            unfilled_ids = set(sim.loc[~sim.filled].signal_id)
            limit.append(
                {
                    "entry_model": model,
                    "filled_current_net_AvgR": float(performance(cur_f.loc[cur_f.index.intersection(filled_ids)].reset_index())["AvgR"]) if filled_ids else np.nan,
                    "unfilled_current_net_AvgR": float(performance(cur_f.loc[cur_f.index.intersection(unfilled_ids)].reset_index())["AvgR"]) if unfilled_ids else np.nan,
                    "fills": len(filled_ids),
                    "unfilled": len(unfilled_ids),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(matched), pd.DataFrame(limit)


def sweep(signals, market, base_cfg, col_name, values, apply_fn):
    rows = []
    for val in values:
        cfg = apply_fn(base_cfg, val)
        sim = simulate_all(signals, market, cfg)
        rows.append({col_name: val, **performance(sim.loc[sim.filled])})
    return pd.DataFrame(rows)


def build_shortlist(entry_df, stop_df, target_df, hold_df, mgmt_df) -> Dict[str, list]:
    def top(df, col, n):
        return df.sort_values("AvgR", ascending=False).head(n)[col].tolist()

    return {
        "entry": top(entry_df, "entry_model", 2),
        "stop": top(stop_df, "stop_atr", 3),
        "target": top(target_df, "target_r", 3),
        "hold": top(hold_df, "hold_minutes", 2),
        "management": top(mgmt_df, "management", 2),
    }


def score_train(filled: pd.DataFrame) -> float:
    if len(filled) < 30:
        return -999.0
    p = performance(filled)
    dd = abs(p["MaxDD"]) if p["MaxDD"] else 1.0
    return p["AvgR"] * 2.0 + (p["PF"] - 1.0) * 0.5 + p["TotalR"] / dd * 0.01


def optimization_grid(signals, market, shortlist):
    rows = []
    for entry, stop, target, hold, mgmt in product(
        shortlist["entry"], shortlist["stop"], shortlist["target"], shortlist["hold"], shortlist["management"]
    ):
        cfg = SimConfig(entry_model=entry, stop_atr=stop, target_r=target, max_bars=hold_bars(hold), management=mgmt)
        sim = simulate_all(signals, market, cfg)
        filled = sim.loc[sim.filled]
        rows.append({"entry_model": entry, "stop_atr": stop, "target_r": target, "hold_minutes": hold, "management": mgmt, "score": score_train(filled), **performance(filled)})
    return pd.DataFrame(rows).sort_values("score", ascending=False)


def walk_forward(signals, market, grid):
    tz = signals["entry_timestamp"].dt.tz
    fold_rows, stitched_parts, selections = [], [], []
    combos = grid.to_dict("records")
    for train_start, train_end, test_start, test_end in WALK_FORWARD_FOLDS:
        train_sig = signals.loc[(signals.entry_timestamp >= pd.Timestamp(train_start, tz=tz)) & (signals.entry_timestamp <= pd.Timestamp(train_end, tz=tz))]
        test_sig = signals.loc[(signals.entry_timestamp >= pd.Timestamp(test_start, tz=tz)) & (signals.entry_timestamp <= pd.Timestamp(test_end, tz=tz))]
        if len(train_sig) < 30 or len(test_sig) < 5:
            continue
        best_score, best_cfg = -999.0, SimConfig()
        for row in combos:
            cfg = SimConfig(
                entry_model=row["entry_model"],
                stop_atr=row["stop_atr"],
                target_r=row["target_r"],
                max_bars=hold_bars(int(row["hold_minutes"])),
                management=row["management"],
            )
            sc = score_train(simulate_all(train_sig, market, cfg).loc[lambda d: d.filled])
            if sc > best_score:
                best_score, best_cfg = sc, cfg
        test_sim = simulate_all(test_sig, market, best_cfg)
        filled = enrich_net(test_sim.loc[test_sim.filled])
        filled["fold_test_end"] = test_end
        stitched_parts.append(filled)
        fold_rows.append({"train_end": train_end, "test_end": test_end, **performance(filled), **best_cfg.__dict__})
        selections.append(best_cfg.__dict__ | {"hold_minutes": best_cfg.max_bars * 15})
    folds = pd.DataFrame(fold_rows)
    stitched = pd.concat(stitched_parts, ignore_index=True) if stitched_parts else pd.DataFrame()
    stab = []
    if selections:
        sel = pd.DataFrame(selections)
        for col in sel.columns:
            for val, cnt in sel[col].value_counts().items():
                stab.append({"parameter": col, "value": val, "count": int(cnt), "folds": len(sel)})
    return folds, stitched, pd.DataFrame(stab)


def era_yearly(signals_or_trades: pd.DataFrame, *, ts_col: str = "entry_timestamp") -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = enrich_net(signals_or_trades) if "net_R" not in signals_or_trades.columns else signals_or_trades.copy()
    ts = pd.to_datetime(df[ts_col], utc=True).dt.tz_convert(signals_or_trades[ts_col].dt.tz)
    df["year"] = ts.dt.year
    yearly = pd.DataFrame([{"year": int(y), **performance(g)} for y, g in df.groupby("year")])
    era_rows = []
    for name, start, end in ERAS:
        sub = df.loc[(ts >= pd.Timestamp(start, tz=ts.dt.tz)) & (ts <= pd.Timestamp(end, tz=ts.dt.tz))]
        era_rows.append({"era": name, **performance(sub)})
    return yearly, pd.DataFrame(era_rows)


def long_short_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for direction in ("Long", "Short"):
        sub = df.loc[df["direction"] == direction] if "direction" in df.columns else pd.DataFrame()
        rows.append({"direction": direction, **performance(sub)})
    return pd.DataFrame(rows)


def giveback(df: pd.DataFrame) -> pd.DataFrame:
    w = df.copy()
    w["giveback_r"] = w["mfe_r"] - w["result_R"].astype(float)
    return pd.DataFrame(
        [
            {"metric": "pct_hit_0.5R_finish_negative", "value": float(((w.mfe_r >= 0.5) & (w.net_R < 0)).mean())},
            {"metric": "pct_hit_1R_finish_negative", "value": float(((w.mfe_r >= 1.0) & (w.net_R < 0)).mean())},
            {"metric": "pct_hit_1.5R_finish_nonpositive", "value": float(((w.mfe_r >= 1.5) & (w.net_R <= 0)).mean())},
            {"metric": "pct_hit_2R_fail_realize_1R", "value": float(((w.mfe_r >= 2.0) & (w.net_R < 1.0)).mean())},
            {"metric": "median_giveback", "value": float(w.giveback_r.median())},
        ]
    )


def outlier_table(df: pd.DataFrame) -> pd.DataFrame:
    w = enrich_net(df.sort_values("entry_timestamp"))
    rows = []
    for label, sub in (
        ("full", w),
        ("exclude_best", w.nsmallest(len(w) - 1, "net_R")),
        ("exclude_top3", w.nsmallest(max(1, len(w) - 3), "net_R")),
        ("exclude_top1pct", w.loc[w.net_R <= w.net_R.quantile(0.99)]),
    ):
        rows.append({"scenario": label, **performance(sub, col="net_R")})
    return pd.DataFrame(rows)


def cost_stress(df: pd.DataFrame, label: str) -> List[dict]:
    rows = []
    for mult in (1.0, 1.5, 2.0):
        net = apply_costs(df, multiplier=mult)
        rows.append({"architecture": label, "cost_multiplier": mult, **performance(df.assign(net_R=net), col="net_R")})
    return rows


def success_criteria(wf: Dict, era_df: pd.DataFrame, outlier_df: pd.DataFrame, cost_df: pd.DataFrame, stab_df: pd.DataFrame) -> Tuple[int, List[str]]:
    checks = []
    checks.append(("N>=150", wf.get("N", 0) >= 150))
    checks.append(("Net AvgR>=0.08", wf.get("AvgR", -9) >= 0.08))
    checks.append(("Net PF>=1.20", wf.get("PF", 0) >= 1.20))
    checks.append(("Net TotalR>0", wf.get("TotalR", -9) > 0))
    checks.append(("MaxDD<=10", wf.get("MaxDD", 99) <= 10))
    pos_eras = sum(1 for _, r in era_df.iterrows() if r.get("AvgR", 0) > 0)
    checks.append(("2/3 eras positive", pos_eras >= 2))
    if not outlier_df.empty:
        ex_best = outlier_df.loc[outlier_df.scenario == "exclude_best"]
        checks.append(("ex-best positive", bool(len(ex_best) and ex_best.iloc[0]["AvgR"] > 0)))
        ex1 = outlier_df.loc[outlier_df.scenario == "exclude_top1pct"]
        checks.append(("ex-top1% positive", bool(len(ex1) and ex1.iloc[0]["AvgR"] > 0)))
    c15 = cost_df.loc[(cost_df.architecture == "walk_forward") & (cost_df.cost_multiplier == 1.5)]
    checks.append(("1.5x cost positive", bool(len(c15) and c15.iloc[0]["AvgR"] > 0)))
    if len(stab_df):
        max_count = int(stab_df["count"].max())
        n_folds = int(stab_df["folds"].iloc[0])
        stable = max_count >= max(2, int(n_folds * 0.4))
    else:
        stable = False
    checks.append(("parameter stability", stable))
    passed = sum(1 for _, ok in checks if ok)
    return passed, [name for name, ok in checks if ok]


def classify(passed: int, wf: Dict) -> str:
    if passed >= 8 and wf.get("AvgR", 0) >= 0.10 and wf.get("PF", 0) >= 1.30:
        return "A"
    if passed >= 6 and wf.get("AvgR", 0) >= 0.08 and wf.get("PF", 0) >= 1.20:
        return "B"
    if wf.get("TotalR", 0) > 0:
        return "C"
    return "D"


def run_phase29(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    market = load_market_15m()
    signals = extract_signals(market)
    signals.to_csv(output / "baseline.csv", index=False)

    base_cfg = SimConfig(
        entry_model="CURRENT",
        stop_atr=BASELINE_STOP_ATR,
        target_r=BASELINE_TARGET_R,
        max_bars=hold_bars(BASELINE_HOLD_MINUTES),
        management="FIXED",
    )
    parity = verify_parity(signals, market)
    baseline_sim = simulate_all(signals, market, base_cfg)
    baseline_filled = enrich_net(baseline_sim.loc[baseline_sim.filled])
    baseline_perf = performance(baseline_filled)

    paths = trade_paths(signals, market, baseline_sim)
    paths.to_csv(output / "trade_paths.csv", index=False)

    mfe_row = {
        "median_MFE": float(baseline_filled["mfe_r"].median()),
        "median_MAE": float(baseline_filled["mae_r"].median()),
        "mean_MFE": float(baseline_filled["mfe_r"].mean()),
        "mean_MAE": float(baseline_filled["mae_r"].mean()),
    }
    for k in ("P_p0.5R_before_l0.5R", "P_p1.0R_before_l0.5R", "P_p1.0R_before_l1.0R", "P_p1.5R_before_l1.0R", "P_p2.0R_before_l1.0R", "P_p2.5R_before_l1.0R", "P_p3.0R_before_l1.0R"):
        if k in paths.columns:
            mfe_row[k] = float(paths[k].mean())
    mfe_df = pd.DataFrame([mfe_row])
    mfe_df.to_csv(output / "mfe_mae.csv", index=False)

    giveback_df = giveback(baseline_filled)
    giveback_df.to_csv(output / "giveback.csv", index=False)

    entry_df, matched_df, _ = entry_study(signals, market, base_cfg)
    entry_df.to_csv(output / "entry_study.csv", index=False)
    matched_df.to_csv(output / "matched_entry.csv", index=False)

    best_entry = entry_df.sort_values("AvgR", ascending=False).iloc[0]["entry_model"]
    entry_cfg = SimConfig(entry_model=best_entry, stop_atr=BASELINE_STOP_ATR, target_r=BASELINE_TARGET_R, max_bars=hold_bars(BASELINE_HOLD_MINUTES), management="FIXED")

    stop_df = sweep(signals, market, entry_cfg, "stop_atr", STOP_ATRS, lambda c, v: SimConfig(c.entry_model, v, c.target_r, c.max_bars, c.management))
    target_df = sweep(signals, market, entry_cfg, "target_r", TARGET_RS, lambda c, v: SimConfig(c.entry_model, c.stop_atr, v, c.max_bars, c.management))
    hold_df = sweep(signals, market, entry_cfg, "hold_minutes", HOLD_MINUTES, lambda c, v: SimConfig(c.entry_model, c.stop_atr, c.target_r, hold_bars(v), c.management))
    mgmt_df = sweep(signals, market, entry_cfg, "management", MANAGEMENT_MODELS, lambda c, v: SimConfig(c.entry_model, c.stop_atr, c.target_r, c.max_bars, v))
    stop_df.to_csv(output / "stop_study.csv", index=False)
    target_df.to_csv(output / "target_study.csv", index=False)
    hold_df.to_csv(output / "hold_study.csv", index=False)
    mgmt_df.to_csv(output / "management_study.csv", index=False)

    ls_base = long_short_table(baseline_filled)
    ls_base.to_csv(output / "long_short.csv", index=False)

    ablation = []
    for label, filt in (("BOTH", signals), ("LONG_ONLY", signals.loc[signals.direction == "Long"]), ("SHORT_ONLY", signals.loc[signals.direction == "Short"])):
        sim = simulate_all(filt, market, entry_cfg)
        ablation.append({"population": label, **performance(sim.loc[sim.filled])})
    ablation_df = pd.DataFrame(ablation)
    ablation_df.to_csv(output / "directional_ablation.csv", index=False)

    shortlist = build_shortlist(entry_df, stop_df, target_df, hold_df, mgmt_df)
    grid = optimization_grid(signals, market, shortlist)
    grid.to_csv(output / "optimization_grid.csv", index=False)
    is_best = grid.iloc[0].to_dict() if not grid.empty else {}

    folds, stitched, stab = walk_forward(signals, market, grid)
    folds.to_csv(output / "walk_forward_folds.csv", index=False)
    stab.to_csv(output / "parameter_stability.csv", index=False)
    if not stitched.empty:
        stitched.to_csv(output / "walk_forward_trades.csv", index=False)

    wf_perf = performance(stitched) if not stitched.empty else {}
    wf_ls = long_short_table(stitched) if not stitched.empty else pd.DataFrame()
    yearly, era_df = era_yearly(stitched if not stitched.empty else baseline_filled)
    yearly.to_csv(output / "yearly.csv", index=False)
    era_df.to_csv(output / "era.csv", index=False)

    outlier_df = outlier_table(stitched) if not stitched.empty else pd.DataFrame()
    outlier_df.to_csv(output / "outlier_robustness.csv", index=False)

    cost_rows = cost_stress(baseline_filled, "baseline")
    if not stitched.empty:
        cost_rows.extend(cost_stress(stitched, "walk_forward"))
    cost_df = pd.DataFrame(cost_rows)
    cost_df.to_csv(output / "cost_stress.csv", index=False)

    passed, passed_names = success_criteria(wf_perf, era_df, outlier_df, cost_df, stab)
    final = classify(passed, wf_perf)
    ready = final in {"A", "B"} and passed >= 6

    days = max((pd.Timestamp(COMMON_END) - pd.Timestamp(COMMON_START)).days, 1)
    freq = {"baseline_trades_per_month": baseline_perf["N"] / (days / 30.4375), "wf_trades_per_month": wf_perf.get("N", 0) / (days / 30.4375) if wf_perf else 0}

    manifest = {
        "phase": "Phase 29",
        "parity": parity,
        "baseline_net": baseline_perf,
        "in_sample_best": is_best,
        "walk_forward_net": wf_perf,
        "shortlist": shortlist,
        "success_criteria_passed": passed,
        "success_criteria": passed_names,
        "final_classification": final,
        "ready_for_pine": ready,
        "frequency": freq,
    }
    (output / "study_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    with pd.ExcelWriter(output / "CRT_V2_15M_OPTIMIZATION.xlsx", engine="openpyxl") as writer:
        for name in ["baseline", "entry_study", "stop_study", "target_study", "hold_study", "management_study", "optimization_grid", "walk_forward_folds", "era", "yearly", "cost_stress", "outlier_robustness"]:
            p = output / f"{name}.csv"
            if p.exists():
                pd.read_csv(p).to_excel(writer, sheet_name=name[:31], index=False)

    report = [
        "# CRT V2 @ 15m Optimization Report",
        f"**Classification:** {final}",
        f"**Ready for Pine:** {'YES' if ready else 'NO'}",
        f"**Baseline N:** {baseline_perf['N']} | net AvgR {baseline_perf['AvgR']:.4f} | PF {baseline_perf['PF']:.2f}",
        f"**Walk-forward N:** {wf_perf.get('N', 0)} | net AvgR {wf_perf.get('AvgR', 0):.4f} | PF {wf_perf.get('PF', 0):.2f}",
        f"**Success criteria:** {passed}/10",
    ]
    (output / "CRT_V2_15M_OPTIMIZATION_REPORT.md").write_text("\n".join(report) + "\n")
    return manifest


def main() -> int:
    manifest = run_phase29()
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
