"""Phase 25 BOS trade architecture optimization — full study runner."""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig

from .baseline import apply_costs, bootstrap_avg_r, load_bos_trades, load_market, performance
from .config import (
    ENTRY_MODELS,
    HOLD_MINUTES,
    MANAGEMENT_MODELS,
    MC_SIMULATIONS,
    PATH_HORIZONS,
    RESULTS,
    R_LEVELS,
    LOSS_LEVELS,
    STOP_ATRS,
    TARGET_RS,
    WALK_FORWARD_FOLDS,
)
from .trade_simulator import SimConfig, first_passage_probs, simulate_trade


def _results_to_df(results: list) -> pd.DataFrame:
    return pd.DataFrame([r.__dict__ for r in results])


def simulate_all(signals: pd.DataFrame, market: pd.DataFrame, config: SimConfig) -> pd.DataFrame:
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    rows = [simulate_trade(row, market, pos_map, config) for row in signals.itertuples(index=False)]
    out = _results_to_df(rows)
    out = out.merge(signals[["signal_id", "direction", "entry_timestamp", "session_bucket"]], on="signal_id", how="left")
    return out


def score_config(df: pd.DataFrame) -> float:
    filled = df.loc[df["filled"]]
    if len(filled) < 50:
        return -999.0
    perf = performance(filled)
    pf = perf["PF"] if np.isfinite(perf["PF"]) else 0.0
    dd = abs(perf["MaxDD"]) if perf["MaxDD"] != 0 else 1.0
    return perf["AvgR"] * 2.0 + (pf - 1.0) * 0.5 + perf["TotalR"] / dd * 0.01


def baseline_reports(bos: pd.DataFrame, output: Path) -> Dict[str, Any]:
    bos.to_csv(output / "baseline_bos.csv", index=False)
    base = performance(bos)
    years = []
    bos = bos.copy()
    bos["year"] = bos["entry_timestamp"].dt.year
    bos["half"] = np.where(bos["entry_timestamp"] < bos["entry_timestamp"].median(), "first_half", "second_half")
    for y, g in bos.groupby("year"):
        years.append({"year": int(y), **performance(g)})
    for half, g in bos.groupby("half"):
        years.append({"period": half, **performance(g)})
    for direction in ("Long", "Short"):
        years.append({"direction": direction, **performance(bos.loc[bos.direction == direction])})

    robust = []
    r = bos["result_R"].astype(float).to_numpy()
    for label, sub in (
        ("full", bos),
        ("exclude_best", bos.nsmallest(len(bos) - 1, "result_R") if len(bos) > 1 else bos),
        ("exclude_top3", bos.nsmallest(max(1, len(bos) - 3), "result_R")),
        ("exclude_top1pct", bos.nsmallest(max(1, int(len(bos) * 0.99)), "result_R")),
    ):
        robust.append({"scenario": label, **performance(sub)})
    mean, lo, hi = bootstrap_avg_r(r)
    return {
        "baseline": base,
        "trades_per_year": base["N"] / ((bos.entry_timestamp.max() - bos.entry_timestamp.min()).days / 365.25),
        "yearly": years,
        "robustness": robust,
        "bootstrap_avg_r": {"mean": mean, "ci_low": lo, "ci_high": hi},
    }


def build_trade_paths(bos: pd.DataFrame, market: pd.DataFrame, output: Path) -> pd.DataFrame:
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    rows = []
    for trade in bos.itertuples(index=False):
        ts = trade.entry_timestamp
        if ts not in pos_map:
            continue
        i = pos_map[ts]
        risk = abs(trade.entry_price - trade.stop_price)
        direction = trade.direction
        row = {"signal_id": trade.signal_id, "direction": direction, "entry_timestamp": ts}
        highs = market["high"].to_numpy()
        lows = market["low"].to_numpy()
        path_hi = highs[i + 1 : i + 37]
        path_lo = lows[i + 1 : i + 37]
        mfe = mae = 0.0
        bt_mfe = bt_mae = np.nan
        for h in PATH_HORIZONS:
            if h > len(path_hi):
                continue
            if direction == "Long":
                mfe_h = (path_hi[:h].max() - trade.entry_price) / risk
                mae_h = (trade.entry_price - path_lo[:h].min()) / risk
            else:
                mfe_h = (trade.entry_price - path_lo[:h].min()) / risk
                mae_h = (path_hi[:h].max() - trade.entry_price) / risk
            row[f"mfe_{h}"] = mfe_h
            row[f"mae_{h}"] = mae_h
            if mfe_h > mfe:
                mfe, bt_mfe = mfe_h, h
            if mae_h > mae:
                mae, bt_mae = mae_h, h
        row["mfe_r"] = mfe
        row["mae_r"] = mae
        row["bars_to_mfe"] = bt_mfe
        row["bars_to_mae"] = bt_mae
        probs = first_passage_probs(direction, trade.entry_price, risk, path_hi, path_lo, R_LEVELS, LOSS_LEVELS)
        row.update(probs)
        rows.append(row)
    paths = pd.DataFrame(rows)
    paths.to_csv(output / "bos_trade_paths.csv", index=False)
    return paths


