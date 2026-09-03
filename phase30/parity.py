"""Build Python parity reference for Phase 30 Pine validation."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from phase29.config import NQ_DOLLARS_PER_POINT, frozen_config_15m
from phase29.data import extract_signals, load_market_15m
from phase29.run import apply_costs, performance, simulate_all
from phase29.simulator import SimConfig

from .config import (
    COMMON_END,
    COMMON_START,
    ENTRY_MODEL,
    ERAS,
    MANAGEMENT,
    MAX_HOLD_BARS,
    STOP_ATR,
    TARGET_R,
    VARIANT_ID,
)


def frozen_sim_config() -> SimConfig:
    return SimConfig(
        entry_model=ENTRY_MODEL,
        stop_atr=STOP_ATR,
        target_r=TARGET_R,
        max_bars=MAX_HOLD_BARS,
        management=MANAGEMENT,
    )


def _bos_level(row, market: pd.DataFrame, pos_map: Dict[pd.Timestamp, int]) -> float:
    bos_ts = pd.Timestamp(row.bos_timestamp)
    if bos_ts not in pos_map:
        return float("nan")
    bar = market.iloc[pos_map[bos_ts]]
    direction = str(row.direction).lower()
    return float(bar.high) if direction == "long" else float(bar.low)


def _setup_price(row, market: pd.DataFrame, pos_map: Dict[pd.Timestamp, int]) -> float:
    setup_ts = pd.Timestamp(row.setup_timestamp)
    if setup_ts not in pos_map:
        return float("nan")
    return float(market.iloc[pos_map[setup_ts]].close)


def build_parity_reference(
    *,
    start: str = COMMON_START,
    end: str = COMMON_END,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, float]]:
    market = load_market_15m()
    signals = extract_signals(market, start=start, end=end)
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    sim = simulate_all(signals, market, frozen_sim_config())
    filled = sim.loc[sim.filled].copy()
    if filled.empty:
        return pd.DataFrame(), pd.DataFrame(), {"N": 0}

    meta = signals[
        [
            "signal_id",
            "direction",
            "setup_timestamp",
            "bos_timestamp",
            "retest_timestamp",
            "confirm_timestamp",
        ]
    ].copy()
    out = filled.merge(meta, on=["signal_id", "direction"], how="left", suffixes=("", "_sig"))
    out["trade_id"] = out["signal_id"].astype(int)
    out["variant_id"] = VARIANT_ID
    out["entry_model"] = ENTRY_MODEL
    out["setup_price"] = out.apply(lambda r: _setup_price(r, market, pos_map), axis=1)
    out["bos_level"] = out.apply(lambda r: _bos_level(r, market, pos_map), axis=1)
    out["gross_R"] = out["result_R"].astype(float)
    out["net_R"] = apply_costs(out, gross_col="gross_R")
    out["risk_points"] = (out["entry_price"].astype(float) - out["stop_price"].astype(float)).abs()
    risk = out["risk_points"].astype(float)
    direction = out["direction"].astype(str).str.lower()
    out["target_price"] = np.where(
        direction == "long",
        out["entry_price"].astype(float) + TARGET_R * risk,
        out["entry_price"].astype(float) - TARGET_R * risk,
    )

    columns = [
        "trade_id",
        "variant_id",
        "direction",
        "entry_model",
        "setup_timestamp",
        "setup_price",
        "bos_timestamp",
        "bos_level",
        "retest_timestamp",
        "confirm_timestamp",
        "entry_timestamp",
        "entry_price",
        "stop_price",
        "target_price",
        "exit_timestamp",
        "exit_price",
        "exit_reason",
        "gross_R",
        "net_R",
        "risk_points",
        "bars_in_trade",
        "mfe_r",
        "mae_r",
    ]
    reference = out[columns].sort_values("entry_timestamp").reset_index(drop=True)
    windows = build_parity_windows(reference)
    perf = performance(reference.rename(columns={"gross_R": "result_R"}))
    perf["net_AvgR"] = float(reference["net_R"].mean()) if len(reference) else float("nan")
    perf["net_TotalR"] = float(reference["net_R"].sum()) if len(reference) else float("nan")
    return reference, windows, perf


def build_parity_windows(reference: pd.DataFrame, trades_per_window: int = 5) -> pd.DataFrame:
    rows: List[dict] = []
    if reference.empty:
        return pd.DataFrame(columns=["window_id", "era", "start", "end", "trade_id", "direction", "entry_timestamp", "entry_price", "stop_price", "target_price"])

    for era_name, era_start, era_end in ERAS:
        era = reference.loc[
            (reference["entry_timestamp"] >= pd.Timestamp(era_start, tz=reference["entry_timestamp"].dt.tz))
            & (reference["entry_timestamp"] <= pd.Timestamp(era_end, tz=reference["entry_timestamp"].dt.tz))
        ]
        if era.empty:
            continue
        sample = era.head(trades_per_window)
        window_id = f"{era_name}_SAMPLE"
        for _, row in sample.iterrows():
            rows.append(
                {
                    "window_id": window_id,
                    "era": era_name,
                    "start": era_start,
                    "end": era_end,
                    "trade_id": int(row.trade_id),
                    "direction": row.direction,
                    "setup_timestamp": row.setup_timestamp,
                    "bos_timestamp": row.bos_timestamp,
                    "confirm_timestamp": row.confirm_timestamp,
                    "entry_timestamp": row.entry_timestamp,
                    "entry_price": row.entry_price,
                    "stop_price": row.stop_price,
                    "target_price": row.target_price,
                    "exit_timestamp": row.exit_timestamp,
                    "exit_reason": row.exit_reason,
                }
            )

    recent = reference.tail(trades_per_window)
    for _, row in recent.iterrows():
        rows.append(
            {
                "window_id": "RECENT_SAMPLE",
                "era": "RECENT",
                "start": recent["entry_timestamp"].min(),
                "end": recent["entry_timestamp"].max(),
                "trade_id": int(row.trade_id),
                "direction": row.direction,
                "setup_timestamp": row.setup_timestamp,
                "bos_timestamp": row.bos_timestamp,
                "confirm_timestamp": row.confirm_timestamp,
                "entry_timestamp": row.entry_timestamp,
                "entry_price": row.entry_price,
                "stop_price": row.stop_price,
                "target_price": row.target_price,
                "exit_timestamp": row.exit_timestamp,
                "exit_reason": row.exit_reason,
            }
        )
    return pd.DataFrame(rows)
