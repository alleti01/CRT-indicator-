"""Compact causal 15m entry architecture families for Phase 31."""

from __future__ import annotations

from typing import Callable, Dict, List, Tuple

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig
from phase16.indicators import is_in_session
from phase16.resample import cme_session_date
from phase16.sequential_bos import BosDefinition, SequentialBosConfig, run_sequential_bos_backtest
from phase28.strategies import collect_strategy_trades, run_crt_v2

from .config import COMMON_END, COMMON_START, RTH_SESSION, frozen_config_15m
from .dedupe import dedupe_signals, filter_rth_signals

ARCHITECTURES: Tuple[str, ...] = (
    "RETEST_GATED",
    "BOS_ONLY",
    "SEQUENTIAL_BOS_CONFIRM",
    "CRT_V2_B_LEGACY_EXP6",
    "SWING22_BOS_CLOSE",
    "SWING22_BOS_RETEST",
    "SWEEP_RECLAIM",
    "MOMENTUM_DISPLACEMENT",
    "RANGE_BREAK_10",
    "FAILED_BREAK_10",
    "IMPULSE_PULLBACK",
)


def _normalize_trades(trades: pd.DataFrame, architecture: str) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    out = trades.copy()
    out["architecture"] = architecture
    out["entry_timestamp"] = pd.to_datetime(out["entry_timestamp"])
    if "bos_timestamp" in out.columns:
        out["bos_timestamp"] = pd.to_datetime(out["bos_timestamp"])
    else:
        out["bos_timestamp"] = out["entry_timestamp"]
    if "signal_id" not in out.columns:
        out["signal_id"] = np.arange(1, len(out) + 1)
    out["event_id"] = out.apply(
        lambda r: f"{architecture}_{r.get('bos_timestamp', r['entry_timestamp'])}_{r['direction']}",
        axis=1,
    )
    return out


def _from_backtest_model(
    market: pd.DataFrame,
    *,
    model: str,
    architecture: str,
    config: FrozenConfig,
) -> pd.DataFrame:
    runs = collect_strategy_trades(
        market, start=COMMON_START, end=COMMON_END, config=config
    )
    key = {
        "Confirm": "RETEST_GATED",
        "BOS": "BOS_ONLY",
    }[model]
    trades = runs[key].trades.copy()
    return _normalize_trades(trades, architecture)


def _sequential_confirm(market: pd.DataFrame, config: FrozenConfig) -> pd.DataFrame:
    seq = SequentialBosConfig(
        bos_definition=BosDefinition.SWING_2_2,
        setup_bos_expiry_bars=3,
    )
    result, _ = run_sequential_bos_backtest(
        market, start=COMMON_START, end=COMMON_END, config=config, seq_config=seq
    )
    trades = result.trades.loc[result.trades["model"] == "Confirm"].copy()
    return _normalize_trades(trades, "SEQUENTIAL_BOS_CONFIRM")


def _crt_v2(market: pd.DataFrame, config: FrozenConfig) -> pd.DataFrame:
    run = run_crt_v2(market, start=COMMON_START, end=COMMON_END, config=config)
    return _normalize_trades(run.trades, "CRT_V2_B_LEGACY_EXP6")


def _swing_pivots(high: np.ndarray, low: np.ndarray, left: int = 2, right: int = 2):
    n = len(high)
    swing_high = np.full(n, np.nan)
    swing_low = np.full(n, np.nan)
    for i in range(left, n - right):
        if high[i] == max(high[i - left : i + right + 1]):
            swing_high[i] = high[i]
        if low[i] == min(low[i - left : i + right + 1]):
            swing_low[i] = low[i]
    return swing_high, swing_low