def mfe_mae_geometry(paths: pd.DataFrame, bos: pd.DataFrame, output: Path) -> pd.DataFrame:
    rows = []
    for label, subset_ids in (
        ("ALL", paths.signal_id),
        ("LONG", bos.loc[bos.direction == "Long", "signal_id"]),
        ("SHORT", bos.loc[bos.direction == "Short", "signal_id"]),
    ):
        sub = paths.loc[paths.signal_id.isin(subset_ids)]
        if sub.empty:
            continue
        row = {
            "population": label,
            "median_mfe": float(sub["mfe_r"].median()),
            "mean_mfe": float(sub["mfe_r"].mean()),
            "median_mae": float(sub["mae_r"].median()),
            "mean_mae": float(sub["mae_r"].mean()),
        }
        for q in (0.25, 0.5, 0.75):
            row[f"mfe_q{int(q*100)}"] = float(sub["mfe_r"].quantile(q))
            row[f"mae_q{int(q*100)}"] = float(sub["mae_r"].quantile(q))
        for key in (
            "p_0.25R_before_0.25R",
            "p_0.5R_before_0.5R",
            "p_1.0R_before_0.5R",
            "p_1.0R_before_1.0R",
            "p_1.5R_before_0.5R",
            "p_1.5R_before_1.0R",
            "p_2.0R_before_1.0R",
            "p_2.5R_before_1.0R",
            "p_3.0R_before_1.0R",
        ):
            if key in sub.columns:
                row[key] = float(sub[key].mean())
        rows.append(row)
    geom = pd.DataFrame(rows)
    geom.to_csv(output / "mfe_mae_geometry.csv", index=False)
    return geom


