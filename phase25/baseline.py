"""Load frozen BOS baseline and market data."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig
from phase16.data_loader import load_ohlcv_csv
from phase16.indicators import add_base_indicators
from phase17.analysis_core import max_drawdown, read_trades

from .config import NQ_DATA_PATHS, ROUND_TURN_COST_USD, NQ_DOLLARS_PER_POINT, TRADE_SOURCES


def load_market(config: FrozenConfig = FrozenConfig()) -> pd.DataFrame:
    frames = [load_ohlcv_csv(p, exchange_timezone=config.exchange_timezone) for p in NQ_DATA_PATHS]
    market = pd.concat(frames).sort_index()
    market = market[~market.index.duplicated(keep="last")]
    return add_base_indicators(market, config)


def load_bos_trades() -> pd.DataFrame:
    frames = []
    for path in TRADE_SOURCES:
        trades = read_trades(path)
        bos = trades.loc[trades["model"] == "BOS"].copy()
        bos["source"] = path.parent.name
        frames.append(bos)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("entry_timestamp", kind="stable").reset_index(drop=True)
    combined["signal_id"] = np.arange(len(combined))
    return combined


def apply_costs(trades: pd.DataFrame, result_col: str = "result_R", *, multiplier: float = 1.0) -> pd.Series:
    if "stop_price" in trades.columns and trades["stop_price"].notna().any():
        risk_pts = (trades["entry_price"].astype(float) - trades["stop_price"].astype(float)).abs()
    else:
        risk_pts = trades.get("risk", pd.Series(7.5, index=trades.index)).astype(float)
    cost_r = (ROUND_TURN_COST_USD * multiplier) / (risk_pts * NQ_DOLLARS_PER_POINT)
    return trades[result_col].astype(float) - cost_r


def performance(df: pd.DataFrame, result_col: str = "result_R") -> Dict[str, float]:
    if df.empty:
        return {"N": 0, "win_rate": np.nan, "AvgR": np.nan, "TotalR": np.nan, "PF": np.nan, "MaxDD": np.nan}
    r = df[result_col].astype(float)
    wins = r[r > 0].sum()
    losses = abs(r[r < 0].sum())
    return {
        "N": int(len(df)),
        "win_rate": float((r > 0).mean()),
        "AvgR": float(r.mean()),
        "TotalR": float(r.sum()),
        "PF": float(wins / losses) if losses > 0 else float("inf"),
        "MaxDD": float(max_drawdown(r.to_numpy())),
        "return_over_dd": float(r.sum() / abs(max_drawdown(r.to_numpy()))) if max_drawdown(r.to_numpy()) != 0 else np.nan,
    }


def bootstrap_avg_r(values: np.ndarray, *, samples: int = 2000, seed: int = 25) -> Tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    if len(values) == 0:
        return float("nan"), float("nan"), float("nan")
    means = [rng.choice(values, size=len(values), replace=True).mean() for _ in range(samples)]
    return float(np.mean(means)), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))