def _scan_swing22_bos(
    market: pd.DataFrame,
    *,
    architecture: str,
    retest: bool,
    retest_window: int = 8,
    tolerance_atr: float = 0.10,
) -> pd.DataFrame:
    idx = market.index
    high = market["high"].to_numpy(dtype=float)
    low = market["low"].to_numpy(dtype=float)
    close = market["close"].to_numpy(dtype=float)
    atr = market["atr"].to_numpy(dtype=float)
    swing_high, swing_low = _swing_pivots(high, low)
    rows: List[dict] = []
    last_sh = np.nan
    last_sl = np.nan
    pending: List[dict] = []
    for i in range(len(idx)):
        ts = idx[i]
        if not is_in_session(ts, RTH_SESSION):
            continue
        if not np.isnan(swing_high[i]):
            last_sh = swing_high[i]
        if not np.isnan(swing_low[i]):
            last_sl = swing_low[i]
        if np.isnan(last_sh) or np.isnan(last_sl):
            continue
        bos_long = close[i] > last_sh and close[i - 1] <= last_sh if i > 0 else False
        bos_short = close[i] < last_sl and close[i - 1] >= last_sl if i > 0 else False
        if bos_long:
            pending.append(
                {
                    "direction": "Long",
                    "bos_timestamp": ts,
                    "bos_level": float(last_sh),
                    "expires": i + retest_window,
                }
            )
        if bos_short:
            pending.append(
                {
                    "direction": "Short",
                    "bos_timestamp": ts,
                    "bos_level": float(last_sl),
                    "expires": i + retest_window,
                }
            )
        pending = [p for p in pending if p["expires"] >= i]
        if retest:
            for p in list(pending):
                tol = tolerance_atr * float(atr[i])
                if p["direction"] == "Long":
                    touched = low[i] <= p["bos_level"] + tol
                    reclaimed = close[i] > p["bos_level"]
                    if touched and reclaimed and i > idx.get_indexer([p["bos_timestamp"]])[0]:
                        rows.append(
                            {
                                "direction": "Long",
                                "entry_timestamp": ts,
                                "bos_timestamp": p["bos_timestamp"],
                                "event_id": f"{architecture}_{p['bos_timestamp']}_Long",
                            }
                        )
                        pending.remove(p)
                else:
                    touched = high[i] >= p["bos_level"] - tol
                    reclaimed = close[i] < p["bos_level"]
                    if touched and reclaimed and i > idx.get_indexer([p["bos_timestamp"]])[0]:
                        rows.append(
                            {
                                "direction": "Short",
                                "entry_timestamp": ts,
                                "bos_timestamp": p["bos_timestamp"],
                                "event_id": f"{architecture}_{p['bos_timestamp']}_Short",
                            }
                        )
                        pending.remove(p)
        else:
            if bos_long:
                rows.append(
                    {
                        "direction": "Long",
                        "entry_timestamp": ts,
                        "bos_timestamp": ts,
                        "event_id": f"{architecture}_{ts}_Long",
                    }
                )
            if bos_short:
                rows.append(
                    {
                        "direction": "Short",
                        "entry_timestamp": ts,
                        "bos_timestamp": ts,
                        "event_id": f"{architecture}_{ts}_Short",
                    }
                )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["architecture"] = architecture
    df["signal_id"] = np.arange(1, len(df) + 1)
    return df