def entry_study(signals: pd.DataFrame, market: pd.DataFrame, output: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows, matched_rows, limit_rows = [], [], []
    current = simulate_all(signals, market, SimConfig(entry_model="CURRENT"))
    current_filled = current.loc[current.filled].set_index("signal_id")
    for model in ENTRY_MODELS:
        sim = simulate_all(signals, market, SimConfig(entry_model=model))
        filled = sim.loc[sim.filled]
        perf = performance(filled)
        rows.append({"entry_model": model, "signals": len(signals), "fills": len(filled), "fill_rate": len(filled) / len(signals), **perf})
        if model != "CURRENT":
            common = filled.set_index("signal_id").index.intersection(current_filled.index)
            if len(common):
                cur = current_filled.loc[common]
                alt = filled.set_index("signal_id").loc[common]
                matched_rows.append(
                    {
                        "entry_model": model,
                        "matched_N": len(common),
                        "current_AvgR": float(cur["result_R"].mean()),
                        "alt_AvgR": float(alt["result_R"].mean()),
                        "delta_AvgR": float(alt["result_R"].mean() - cur["result_R"].mean()),
                        "current_PF": performance(cur.reset_index())["PF"],
                        "alt_PF": performance(alt.reset_index())["PF"],
                        "delta_PF": performance(alt.reset_index())["PF"] - performance(cur.reset_index())["PF"],
                        "current_MaxDD": performance(cur.reset_index())["MaxDD"],
                        "alt_MaxDD": performance(alt.reset_index())["MaxDD"],
                    }
                )
            filled_ids = set(filled.signal_id)
            unfilled_ids = set(sim.loc[~sim.filled].signal_id)
            limit_rows.append(
                {
                    "entry_model": model,
                    "filled_current_AvgR": float(current_filled.loc[current_filled.index.intersection(filled_ids), "result_R"].mean()) if filled_ids else np.nan,
                    "unfilled_current_AvgR": float(current_filled.loc[current_filled.index.intersection(unfilled_ids), "result_R"].mean()) if unfilled_ids else np.nan,
                    "fills": len(filled_ids),
                    "unfilled": len(unfilled_ids),
                }
            )
    entry_df = pd.DataFrame(rows)
    matched_df = pd.DataFrame(matched_rows)
    limit_df = pd.DataFrame(limit_rows)
    entry_df.to_csv(output / "entry_model_comparison.csv", index=False)
    matched_df.to_csv(output / "matched_entry_comparison.csv", index=False)
    limit_df.to_csv(output / "limit_fill_analysis.csv", index=False)
    return entry_df, matched_df, limit_df


def sweep_study(signals, market, output):
    cfg = SimConfig()
    stop_rows, target_rows, hold_rows, mgmt_rows = [], [], [], []
    for stop in STOP_ATRS:
        sim = simulate_all(signals, market, SimConfig(stop_atr=stop))
        stop_rows.append({"stop_atr": stop, **performance(sim.loc[sim.filled])})
    for target in TARGET_RS:
        sim = simulate_all(signals, market, SimConfig(target_r=target))
        target_rows.append({"target_r": target, **performance(sim.loc[sim.filled])})
    for hold in HOLD_MINUTES:
        bars = max(1, round(hold / 5))
        sim = simulate_all(signals, market, SimConfig(max_bars=bars))
        hold_rows.append({"hold_minutes": hold, "max_bars": bars, **performance(sim.loc[sim.filled])})
    for mgmt in MANAGEMENT_MODELS:
        sim = simulate_all(signals, market, SimConfig(management=mgmt))
        mgmt_rows.append({"management": mgmt, **performance(sim.loc[sim.filled])})
    stop_df = pd.DataFrame(stop_rows)
    target_df = pd.DataFrame(target_rows)
    hold_df = pd.DataFrame(hold_rows)
    mgmt_df = pd.DataFrame(mgmt_rows)
    stop_df.to_csv(output / "stop_sweep.csv", index=False)
    target_df.to_csv(output / "target_sweep.csv", index=False)
    hold_df.to_csv(output / "hold_sweep.csv", index=False)
    mgmt_df.to_csv(output / "trade_management.csv", index=False)
    return stop_df, target_df, hold_df, mgmt_df


def exit_efficiency(bos: pd.DataFrame, paths: pd.DataFrame, output: Path) -> pd.DataFrame:
    merged = bos.merge(paths[["signal_id", "mfe_r"]], on="signal_id", how="left")
    merged["giveback_r"] = merged["mfe_r"] - merged["result_R"].astype(float)
    rows = [
        {"metric": "pct_hit_0.5R_finish_negative", "value": float(((merged.mfe_r >= 0.5) & (merged.result_R < 0)).mean())},
        {"metric": "pct_hit_1R_finish_negative", "value": float(((merged.mfe_r >= 1.0) & (merged.result_R < 0)).mean())},
        {"metric": "pct_hit_1.5R_finish_nonpositive", "value": float(((merged.mfe_r >= 1.5) & (merged.result_R <= 0)).mean())},
        {"metric": "pct_hit_1R_fail_2R", "value": float(((merged.mfe_r >= 1.0) & (merged.result_R < 2.0)).mean())},
        {"metric": "median_giveback", "value": float(merged.giveback_r.median())},
        {"metric": "mean_giveback", "value": float(merged.giveback_r.mean())},
    ]
    return pd.DataFrame(rows)


def build_shortlist(entry_df, stop_df, target_df, hold_df, mgmt_df) -> Dict[str, list]:
    def top(df, col, n=2):
        return df.sort_values("AvgR", ascending=False).head(n)[col].tolist()

    entries = top(entry_df, "entry_model", 3)
    stops = top(stop_df, "stop_atr", 3)
    targets = top(target_df, "target_r", 3)
    holds = top(hold_df, "hold_minutes", 2)
    mgmt = top(mgmt_df, "management", 2)
    return {"entry": entries, "stop": stops, "target": targets, "hold": holds, "management": mgmt}


def optimization_grid(signals, market, shortlist, output):
    rows = []
    combos = list(
        product(
            shortlist["entry"],
            shortlist["stop"],
            shortlist["target"],
            shortlist["hold"],
            shortlist["management"],
        )
    )
    for entry, stop, target, hold, mgmt in combos[:200]:
        bars = max(1, round(hold / 5))
        sim = simulate_all(
            signals,
            market,
            SimConfig(entry_model=entry, stop_atr=stop, target_r=target, max_bars=bars, management=mgmt),
        )
        filled = sim.loc[sim.filled]
        rows.append(
            {
                "entry_model": entry,
                "stop_atr": stop,
                "target_r": target,
                "hold_minutes": hold,
                "management": mgmt,
                "score": score_config(sim),
                **performance(filled),
            }
        )
    grid = pd.DataFrame(rows).sort_values("score", ascending=False)
    grid.to_csv(output / "optimization_grid.csv", index=False)
    return grid


def walk_forward(signals, market, grid, output):
    tz = signals["entry_timestamp"].dt.tz
    fold_rows, test_trades, selections = [], [], []
    param_cols = ["entry_model", "stop_atr", "target_r", "hold_minutes", "management"]
    for train_start, train_end, test_start, test_end in WALK_FORWARD_FOLDS:
        train_sig = signals.loc[
            (signals.entry_timestamp >= pd.Timestamp(train_start, tz=tz))
            & (signals.entry_timestamp <= pd.Timestamp(train_end, tz=tz))
        ]
        test_sig = signals.loc[
            (signals.entry_timestamp >= pd.Timestamp(test_start, tz=tz))
            & (signals.entry_timestamp <= pd.Timestamp(test_end, tz=tz))
        ]
        if len(train_sig) < 100 or len(test_sig) < 20:
            continue
        best_score = -999
        best_cfg = SimConfig()
        for _, row in grid.head(30).iterrows():
            cfg = SimConfig(
                entry_model=row["entry_model"],
                stop_atr=row["stop_atr"],
                target_r=row["target_r"],
                max_bars=max(1, round(row["hold_minutes"] / 5)),
                management=row["management"],
            )
            train_sim = simulate_all(train_sig, market, cfg)
            sc = score_config(train_sim)
            if sc > best_score:
                best_score, best_cfg = sc, cfg
        test_sim = simulate_all(test_sig, market, best_cfg)
        filled = test_sim.loc[test_sim.filled].copy()
        filled["fold_test_start"] = test_start
        test_trades.append(filled)
        fold_rows.append({"train_end": train_end, "test_end": test_end, **performance(filled), **best_cfg.__dict__})
        selections.append(best_cfg.__dict__)
    folds = pd.DataFrame(fold_rows)
    stitched = pd.concat(test_trades, ignore_index=True) if test_trades else pd.DataFrame()
    folds.to_csv(output / "walk_forward_folds.csv", index=False)
    if not stitched.empty:
        stitched.to_csv(output / "walk_forward_trades.csv", index=False)
    stab_rows: List[dict] = []
    if selections:
        sel_df = pd.DataFrame(selections)
        for col in sel_df.columns:
            counts = sel_df[col].value_counts()
            for val, cnt in counts.items():
                stab_rows.append({"parameter": col, "value": val, "count": int(cnt), "folds": len(sel_df)})
    pd.DataFrame(stab_rows).to_csv(output / "parameter_stability.csv", index=False)
    return folds, stitched, pd.DataFrame(stab_rows)


def session_analysis(bos, output):
    from phase16.indicators import session_bucket_name

    bos = bos.copy()
    bos["session"] = bos["session_bucket"].map(session_bucket_name)
    rows = [performance(g.assign(result_R=g.result_R)) | {"session": s} for s, g in bos.groupby("session")]
    df = pd.DataFrame(rows)
    df.to_csv(output / "session_analysis.csv", index=False)
    return df


def cost_stress_report(bos, stitched, output):
    rows = []
    for label, df in (("baseline", bos), ("walk_forward", stitched)):
        if df is None or df.empty:
            continue
        for mult in (1.0, 1.5, 2.0):
            net = apply_costs(df, multiplier=mult)
            rows.append({"architecture": label, "cost_multiplier": mult, **performance(df.assign(result_R=net))})
    out = pd.DataFrame(rows)
    out.to_csv(output / "cost_stress.csv", index=False)
    return out


def monte_carlo(stitched, output):
    r = stitched["result_R"].astype(float).to_numpy()
    rng = np.random.default_rng(25)
    terminals, dds, streaks = [], [], []
    for _ in range(MC_SIMULATIONS):
        sample = rng.choice(r, size=len(r), replace=True)
        terminals.append(sample.sum())
        eq = np.cumsum(sample)
        dds.append(float(np.max(np.maximum.accumulate(eq) - eq)))
        streak = cur = 0
        for v in sample:
            cur = cur + 1 if v < 0 else 0
            streak = max(streak, cur)
        streaks.append(streak)
    mc = {
        "median_terminal_R": float(np.median(terminals)),
        "p5_terminal_R": float(np.quantile(terminals, 0.05)),
        "p25_terminal_R": float(np.quantile(terminals, 0.25)),
        "p75_terminal_R": float(np.quantile(terminals, 0.75)),
        "p95_terminal_R": float(np.quantile(terminals, 0.95)),
        "P_terminal_R_gt_0": float(np.mean(np.array(terminals) > 0)),
        "median_MaxDD": float(np.median(dds)),
        "p95_MaxDD": float(np.quantile(dds, 0.95)),
        "median_losing_streak": float(np.median(streaks)),
        "p95_losing_streak": float(np.quantile(streaks, 0.95)),
    }
    pd.DataFrame([mc]).to_csv(output / "monte_carlo.csv", index=False)
    return mc


def classify_wf(wf_perf, baseline_perf, mc, yearly) -> str:
    checks = [
        wf_perf["N"] >= 200,
        wf_perf["AvgR"] > 0.05,
        wf_perf["PF"] >= 1.15,
        wf_perf["TotalR"] > 0,
        mc["P_terminal_R_gt_0"] >= 0.80,
    ]
    passed = sum(checks)
    if passed >= 4 and wf_perf["PF"] >= 1.20 and wf_perf["AvgR"] >= 0.08:
        return "A"
    if passed >= 3 and wf_perf["PF"] >= 1.15:
        return "B"
    if wf_perf["TotalR"] > 0:
        return "C"
    return "D"


def run_phase25(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    config = FrozenConfig()
    market = load_market(config)
    bos = load_bos_trades()
    base_info = baseline_reports(bos, output)
    paths = build_trade_paths(bos, market, output)
    geom = mfe_mae_geometry(paths, bos, output)
    entry_df, matched_df, limit_df = entry_study(bos, market, output)
    stop_df, target_df, hold_df, mgmt_df = sweep_study(bos, market, output)
    exit_efficiency(bos, paths, output)
    shortlist = build_shortlist(entry_df, stop_df, target_df, hold_df, mgmt_df)
    grid = optimization_grid(bos, market, shortlist, output)
    folds, stitched, stab = walk_forward(bos, market, grid, output)
    session_analysis(bos, output)
    cost_stress_report(bos, stitched, output)
    mc = monte_carlo(stitched, output) if not stitched.empty else {}
    wf_perf = performance(stitched) if not stitched.empty else {}
    wf_net = performance(stitched.assign(result_R=apply_costs(stitched))) if not stitched.empty and "stop_price" in stitched.columns else {}
    best_is = grid.iloc[0].to_dict() if not grid.empty else {}
    yearly = []
    if not stitched.empty:
        stitched = stitched.copy()
        stitched["year"] = stitched["entry_timestamp"].dt.year
        for y, g in stitched.groupby("year"):
            yearly.append({"year": int(y), **performance(g)})
        pd.DataFrame(yearly).to_csv(output / "yearly.csv", index=False)
        stitched["quarter"] = stitched["entry_timestamp"].dt.to_period("Q").astype(str)
        q = pd.DataFrame([{"quarter": qtr, **performance(g)} for qtr, g in stitched.groupby("quarter")])
        q.to_csv(output / "quarterly.csv", index=False)
    outlier = []
    if not stitched.empty:
        for label, sub in (
            ("full", stitched),
            ("exclude_best", stitched.nsmallest(len(stitched) - 1, "result_R")),
            ("exclude_top3", stitched.nsmallest(max(1, len(stitched) - 3), "result_R")),
            ("exclude_top1pct", stitched.nsmallest(max(1, int(len(stitched) * 0.99)), "result_R")),
        ):
            outlier.append({"scenario": label, **performance(sub)})
        pd.DataFrame(outlier).to_csv(output / "outlier_robustness.csv", index=False)
    final_class = classify_wf(wf_perf, base_info["baseline"], mc, yearly) if wf_perf else "D"
    manifest = {
        "phase": "Phase 25 — BOS Trade Architecture Optimization",
        "baseline_gross": base_info["baseline"],
        "baseline_net_1x": performance(bos.assign(result_R=apply_costs(bos))),
        "baseline_totalR_expected_gross": 48.24,
        "walk_forward_gross": wf_perf,
        "walk_forward_net_1x": wf_net,
        "in_sample_best": best_is,
        "monte_carlo": mc,
        "final_classification": "D" if (not wf_net or wf_net.get("TotalR", 0) <= 0) else classify_wf(wf_perf, base_info["baseline"], mc, yearly),
        "shortlist": shortlist,
    }
    (output / "study_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest
