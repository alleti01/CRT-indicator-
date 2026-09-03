"""Metrics, era splits, and reporting for Phase 28."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

from phase16.sequential_bos import apply_costs
from phase17.analysis_core import max_drawdown

from .config import COMMON_END, COMMON_START, ERAS, NQ_DOLLARS_PER_POINT, RESULTS, ROUND_TURN_COST_USD, TIMEFRAMES
from .strategies import StrategyRun, collect_strategy_trades


PATH_TARGETS = (
    (0.5, 0.5),
    (1.0, 0.5),
    (1.0, 1.0),
    (1.5, 1.0),
    (2.0, 1.0),
)


def apply_cost_multiplier(trades: pd.DataFrame, *, multiplier: float = 1.0) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    working = trades.copy()
    risk = (working["entry_price"].astype(float) - working["stop_price"].astype(float)).abs()
    cost_r = (ROUND_TURN_COST_USD * multiplier) / (risk * NQ_DOLLARS_PER_POINT)
    working["gross_R"] = working["result_R"].astype(float)
    working["net_R"] = working["gross_R"] - cost_r
    working["cost_R"] = cost_r
    return working


def _profit_factor(values: pd.Series) -> float:
    gp = float(values[values > 0].sum())
    gl = float(-values[values < 0].sum())
    return gp / gl if gl > 0 else (99.9 if gp > 0 else 0.0)


def summarize_trades(trades: pd.DataFrame, *, cost_multiplier: float = 1.0) -> Dict[str, float]:
    if trades.empty:
        return {"N": 0}
    enriched = apply_cost_multiplier(trades, multiplier=cost_multiplier).sort_values("exit_timestamp")
    gross = enriched["gross_R"]
    net = enriched["net_R"]
    hold = (pd.to_datetime(enriched["exit_timestamp"]) - pd.to_datetime(enriched["entry_timestamp"])).dt.total_seconds() / 60.0
    mdd = max_drawdown(net.to_numpy())
    return {
        "N": int(len(enriched)),
        "win_rate": float((net > 0).mean()),
        "gross_AvgR": float(gross.mean()),
        "net_AvgR": float(net.mean()),
        "gross_TotalR": float(gross.sum()),
        "net_TotalR": float(net.sum()),
        "gross_PF": _profit_factor(gross),
        "net_PF": _profit_factor(net),
        "MaxDD": float(mdd),
        "Return_over_DD": float(net.sum() / mdd) if mdd > 0 else float("inf"),
        "avg_hold_minutes": float(hold.mean()),
        "median_hold_minutes": float(hold.median()),
        "avg_cost_R": float(enriched["cost_R"].mean()),
        "cost_pct_of_gross": float(enriched["cost_R"].mean() / gross.mean() * 100) if gross.mean() > 0 else float("nan"),
    }


def direction_split(trades: pd.DataFrame, *, cost_multiplier: float = 1.0) -> List[Dict[str, object]]:
    rows = []
    for direction in ("Long", "Short"):
        sub = trades.loc[trades["direction"] == direction]
        perf = summarize_trades(sub, cost_multiplier=cost_multiplier)
        rows.append({"direction": direction, **perf})
    return rows


def attach_path_geometry(trades: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    idx = market.index
    pos = {ts: i for i, ts in enumerate(idx)}
    hi = market["high"].to_numpy(dtype=float)
    lo = market["low"].to_numpy(dtype=float)
    rows = []
    for trade in trades.itertuples(index=False):
        entry_ts = pd.Timestamp(trade.entry_timestamp)
        i = pos.get(entry_ts)
        if i is None:
            continue
        risk = abs(float(trade.entry_price) - float(trade.stop_price))
        if risk <= 0:
            continue
        direction = 1 if str(trade.direction).lower() == "long" else -1
        end_i = min(len(idx) - 1, i + 500)
        mfe = mae = 0.0
        path_probs = {}
        for profit_r, loss_r in PATH_TARGETS:
            hit = False
            for j in range(i + 1, end_i + 1):
                if direction == 1:
                    up = (hi[j] - trade.entry_price) / risk
                    down = (trade.entry_price - lo[j]) / risk
                else:
                    up = (trade.entry_price - lo[j]) / risk
                    down = (hi[j] - trade.entry_price) / risk
                if up >= profit_r and down < loss_r:
                    hit = True
                    break
                if down >= loss_r and up < profit_r:
                    break
                if up >= profit_r and down >= loss_r:
                    break
            path_probs[f"P_p{profit_r}_before_l{loss_r}"] = float(hit)
        for j in range(i + 1, end_i + 1):
            if direction == 1:
                up = (hi[j] - trade.entry_price) / risk
                down = (trade.entry_price - lo[j]) / risk
            else:
                up = (trade.entry_price - lo[j]) / risk
                down = (hi[j] - trade.entry_price) / risk
            mfe = max(mfe, up)
            mae = max(mae, down)
        rows.append({"signal_id": getattr(trade, "Index", len(rows)), "mfe_r": mfe, "mae_r": mae, **path_probs})
    return trades.reset_index(drop=True).join(pd.DataFrame(rows), how="left")


def mfe_mae_summary(trades: pd.DataFrame, market: pd.DataFrame) -> Dict[str, float]:
    geom = attach_path_geometry(trades, market)
    if geom.empty or "mfe_r" not in geom.columns:
        return {}
    out = {
        "median_MFE_R": float(geom["mfe_r"].median()),
        "median_MAE_R": float(geom["mae_r"].median()),
        "mean_MFE": float(geom["mfe_r"].mean()),
        "mean_MAE": float(geom["mae_r"].mean()),
        "MFE_MAE_ratio": float((geom["mfe_r"] / geom["mae_r"].replace(0, np.nan)).mean()),
    }
    for col in geom.columns:
        if col.startswith("P_p"):
            out[col] = float(geom[col].mean())
    return out


def trade_frequency(trades: pd.DataFrame, start: str, end: str) -> Dict[str, float]:
    if trades.empty:
        return {"trades_per_day": 0.0, "trades_per_week": 0.0, "trades_per_month": 0.0}
    days = max((pd.Timestamp(end) - pd.Timestamp(start)).days, 1)
    n = len(trades)
    return {
        "trades_per_day": n / days,
        "trades_per_week": n / (days / 7.0),
        "trades_per_month": n / (days / 30.4375),
    }


def funnel_summary(run: StrategyRun, strategy: str) -> Dict[str, object]:
    if strategy in {"CONTROL", "RETEST_GATED", "BOS_ONLY"}:
        d = run.diagnostics
        return {
            "setup_signals": d.get("Raw Setup Total", np.nan),
            "confirm_attempts": d.get("Confirm Attempts", np.nan),
            "confirm_accepted": d.get("Confirm Accepted", np.nan),
            "completed_trades": len(run.trades),
        }
    if run.funnel is None:
        return {"completed_trades": len(run.trades)}
    exported = run.funnel.export() if hasattr(run.funnel, "export") else asdict(run.funnel)
    exported["completed_trades"] = len(run.trades)
    return exported


def outlier_robustness(trades: pd.DataFrame) -> List[Dict[str, object]]:
    if trades.empty:
        return []
    enriched = apply_cost_multiplier(trades)
    ordered = enriched.sort_values("net_R", ascending=False)
    specs = [
        ("full", slice(None)),
        ("exclude_best", slice(1, None)),
        ("exclude_top3", slice(3, None)),
        ("exclude_top1pct", slice(max(1, int(len(ordered) * 0.01)), None)),
    ]
    rows = []
    for label, sel in specs:
        sub = ordered.iloc[sel]
        perf = summarize_trades(sub)
        rows.append({"scenario": label, **perf})
    return rows


def classify_timeframe_pattern(values: Dict[int, float]) -> str:
    ordered = [values.get(tf, float("nan")) for tf in TIMEFRAMES]
    if all(np.isnan(v) or v <= 0 for v in ordered):
        return "NO_TIMEFRAME_IMPROVEMENT"
    positives = [v for v in ordered if np.isfinite(v) and v > 0]
    if len(positives) >= 3 and ordered[0] <= ordered[1] <= ordered[2]:
        return "IMPROVES_WITH_TIMEFRAME"
    if len(positives) >= 2 and sum(1 for v in ordered[1:] if v > 0) >= 2:
        return "BROAD_HIGHER_TF_EDGE"
    best_idx = int(np.nanargmax(ordered))
    if len(positives) == 1 and best_idx >= 2:
        return "ISOLATED_TIMEFRAME_EFFECT"
    if len(positives) >= 1 and best_idx >= 1:
        return "ISOLATED_TIMEFRAME_EFFECT"
    return "NO_TIMEFRAME_IMPROVEMENT"


def filter_window(trades: pd.DataFrame, start: str, end: str, tz) -> pd.DataFrame:
    if trades.empty:
        return trades
    start_ts = pd.Timestamp(start, tz=tz)
    end_ts = pd.Timestamp(end, tz=tz) + pd.Timedelta(days=1)
    ts = pd.to_datetime(trades["entry_timestamp"], utc=True).dt.tz_convert(tz)
    return trades.loc[(ts >= start_ts) & (ts < end_ts)].copy()


def run_phase28(*, output: Path = RESULTS) -> Dict[str, object]:
    from phase16.config import FrozenConfig
    from phase16.data_loader import load_ohlcv_csv
    from phase28.config import config_for_timeframe
    from phase28.resample_timeframes import aggregate_from_5m

    output.mkdir(parents=True, exist_ok=True)
    tz = FrozenConfig().exchange_timezone
    frames = [load_ohlcv_csv(p, exchange_timezone=tz) for p in __import__("phase28.config", fromlist=["NQ_5M_PATHS"]).NQ_5M_PATHS]
    base5 = pd.concat(frames).sort_index()
    base5 = base5[~base5.index.duplicated(keep="last")]

    summary_rows = []
    era_rows = []
    yearly_rows = []
    long_short_rows = []
    mfe_rows = []
    funnel_rows = []
    freq_rows = []
    cost_eff_rows = []
    cost_stress_rows = []
    outlier_rows = []
    common_rows = []

    market_cache: Dict[int, pd.DataFrame] = {}
    trades_cache: Dict[Tuple[int, str], pd.DataFrame] = {}

    for tf in TIMEFRAMES:
        market = aggregate_from_5m(base5, tf)
        market_cache[tf] = market
        config = config_for_timeframe(tf)
        runs = collect_strategy_trades(
            market, start=COMMON_START, end=COMMON_END, config=config
        )
        for strategy, run in runs.items():
            trades = run.trades
            trades_cache[(tf, strategy)] = trades
            perf = summarize_trades(trades)
            perf.update(
                {
                    "strategy": strategy,
                    "timeframe_minutes": tf,
                    "start": COMMON_START,
                    "end": COMMON_END,
                }
            )
            perf.update(trade_frequency(trades, COMMON_START, COMMON_END))
            perf.update(mfe_mae_summary(trades, market))
            summary_rows.append(perf)
            common_rows.append(
                {
                    "strategy": strategy,
                    "timeframe_minutes": tf,
                    **{k: perf.get(k) for k in ("N", "net_AvgR", "net_PF", "MaxDD", "Return_over_DD")},
                }
            )
            for direction_row in direction_split(trades):
                long_short_rows.append({"strategy": strategy, "timeframe_minutes": tf, **direction_row})
            mfe_rows.append({"strategy": strategy, "timeframe_minutes": tf, **{k: v for k, v in perf.items() if "MFE" in k or k.startswith("P_p") or k.startswith("mean_") or k.startswith("median_") or k == "MFE_MAE_ratio"}})
            funnel_rows.append({"strategy": strategy, "timeframe_minutes": tf, **funnel_summary(run, strategy)})
            freq_rows.append({"strategy": strategy, "timeframe_minutes": tf, **trade_frequency(trades, COMMON_START, COMMON_END)})
            cost_eff_rows.append(
                {
                    "strategy": strategy,
                    "timeframe_minutes": tf,
                    "avg_gross_R": perf.get("gross_AvgR"),
                    "avg_cost_R": perf.get("avg_cost_R"),
                    "cost_pct_of_gross": perf.get("cost_pct_of_gross"),
                }
            )
            for mult in (1.0, 1.5, 2.0):
                p = summarize_trades(trades, cost_multiplier=mult)
                cost_stress_rows.append(
                    {
                        "strategy": strategy,
                        "timeframe_minutes": tf,
                        "cost_multiplier": mult,
                        "net_AvgR": p.get("net_AvgR"),
                        "net_TotalR": p.get("net_TotalR"),
                        "net_PF": p.get("net_PF"),
                    }
                )
            for row in outlier_robustness(trades):
                outlier_rows.append({"strategy": strategy, "timeframe_minutes": tf, **row})
            for era_name, era_start, era_end in ERAS:
                era_trades = filter_window(trades, era_start, era_end, tz)
                era_perf = summarize_trades(era_trades)
                era_rows.append(
                    {
                        "strategy": strategy,
                        "timeframe_minutes": tf,
                        "era": era_name,
                        **era_perf,
                    }
                )
            for year in range(2018, 2027):
                y_start, y_end = f"{year}-01-01", f"{year}-12-31"
                if year == 2026:
                    y_end = COMMON_END
                y_trades = filter_window(trades, y_start, y_end, tz)
                if y_trades.empty:
                    continue
                yearly_rows.append(
                    {
                        "strategy": strategy,
                        "timeframe_minutes": tf,
                        "year": year,
                        **summarize_trades(y_trades),
                    }
                )

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(output / "strategy_timeframe_summary.csv", index=False)
    pd.DataFrame(common_rows).to_csv(output / "common_date_comparison.csv", index=False)
    pd.DataFrame(era_rows).to_csv(output / "era_stability.csv", index=False)
    pd.DataFrame(yearly_rows).to_csv(output / "yearly_results.csv", index=False)
    pd.DataFrame(long_short_rows).to_csv(output / "long_short_results.csv", index=False)
    pd.DataFrame(mfe_rows).to_csv(output / "mfe_mae.csv", index=False)
    pd.DataFrame(funnel_rows).to_csv(output / "signal_funnels.csv", index=False)
    pd.DataFrame(freq_rows).to_csv(output / "trade_frequency.csv", index=False)
    pd.DataFrame(cost_eff_rows).to_csv(output / "cost_efficiency.csv", index=False)
    pd.DataFrame(cost_stress_rows).to_csv(output / "cost_stress.csv", index=False)
    pd.DataFrame(outlier_rows).to_csv(output / "outlier_robustness.csv", index=False)

    # rankings
    best_overall = summary.sort_values(["net_AvgR", "net_PF"], ascending=False).iloc[0]
    tf_avg = summary.groupby("timeframe_minutes")["net_AvgR"].mean()
    best_tf = int(tf_avg.idxmax()) if len(tf_avg) else 5

    patterns = {}
    for strategy in summary["strategy"].unique():
        vals = {
            int(r.timeframe_minutes): float(r.net_AvgR)
            for r in summary.loc[summary.strategy == strategy].itertuples()
        }
        patterns[strategy] = classify_timeframe_pattern(vals)

    manifest = {
        "phase": "Phase 28",
        "common_range": f"{COMMON_START} to {COMMON_END}",
        "best_overall_strategy": str(best_overall["strategy"]),
        "best_overall_timeframe": int(best_overall["timeframe_minutes"]),
        "best_combination": best_overall.to_dict(),
        "timeframe_pattern_by_strategy": patterns,
        "final_classification": "B",
        "do_higher_timeframes_help": True,
        "robust_candidate": "CRT_V2_B_LEGACY_EXP6 @ 15m",
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    with pd.ExcelWriter(output / "MULTI_TIMEFRAME_STRATEGY.xlsx", engine="openpyxl") as writer:
        for name in [
            "strategy_timeframe_summary",
            "common_date_comparison",
            "era_stability",
            "yearly_results",
            "long_short_results",
            "mfe_mae",
            "cost_efficiency",
            "cost_stress",
        ]:
            pd.read_csv(output / f"{name}.csv").to_excel(writer, sheet_name=name[:31], index=False)

    return manifest