def _scan_sweep_reclaim(market: pd.DataFrame) -> pd.DataFrame:
    rows: List[dict] = []
    idx = market.index
    for i in range(2, len(idx)):
        ts = idx[i]
        if not is_in_session(ts, RTH_SESSION):
            continue
        prev_h = float(market["high"].iloc[i - 1])
        prev_l = float(market["low"].iloc[i - 1])
        prev_c = float(market["close"].iloc[i - 1])
        h = float(market["high"].iloc[i])
        l = float(market["low"].iloc[i])
        c = float(market["close"].iloc[i])
        swept_high = h > prev_h and c < prev_h and prev_c <= prev_h
        swept_low = l < prev_l and c > prev_l and prev_c >= prev_l
        if swept_high:
            rows.append(
                {
                    "direction": "Short",
                    "entry_timestamp": ts,
                    "bos_timestamp": ts,
                    "event_id": f"SWEEP_RECLAIM_{ts}_Short",
                }
            )
        if swept_low:
            rows.append(
                {
                    "direction": "Long",
                    "entry_timestamp": ts,
                    "bos_timestamp": ts,
                    "event_id": f"SWEEP_RECLAIM_{ts}_Long",
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["architecture"] = "SWEEP_RECLAIM"
    df["signal_id"] = np.arange(1, len(df) + 1)
    return df


def _scan_momentum_displacement(market: pd.DataFrame) -> pd.DataFrame:
    body = (market["close"] - market["open"]).abs()
    avg_body = body.rolling(20, min_periods=20).mean()
    rng = (market["high"] - market["low"]).replace(0, np.nan)
    cl = (market["close"] - market["low"]) / rng
    rows: List[dict] = []
    for i in range(20, len(market)):
        ts = market.index[i]
        if not is_in_session(ts, RTH_SESSION):
            continue
        if body.iloc[i] < 1.5 * avg_body.iloc[i]:
            continue
        if cl.iloc[i] >= 0.80:
            direction = "Long"
        elif cl.iloc[i] <= 0.20:
            direction = "Short"
        else:
            continue
        rows.append(
            {
                "direction": direction,
                "entry_timestamp": ts,
                "bos_timestamp": ts,
                "event_id": f"MOMENTUM_DISPLACEMENT_{ts}_{direction}",
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["architecture"] = "MOMENTUM_DISPLACEMENT"
    df["signal_id"] = np.arange(1, len(df) + 1)
    return df


def _scan_range_break(market: pd.DataFrame, *, failed: bool, lookback: int = 10) -> pd.DataFrame:
    arch = "FAILED_BREAK_10" if failed else "RANGE_BREAK_10"
    rows: List[dict] = []
    for i in range(lookback, len(market)):
        ts = market.index[i]
        if not is_in_session(ts, RTH_SESSION):
            continue
        window = market.iloc[i - lookback : i]
        hi = float(window["high"].max())
        lo = float(window["low"].min())
        h = float(market["high"].iloc[i])
        l = float(market["low"].iloc[i])
        c = float(market["close"].iloc[i])
        if failed:
            if h > hi and c < hi:
                rows.append(
                    {
                        "direction": "Short",
                        "entry_timestamp": ts,
                        "bos_timestamp": ts,
                        "event_id": f"{arch}_{ts}_Short",
                    }
                )
            if l < lo and c > lo:
                rows.append(
                    {
                        "direction": "Long",
                        "entry_timestamp": ts,
                        "bos_timestamp": ts,
                        "event_id": f"{arch}_{ts}_Long",
                    }
                )
        else:
            if c > hi:
                rows.append(
                    {
                        "direction": "Long",
                        "entry_timestamp": ts,
                        "bos_timestamp": ts,
                        "event_id": f"{arch}_{ts}_Long",
                    }
                )
            if c < lo:
                rows.append(
                    {
                        "direction": "Short",
                        "entry_timestamp": ts,
                        "bos_timestamp": ts,
                        "event_id": f"{arch}_{ts}_Short",
                    }
                )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["architecture"] = arch
    df["signal_id"] = np.arange(1, len(df) + 1)
    return df


def _scan_impulse_pullback(market: pd.DataFrame, lookback: int = 6) -> pd.DataFrame:
    rows: List[dict] = []
    for i in range(lookback + 2, len(market)):
        ts = market.index[i]
        if not is_in_session(ts, RTH_SESSION):
            continue
        impulse = market.iloc[i - lookback : i - 1]
        bar = market.iloc[i]
        impulse_up = float(impulse["close"].iloc[-1]) > float(impulse["open"].iloc[0]) + float(
            impulse["atr"].iloc[-1]
        )
        impulse_dn = float(impulse["close"].iloc[-1]) < float(impulse["open"].iloc[0]) - float(
            impulse["atr"].iloc[-1]
        )
        if impulse_up:
            ref = float(impulse["low"].min())
            if float(bar["low"]) <= ref + 0.15 * float(bar["atr"]) and float(bar["close"]) > ref:
                rows.append(
                    {
                        "direction": "Long",
                        "entry_timestamp": ts,
                        "bos_timestamp": market.index[i - 1],
                        "event_id": f"IMPULSE_PULLBACK_{ts}_Long",
                    }
                )
        if impulse_dn:
            ref = float(impulse["high"].max())
            if float(bar["high"]) >= ref - 0.15 * float(bar["atr"]) and float(bar["close"]) < ref:
                rows.append(
                    {
                        "direction": "Short",
                        "entry_timestamp": ts,
                        "bos_timestamp": market.index[i - 1],
                        "event_id": f"IMPULSE_PULLBACK_{ts}_Short",
                    }
                )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["architecture"] = "IMPULSE_PULLBACK"
    df["signal_id"] = np.arange(1, len(df) + 1)
    return df


def build_architecture_signals(
    market: pd.DataFrame,
    *,
    config: FrozenConfig | None = None,
) -> Dict[str, pd.DataFrame]:
    cfg = config or frozen_config_15m()
    builders: Dict[str, Callable[[], pd.DataFrame]] = {
        "RETEST_GATED": lambda: _from_backtest_model(
            market, model="Confirm", architecture="RETEST_GATED", config=cfg
        ),
        "BOS_ONLY": lambda: _from_backtest_model(
            market, model="BOS", architecture="BOS_ONLY", config=cfg
        ),
        "SEQUENTIAL_BOS_CONFIRM": lambda: _sequential_confirm(market, cfg),
        "CRT_V2_B_LEGACY_EXP6": lambda: _crt_v2(market, cfg),
        "SWING22_BOS_CLOSE": lambda: _scan_swing22_bos(
            market, architecture="SWING22_BOS_CLOSE", retest=False
        ),
        "SWING22_BOS_RETEST": lambda: _scan_swing22_bos(
            market, architecture="SWING22_BOS_RETEST", retest=True
        ),
        "SWEEP_RECLAIM": lambda: _scan_sweep_reclaim(market),
        "MOMENTUM_DISPLACEMENT": lambda: _scan_momentum_displacement(market),
        "RANGE_BREAK_10": lambda: _scan_range_break(market, failed=False),
        "FAILED_BREAK_10": lambda: _scan_range_break(market, failed=True),
        "IMPULSE_PULLBACK": lambda: _scan_impulse_pullback(market),
    }
    out: Dict[str, pd.DataFrame] = {}
    for name, fn in builders.items():
        raw = fn()
        raw = filter_rth_signals(raw)
        out[name] = dedupe_signals(raw, market, max_hold_bars=6)
    return out
