"""Aggregate Databento trades to causal 5-minute order-flow features."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig
from phase16.data_loader import load_ohlcv_csv
from phase16.indicators import add_base_indicators

from .config import FLOW_WINDOWS_SECONDS, NQ_5M_PATHS, PILOT_END, PILOT_START


def load_trades(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True)
    tz = FrozenConfig().exchange_timezone
    df["ts_local"] = df["timestamp"].dt.tz_convert(tz)
    df["buy"] = (df["side"] == "B").astype(int) * df["size"]
    df["sell"] = (df["side"] == "A").astype(int) * df["size"]
    return df


def load_pilot_5m() -> pd.DataFrame:
    config = FrozenConfig()
    frames = [load_ohlcv_csv(p, exchange_timezone=config.exchange_timezone) for p in NQ_5M_PATHS]
    market = pd.concat(frames).sort_index()
    market = market[~market.index.duplicated(keep="last")]
    market = add_base_indicators(market, config)
    tz = config.exchange_timezone
    start = pd.Timestamp(PILOT_START, tz=tz)
    end = pd.Timestamp(PILOT_END, tz=tz)
    return market.loc[(market.index >= start) & (market.index < end)]


def _bar_end(ts: pd.Series, bar_index: pd.DatetimeIndex) -> pd.Series:
    ts = pd.DatetimeIndex(ts)
    if ts.tz is None and bar_index.tz is not None:
        ts = ts.tz_localize(bar_index.tz)
    elif ts.tz is not None and bar_index.tz is None:
        bar_index = bar_index.tz_localize(ts.tz)
    pos = bar_index.searchsorted(ts, side="right") - 1
    pos = np.clip(pos, 0, len(bar_index) - 1)
    return pd.Series(bar_index[pos], index=ts)


def aggregate_flow_to_5m(trades: pd.DataFrame, bars: pd.DatetimeIndex) -> pd.DataFrame:
    trades = trades.copy()
    trades["bar_end"] = _bar_end(trades["ts_local"], bars)
    g = trades.groupby("bar_end", sort=True)
    base = pd.DataFrame(index=bars)
    base["trade_count"] = g.size().reindex(bars).fillna(0)
    base["buy_vol"] = g["buy"].sum().reindex(bars).fillna(0)
    base["sell_vol"] = g["sell"].sum().reindex(bars).fillna(0)
    base["total_vol"] = base["buy_vol"] + base["sell_vol"]
    base["delta"] = base["buy_vol"] - base["sell_vol"]
    base["delta_norm"] = base["delta"] / base["total_vol"].replace(0, np.nan)
    base["avg_trade_size"] = base["total_vol"] / base["trade_count"].replace(0, np.nan)
    span = g["ts_local"].apply(lambda s: max((s.max() - s.min()).total_seconds(), 1.0)).reindex(bars).fillna(300.0)
    base["trades_per_sec"] = base["trade_count"] / span
    base["vol_per_sec"] = base["total_vol"] / span
    large = trades.groupby("bar_end")["size"].quantile(0.9)
    trades = trades.merge(large.rename("large_thresh"), left_on="bar_end", right_index=True, how="left")
    base["large_trade_pct"] = trades.loc[trades["size"] >= trades["large_thresh"]].groupby("bar_end").size().reindex(bars).fillna(0) / base["trade_count"].replace(0, np.nan)

    # causal rolling windows ending at each bar close
    trades_sorted = trades.sort_values("ts_local")
    ts_vals = trades_sorted["ts_local"].astype("int64").to_numpy()
    bar_vals = bars.astype("int64").to_numpy()
    buy = trades_sorted["buy"].to_numpy()
    sell = trades_sorted["sell"].to_numpy()
    for secs in FLOW_WINDOWS_SECONDS:
        delta_w = np.zeros(len(bars))
        norm_w = np.full(len(bars), np.nan)
        tps_w = np.zeros(len(bars))
        offset = int(secs * 1e9)
        for i, bar_ns in enumerate(bar_vals):
            lo = np.searchsorted(ts_vals, bar_ns - offset, side="right")
            hi = np.searchsorted(ts_vals, bar_ns, side="right")
            if hi <= lo:
                continue
            b = buy[lo:hi].sum()
            s = sell[lo:hi].sum()
            delta_w[i] = b - s
            tv = b + s
            norm_w[i] = delta_w[i] / tv if tv else np.nan
            tps_w[i] = (hi - lo) / secs
        base[f"delta_{secs}s"] = delta_w
        base[f"delta_norm_{secs}s"] = norm_w
        base[f"trades_per_sec_{secs}s"] = tps_w

    base["cum_delta_5m"] = base["delta"].cumsum()
    base["delta_accel"] = base["delta"] - base["delta"].shift(1)
    return base


def add_price_response(flow: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    out = flow.copy()
    atr = market["atr"].replace(0, np.nan)
    out["price_change_atr"] = market["close"].diff() / atr
    out["delta_price_response"] = out["delta"] / atr
    out["flow_divergence"] = out["delta_norm"] - out["price_change_atr"]
    return out


def build_ohlcv_control(market: pd.DataFrame) -> pd.DataFrame:
    atr = market["atr"].replace(0, np.nan)
    rng = (market["high"] - market["low"]).replace(0, np.nan)
    body = (market["close"] - market["open"]).abs()
    out = pd.DataFrame(index=market.index)
    out["body_atr"] = body / atr
    out["range_atr"] = rng / atr
    out["close_location"] = (market["close"] - market["low"]) / rng
    out["ret_3_atr"] = (market["close"] - market["close"].shift(3)) / atr
    out["ret_6_atr"] = (market["close"] - market["close"].shift(6)) / atr
    out["volume_z"] = (market["volume"] - market["volume"].shift(1).rolling(288, min_periods=72).mean()) / market["volume"].shift(1).rolling(288, min_periods=72).std()
    out["minute_of_day"] = market.index.hour * 60 + market.index.minute
    out["day_of_week"] = market.index.dayofweek
    return out
