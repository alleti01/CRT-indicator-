"""Build master entry-quality dataset from frozen CRT trades."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig
from phase16.data_loader import load_ohlcv_csv
from phase16.indicators import add_base_indicators
from phase17.analysis_core import build_trade_features, prepare_market_features, read_trades
from phase20.session_levels import prepare_session_liquidity_frame

from .config import BASELINE_TRADE_SOURCES, NQ_DATA_PATHS, ROOT


def load_unified_market(config: FrozenConfig = FrozenConfig()) -> pd.DataFrame:
    frames = [load_ohlcv_csv(path, exchange_timezone=config.exchange_timezone) for path in NQ_DATA_PATHS]
    combined = pd.concat(frames).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    return add_base_indicators(combined, config)


def load_baseline_trades() -> pd.DataFrame:
    frames = []
    for rel, label in BASELINE_TRADE_SOURCES:
        path = ROOT / rel
        trades = read_trades(path)
        trades["source_window"] = label
        frames.append(trades)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("entry_timestamp", kind="stable").reset_index(drop=True)
    return combined


def _first_passage_labels(
    direction: str,
    entry: float,
    risk: float,
    highs: np.ndarray,
    lows: np.ndarray,
) -> Dict[str, object]:
    if risk <= 0 or len(highs) == 0:
        return {
            "mfe_r": np.nan,
            "mae_r": np.nan,
            "bars_to_mfe": np.nan,
            "bars_to_mae": np.nan,
            "good_entry": False,
            "strong_entry": False,
            "bad_entry": False,
            "very_bad_entry": False,
        }
    mfe_r = 0.0
    mae_r = 0.0
    bars_to_mfe = np.nan
    bars_to_mae = np.nan
    good = strong = bad = very_bad = False
    for i, (hi, lo) in enumerate(zip(highs, lows), start=1):
        if direction == "Long":
            bar_mfe = (hi - entry) / risk
            bar_mae = (entry - lo) / risk
        else:
            bar_mfe = (entry - lo) / risk
            bar_mae = (hi - entry) / risk
        if bar_mfe > mfe_r:
            mfe_r = bar_mfe
            bars_to_mfe = i
        if bar_mae > mae_r:
            mae_r = bar_mae
            bars_to_mae = i
        if not good and not bad:
            hit_good_05 = bar_mfe >= 0.5
            hit_bad_05 = bar_mae >= 0.5
            hit_good_10 = bar_mfe >= 1.0
            hit_bad_10 = bar_mae >= 1.0
            if hit_bad_05 and not hit_good_05:
                bad = True
            elif hit_good_05 and not hit_bad_05:
                good = True
            elif hit_bad_05 and hit_good_05:
                bad = True
            if not strong and hit_good_10 and bar_mae < 0.5:
                strong = True
            if not very_bad and hit_bad_10 and bar_mfe < 0.5:
                very_bad = True
    return {
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "bars_to_mfe": bars_to_mfe,
        "bars_to_mae": bars_to_mae,
        "good_entry": good,
        "strong_entry": strong and not bad,
        "bad_entry": bad,
        "very_bad_entry": very_bad,
    }


def attach_path_geometry(trades: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    idx = market.index
    pos_map = {ts: i for i, ts in enumerate(idx)}
    rows = []
    for trade in trades.itertuples(index=False):
        entry_ts = trade.entry_timestamp
        exit_ts = trade.exit_timestamp
        if entry_ts not in pos_map:
            rows.append({k: np.nan for k in ("mfe_r", "mae_r", "bars_to_mfe", "bars_to_mae", "good_entry", "strong_entry", "bad_entry", "very_bad_entry", "bars_in_trade")})
            rows[-1].update({"good_entry": False, "strong_entry": False, "bad_entry": False, "very_bad_entry": False})
            continue
        start = pos_map[entry_ts] + 1
        end = pos_map.get(exit_ts, start)
        if end < start:
            end = start
        highs = market["high"].to_numpy()[start : end + 1]
        lows = market["low"].to_numpy()[start : end + 1]
        risk = abs(float(trade.entry_price) - float(trade.stop_price))
        labels = _first_passage_labels(str(trade.direction), float(trade.entry_price), risk, highs, lows)
        labels["bars_in_trade"] = max(0, end - pos_map[entry_ts])
        rows.append(labels)
    return pd.concat([trades.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def attach_extended_features(trades: pd.DataFrame, market: pd.DataFrame, liquidity: pd.DataFrame) -> pd.DataFrame:
    working = trades.copy().reset_index(drop=True)
    entry_ts = pd.DatetimeIndex(working["entry_timestamp"])
    bar = market.reindex(entry_ts)
    liq = liquidity.reindex(entry_ts)

    def _col(series):
        values = series.to_numpy() if hasattr(series, "to_numpy") else np.asarray(series)
        return pd.Series(values, index=working.index)

    working["range_atr"] = _col((bar["high"] - bar["low"]) / bar["atr"])
    body = (bar["close"] - bar["open"]).abs()
    rng = (bar["high"] - bar["low"]).replace(0, np.nan)
    working["body_range_ratio"] = _col(body / rng)
    bullish = working["direction"] == "Long"
    working["close_location"] = _col(
        np.where(bullish, (bar["close"] - bar["low"]) / rng, (bar["high"] - bar["close"]) / rng)
    )
    working["upper_wick_ratio"] = _col((bar["high"] - np.maximum(bar["open"], bar["close"])) / rng)
    working["lower_wick_ratio"] = _col((np.minimum(bar["open"], bar["close"]) - bar["low"]) / rng)
    working["momentum_3_atr"] = _col((bar["close"] - market["close"].shift(3).reindex(entry_ts)) / bar["atr"])
    accel = bar["close"].diff().abs() / bar["close"].diff().abs().shift(1).rolling(3).mean()
    working["accel_3"] = _col(accel)

    atr6 = market["atr"].ewm(alpha=1 / 6, adjust=False).mean()
    atr72 = market["atr"].ewm(alpha=1 / 72, adjust=False).mean()
    working["atr_ratio_6_72"] = _col((atr6 / atr72).reindex(entry_ts))
    body_atr = body / bar["atr"]
    working["body_atr_pct"] = _col(body_atr.rank(pct=True))

    minute = entry_ts.hour * 60 + entry_ts.minute
    working["minutes_from_rth_open"] = minute - (9 * 60 + 30)
    working["day_of_week"] = entry_ts.dayofweek
    working["volatility_regime_code"] = working["volatility_regime"].map({"Low": 0, "Medium": 1, "High": 2}).fillna(1)
    working["trend_aligned"] = np.where(
        working["direction"] == "Long",
        working["htf_regime"] > 0,
        working["htf_regime"] < 0,
    ).astype(int)

    for name, col in (("pdh", "pdh"), ("pdl", "pdl"), ("onh", "onh"), ("onl", "onl")):
        if col in liq.columns:
            dist = (working["entry_price"].to_numpy() - liq[col].to_numpy())
            working[f"dist_{name}_atr"] = np.abs(dist) / working["atr"].to_numpy()

    working["model_code"] = working["model"].map({"Control": 0, "BOS": 1, "Retest": 2, "Confirm": 3}).fillna(-1)
    working["direction_code"] = (working["direction"] == "Long").astype(int)
    working["win"] = (working["result_R"] > 0).astype(int)
    working["large_winner"] = (working["result_R"] >= 1.0).astype(int)
    working["large_loser"] = (working["result_R"] <= -0.75).astype(int)
    return working


def build_master_dataset() -> Tuple[pd.DataFrame, pd.DataFrame]:
    config = FrozenConfig()
    trades = load_baseline_trades()
    market_path = ROOT / "phase16/data/processed/nq_5m.csv"
    market_features = prepare_market_features(market_path)
    unified = load_unified_market(config)
    base_features = build_trade_features(trades, market_features)
    liquidity = prepare_session_liquidity_frame(unified, config)
    dataset = attach_extended_features(base_features, unified, liquidity)
    dataset = attach_path_geometry(dataset, unified)
    return dataset, trades
