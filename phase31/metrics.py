"""Metrics, walk-forward, and reporting for Phase 31."""

from __future__ import annotations

from itertools import product
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from phase17.analysis_core import max_drawdown
from phase29.config import ROUND_TURN_COST_USD
from phase29.simulator import SimConfig, first_passage_probs, simulate_trade

from .config import (
    CHART_MINUTES,
    ENTRY_MODELS,
    FREQ_BANDS,
    HOLD_MINUTES,
    MC_SIMULATIONS,
    NQ_DOLLARS_PER_POINT,
    SHORTLIST_EXECUTION_GRID,
    STOP_ATRS,
    TARGET_RS,
    WALK_FORWARD_FOLDS,
    hold_bars,
)
from .dedupe import rth_trading_dates


def apply_costs(df: pd.DataFrame, *, multiplier: float = 1.0, col: str = "result_R") -> pd.Series:
    if df.empty or "stop_price" not in df.columns:
        return pd.Series(dtype=float)
    risk = (df["entry_price"].astype(float) - df["stop_price"].astype(float)).abs()
    cost_r = (ROUND_TURN_COST_USD * multiplier) / (risk * NQ_DOLLARS_PER_POINT)
    return df[col].astype(float) - cost_r


def enrich_net(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["net_R"] = apply_costs(out)
    return out


def performance(df: pd.DataFrame, *, col: str = "result_R") -> Dict[str, float]:
    if df is None or df.empty:
        return {"N": 0, "WinRate": 0.0, "AvgR": 0.0, "TotalR": 0.0, "PF": 0.0, "MaxDD": 0.0, "ReturnMaxDD": 0.0}
    r = df[col].astype(float).to_numpy()
    wins = r[r > 0].sum()
    losses = abs(r[r < 0].sum())
    pf = wins / losses if losses > 0 else (999.0 if wins > 0 else 0.0)
    total = float(r.sum())
    mdd = max_drawdown(r)
    return {
        "N": int(len(r)),
        "WinRate": float((r > 0).mean()),
        "AvgR": float(r.mean()),
        "TotalR": total,
        "PF": float(pf),
        "MaxDD": float(mdd),
        "ReturnMaxDD": float(total / mdd) if mdd > 0 else 0.0,
    }


def net_performance(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return performance(df)
    return performance(enrich_net(df), col="net_R")


def simulate_all(signals: pd.DataFrame, market: pd.DataFrame, cfg: SimConfig) -> pd.DataFrame:
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    rows = [simulate_trade(row, market, pos_map, cfg).__dict__ for row in signals.itertuples(index=False)]
    out = pd.DataFrame(rows)
    meta_cols = [c for c in ("signal_id", "direction", "entry_timestamp", "bos_timestamp", "architecture", "event_id") if c in signals.columns]
    if meta_cols:
        out = out.merge(signals[meta_cols], on="signal_id", how="left", suffixes=("", "_sig"))
    return out


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


def daily_distribution(
    signals_or_trades: pd.DataFrame,
    market: pd.DataFrame,
    *,
    ts_col: str = "entry_timestamp",
) -> Dict[str, Any]:
    rth_days = rth_trading_dates(market)
    total_rth = len(rth_days)
    if signals_or_trades.empty:
        return {
            "total_rth_days": total_rth,
            "days_0": total_rth,
            "days_1": 0,
            "days_2": 0,
            "days_3plus": 0,
            "mean_signals_day": 0.0,
            "median_signals_day": 0.0,
            "p90_signals_day": 0.0,
            "mean_trades_week": 0.0,
            "longest_no_signal_stretch": total_rth,
            "pct_days_0": 1.0,
            "pct_days_1": 0.0,
            "pct_days_2": 0.0,
            "pct_days_gt2": 0.0,
        }
    ts = pd.to_datetime(signals_or_trades[ts_col], utc=True)
    day_counts = (
        pd.Series([cme_session_date(pd.DatetimeIndex([t]))[0] for t in ts])
        .value_counts()
        .reindex(rth_days, fill_value=0)
    )
    counts = day_counts.to_numpy()
    stretches = []
    cur = 0
    for c in counts:
        if c == 0:
            cur += 1
            stretches.append(cur)
        else:
            cur = 0
    return {
        "total_rth_days": total_rth,
        "days_0": int((counts == 0).sum()),
        "days_1": int((counts == 1).sum()),
        "days_2": int((counts == 2).sum()),
        "days_3plus": int((counts >= 3).sum()),
        "mean_signals_day": float(counts.mean()),
        "median_signals_day": float(np.median(counts)),
        "p90_signals_day": float(np.quantile(counts, 0.90)),
        "mean_trades_week": float(counts.sum() / max(1, total_rth / 5)),
        "longest_no_signal_stretch": int(max(stretches) if stretches else 0),
        "pct_days_0": float((counts == 0).mean()),
        "pct_days_1": float((counts == 1).mean()),
        "pct_days_2": float((counts == 2).mean()),
        "pct_days_gt2": float((counts > 2).mean()),
    }


def cme_session_date(index: pd.DatetimeIndex) -> pd.Index:
    from phase16.resample import cme_session_date as _csd

    return _csd(index)


def fold_execution_grid(_train_sig: pd.DataFrame, _market: pd.DataFrame) -> pd.DataFrame:
    """Fixed shortlist grid per fold (no in-fold sweeps — keeps search small)."""
    return pd.DataFrame(SHORTLIST_EXECUTION_GRID)


def optimization_grid() -> pd.DataFrame:
    rows = []
    for entry, stop, target, hold in product(ENTRY_MODELS, STOP_ATRS, TARGET_RS, HOLD_MINUTES):
        rows.append(
            {
                "entry_model": entry,
                "stop_atr": stop,
                "target_r": target,
                "hold_minutes": hold,
                "management": "FIXED",
            }
        )
    return pd.DataFrame(rows)


def score_train(filled: pd.DataFrame, *, trades_day: float = 0.0) -> float:
    if filled.empty or len(filled) < 30:
        return -999.0
    perf = net_performance(filled)
    if perf["AvgR"] <= 0:
        return -999.0
    freq_pen = 0.0
    if trades_day < 0.75:
        freq_pen = (0.75 - trades_day) * 0.5
    elif trades_day > 2.0:
        freq_pen = (trades_day - 2.0) * 0.3
    return (
        perf["AvgR"] * 2.0
        + (perf["PF"] - 1.0) * 0.5
        + perf["TotalR"] / max(perf["MaxDD"], 0.5) * 0.01
        - freq_pen
    )


def walk_forward(
    signals: pd.DataFrame,
    market: pd.DataFrame,
    grid: pd.DataFrame,
    *,
    architecture: str,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tz = signals["entry_timestamp"].dt.tz
    fold_rows, stitched_parts, selections = [], [], []
    combo_count = 0
    for train_start, train_end, test_start, test_end in WALK_FORWARD_FOLDS:
        train_sig = signals.loc[
            (signals.entry_timestamp >= pd.Timestamp(train_start, tz=tz))
            & (signals.entry_timestamp <= pd.Timestamp(train_end, tz=tz))
        ]
        test_sig = signals.loc[
            (signals.entry_timestamp >= pd.Timestamp(test_start, tz=tz))
            & (signals.entry_timestamp <= pd.Timestamp(test_end, tz=tz))
        ]
        if len(train_sig) < 30 or len(test_sig) < 5:
            continue
        fold_grid = fold_execution_grid(train_sig, market)
        combos = fold_grid.to_dict("records")
        combo_count += len(combos)
        rth_days_train = max(
            1,
            len(
                rth_trading_dates(
                    market.loc[train_sig.entry_timestamp.min() : train_sig.entry_timestamp.max()]
                )
            ),
        )
        best_score, best_cfg = -999.0, SimConfig()
        sim_cache: Dict[tuple, pd.DataFrame] = {}
        for row in combos:
            cfg = SimConfig(
                entry_model=row["entry_model"],
                stop_atr=row["stop_atr"],
                target_r=row["target_r"],
                max_bars=hold_bars(int(row["hold_minutes"])),
                management=row["management"],
            )
            key = (cfg.entry_model, cfg.stop_atr, cfg.target_r, cfg.max_bars, cfg.management)
            if key not in sim_cache:
                sim_cache[key] = simulate_all(train_sig, market, cfg)
            sim = sim_cache[key]
            filled = enrich_net(sim.loc[sim.filled])
            td = len(filled) / rth_days_train
            sc = score_train(filled, trades_day=td)
            if sc > best_score:
                best_score, best_cfg = sc, cfg
        test_sim = simulate_all(test_sig, market, best_cfg)
        filled = enrich_net(test_sim.loc[test_sim.filled])
        filled["architecture"] = architecture
        filled["fold_test_end"] = test_end
        stitched_parts.append(filled)
        fold_rows.append(
            {
                "architecture": architecture,
                "train_end": train_end,
                "test_end": test_end,
                **performance(filled, col="net_R"),
                **best_cfg.__dict__,
                "hold_minutes": best_cfg.max_bars * CHART_MINUTES,
            }
        )
        selections.append(
            best_cfg.__dict__
            | {"hold_minutes": best_cfg.max_bars * CHART_MINUTES, "architecture": architecture, "test_end": test_end}
        )
    folds = pd.DataFrame(fold_rows)
    stitched = pd.concat(stitched_parts, ignore_index=True) if stitched_parts else pd.DataFrame()
    sel = pd.DataFrame(selections)
    stab = []
    if not sel.empty:
        for col in ("entry_model", "stop_atr", "target_r", "hold_minutes"):
            for val, cnt in sel[col].value_counts().items():
                stab.append({"architecture": architecture, "parameter": col, "value": val, "count": int(cnt), "folds": len(sel)})
    stitched.attrs["combo_count"] = combo_count
    return folds, stitched, pd.DataFrame(stab)


def yearly_results(trades: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    df = enrich_net(trades.copy())
    ts = pd.to_datetime(df["entry_timestamp"], utc=True)
    df["year"] = ts.dt.year
    rows = []
    for year, g in df.groupby("year"):
        y_start, y_end = f"{year}-01-01", f"{year}-12-31"
        mkt_y = market.loc[y_start:y_end]
        rth_days = max(1, len(rth_trading_dates(mkt_y)))
        rows.append({"year": int(year), "trades_day": len(g) / rth_days, **performance(g, col="net_R")})
    return pd.DataFrame(rows)


def outlier_robustness(trades: pd.DataFrame) -> pd.DataFrame:
    w = enrich_net(trades.sort_values("entry_timestamp"))
    rows = []
    for label, sub in (
        ("full", w),
        ("exclude_best", w.nsmallest(max(0, len(w) - 1), "net_R")),
        ("exclude_top3", w.nsmallest(max(1, len(w) - 3), "net_R")),
        ("exclude_top1pct", w.loc[w.net_R <= w.net_R.quantile(0.99)]),
    ):
        rows.append({"scenario": label, **performance(sub, col="net_R")})
    return pd.DataFrame(rows)


def cost_stress(trades: pd.DataFrame, architecture: str) -> pd.DataFrame:
    rows = []
    for mult in (1.0, 1.5, 2.0):
        net = apply_costs(trades, multiplier=mult)
        rows.append({"architecture": architecture, "cost_multiplier": mult, **performance(trades.assign(net_R=net), col="net_R")})
    return pd.DataFrame(rows)


def monte_carlo(trades: pd.DataFrame) -> Dict[str, float]:
    if trades.empty:
        return {}
    r = enrich_net(trades)["net_R"].astype(float).to_numpy()
    rng = np.random.default_rng(31)
    terminals, dds, streaks = [], [], []
    for _ in range(MC_SIMULATIONS):
        sample = rng.choice(r, size=len(r), replace=True)
        terminals.append(float(sample.sum()))
        eq = np.cumsum(sample)
        dds.append(float(np.max(np.maximum.accumulate(eq) - eq)))
        streak = cur = 0
        for v in sample:
            cur = cur + 1 if v < 0 else 0
            streak = max(streak, cur)
        streaks.append(streak)
    return {
        "P_terminal_R_gt_0": float(np.mean(np.array(terminals) > 0)),
        "p5_terminal_R": float(np.quantile(terminals, 0.05)),
        "median_terminal_R": float(np.median(terminals)),
        "p95_terminal_R": float(np.quantile(terminals, 0.95)),
        "median_MaxDD": float(np.median(dds)),
        "p95_MaxDD": float(np.quantile(dds, 0.95)),
        "median_losing_streak": float(np.median(streaks)),
        "p95_losing_streak": float(np.quantile(streaks, 0.95)),
    }


def success_criteria(
    wf: Dict[str, float],
    daily: Dict[str, Any],
    yearly: pd.DataFrame,
    outlier: pd.DataFrame,
    cost: pd.DataFrame,
    trades: pd.DataFrame,
) -> Tuple[int, List[Tuple[str, bool]]]:
    checks: List[Tuple[str, bool]] = []
    checks.append(("N>=300", wf.get("N", 0) >= 300))
    mean_td = daily.get("mean_signals_day", 0.0)
    checks.append(("freq>=0.75/day", mean_td >= 0.75))
    checks.append(("freq<=2.0/day", mean_td <= 2.0))
    checks.append(("Net AvgR>=0.10", wf.get("AvgR", -9) >= 0.10))
    checks.append(("Net PF>=1.20", wf.get("PF", 0) >= 1.20))
    checks.append(("Net TotalR>0", wf.get("TotalR", -9) > 0))
    checks.append(("Return/MaxDD>=2", wf.get("ReturnMaxDD", 0) >= 2.0))
    if not yearly.empty:
        pos_years = int((yearly["AvgR"] > 0).sum())
        total_years = len(yearly)
        checks.append((">=60% years positive", pos_years >= max(1, int(np.ceil(total_years * 0.6)))))
        pos_r = yearly.loc[yearly["TotalR"] > 0, "TotalR"]
        checks.append(("no year >50% pos R", bool(pos_r.empty or pos_r.max() <= 0.5 * wf.get("TotalR", 0))))
    else:
        checks.extend([(">=60% years positive", False), ("no year >50% pos R", False)])
    if not trades.empty:
        ts = pd.to_datetime(trades["entry_timestamp"], utc=True)
        mid = ts.min() + (ts.max() - ts.min()) / 2
        first = enrich_net(trades.loc[ts <= mid])
        second = enrich_net(trades.loc[ts > mid])
        checks.append(("first half positive", performance(first, col="net_R")["TotalR"] > 0))
        checks.append(("second half positive", performance(second, col="net_R")["TotalR"] > 0))
    else:
        checks.extend([("first half positive", False), ("second half positive", False)])
    if not outlier.empty:
        ex_best = outlier.loc[outlier.scenario == "exclude_best"]
        ex1 = outlier.loc[outlier.scenario == "exclude_top1pct"]
        checks.append(("ex-best positive", bool(len(ex_best) and ex_best.iloc[0]["AvgR"] > 0)))
        checks.append(("ex-top1% positive", bool(len(ex1) and ex1.iloc[0]["AvgR"] > 0)))
    else:
        checks.extend([("ex-best positive", False), ("ex-top1% positive", False)])
    c15 = cost.loc[cost.cost_multiplier == 1.5] if not cost.empty else pd.DataFrame()
    checks.append(("1.5x cost positive", bool(len(c15) and c15.iloc[0]["AvgR"] > 0)))
    passed = sum(1 for _, ok in checks if ok)
    return passed, checks


def classify(passed: int, wf: Dict[str, float], daily: Dict[str, Any]) -> str:
    td = daily.get("mean_signals_day", 0.0)
    in_band = 0.75 <= td <= 2.0
    if passed >= 14 and in_band and wf.get("AvgR", 0) >= 0.20 and wf.get("PF", 0) >= 1.40 and wf.get("ReturnMaxDD", 0) >= 3:
        return "A"
    if passed >= 10 and in_band and wf.get("AvgR", 0) >= 0.10 and wf.get("PF", 0) >= 1.20:
        return "B"
    if wf.get("TotalR", 0) > 0:
        return "C"
    return "D"


def frequency_frontier(arch_results: pd.DataFrame) -> pd.DataFrame:
    rows = []
    td_col = "trades_day" if "trades_day" in arch_results.columns else "mean_signals_day"
    for band in FREQ_BANDS:
        sub = arch_results.copy()
        sub["dist"] = (sub[td_col] - band).abs()
        sub = sub.loc[sub[td_col] <= band + 0.5]
        if sub.empty:
            sub = arch_results.copy()
            sub["dist"] = (sub[td_col] - band).abs()
            if sub.empty:
                continue
            best = sub.sort_values(["dist", "NetAvgR"], ascending=[True, False]).iloc[0]
        else:
            best = sub.sort_values(["NetAvgR", "NetPF"], ascending=False).iloc[0]
        rows.append(
            {
                "target_trades_day": band,
                "architecture": best["architecture"],
                "actual_trades_day": best[td_col],
                "NetAvgR": best["NetAvgR"],
                "NetPF": best["NetPF"],
                "N": best["N"],
                "ReturnMaxDD": best["ReturnMaxDD"],
            }
        )
    return pd.DataFrame(rows)
