"""Causal 1-minute OHLCV feature library. No future bars."""
from __future__ import annotations

import numpy as np
import pandas as pd

MA_LENS = (5, 8, 9, 10, 13, 14, 20, 21, 34, 50, 100, 200)
RSI_LENS = (7, 9, 14, 21)
ROLL_LENS = (5, 10, 15, 20, 30, 50)


def _rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_g = gain.ewm(alpha=1.0 / length, adjust=False).mean()
    avg_l = loss.ewm(alpha=1.0 / length, adjust=False).mean()
    rs = avg_g / avg_l.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def add_causal_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    o, h, l, c = out["open"], out["high"], out["low"], out["close"]
    vol = out["volume"].astype(float)
    rng = (h - l).replace(0.0, np.nan)
    body = c - o
    upper = h - np.maximum(c, o)
    lower = np.minimum(c, o) - l
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14, min_periods=14).mean()

    out["ret_1"] = c.pct_change(1)
    out["log_ret_1"] = np.log(c / prev_c)
    out["close_open"] = body
    out["close_close_1"] = c - prev_c
    for n in (2, 3, 5, 10, 20):
        out[f"ret_{n}"] = c.pct_change(n)
    out["range"] = h - l
    out["body"] = body
    out["body_frac"] = body / rng
    out["upper_wick"] = upper
    out["lower_wick"] = lower
    out["upper_wick_frac"] = upper / rng
    out["lower_wick_frac"] = lower / rng
    out["close_loc"] = (c - l) / rng
    out["bullish"] = (c > o).astype(int)
    out["bearish"] = (c < o).astype(int)
    out["inside"] = ((h <= h.shift(1)) & (l >= l.shift(1))).astype(int)
    out["outside"] = ((h >= h.shift(1)) & (l <= l.shift(1))).astype(int)
    out["engulf_bull"] = ((c > o) & (o <= l.shift(1)) & (c >= h.shift(1))).astype(int)
    out["engulf_bear"] = ((c < o) & (o >= h.shift(1)) & (c <= l.shift(1))).astype(int)
    consec = (np.sign(body) == np.sign(body.shift(1))) & (body != 0)
    run = consec.groupby((~consec).cumsum()).cumcount() + 1
    out["consec_dir"] = np.where(body > 0, run, np.where(body < 0, -run, 0))
    out["tr"] = tr
    out["atr14"] = atr14
    out["body_atr"] = body / atr14
    out["upper_atr"] = upper / atr14
    out["lower_atr"] = lower / atr14
    out["vol_expand"] = tr / tr.rolling(20, min_periods=20).mean()
    out["stdev20"] = c.rolling(20, min_periods=20).std()

    for n in MA_LENS:
        sma = c.rolling(n, min_periods=n).mean()
        ema = c.ewm(span=n, adjust=False).mean()
        out[f"sma_{n}"] = sma
        out[f"ema_{n}"] = ema
        out[f"dist_sma_{n}"] = (c - sma) / atr14
        out[f"dist_ema_{n}"] = (c - ema) / atr14
        out[f"ema_slope_{n}"] = ema.diff()
        out[f"cross_ema_{n}_up"] = ((c > ema) & (prev_c <= ema.shift(1))).astype(int)
        out[f"cross_ema_{n}_dn"] = ((c < ema) & (prev_c >= ema.shift(1))).astype(int)

    out["ema8_gt_ema21"] = (out["ema_8"] > out["ema_21"]).astype(int)
    out["ema8_cross_21_up"] = ((out["ema_8"] > out["ema_21"]) & (out["ema_8"].shift(1) <= out["ema_21"].shift(1))).astype(int)
    out["ema8_cross_21_dn"] = ((out["ema_8"] < out["ema_21"]) & (out["ema_8"].shift(1) >= out["ema_21"].shift(1))).astype(int)

    for n in RSI_LENS:
        out[f"rsi_{n}"] = _rsi(c, n)
        out[f"rsi_{n}_reclaim_30"] = ((out[f"rsi_{n}"] >= 30) & (out[f"rsi_{n}"].shift(1) < 30)).astype(int)
        out[f"rsi_{n}_lose_70"] = ((out[f"rsi_{n}"] <= 70) & (out[f"rsi_{n}"].shift(1) > 70)).astype(int)

    for n in ROLL_LENS:
        rh = h.rolling(n, min_periods=n).max()
        rl = l.rolling(n, min_periods=n).min()
        out[f"roll_high_{n}"] = rh
        out[f"roll_low_{n}"] = rl
        out[f"dist_high_{n}"] = (rh - c) / atr14
        out[f"dist_low_{n}"] = (c - rl) / atr14
        out[f"close_through_high_{n}"] = ((c > rh.shift(1)) & (prev_c <= rh.shift(1))).astype(int)
        out[f"close_through_low_{n}"] = ((c < rl.shift(1)) & (prev_c >= rl.shift(1))).astype(int)
        out[f"wick_through_high_{n}"] = ((h > rh.shift(1)) & (c <= rh.shift(1))).astype(int)
        out[f"wick_through_low_{n}"] = ((l < rl.shift(1)) & (c >= rl.shift(1))).astype(int)
        out[f"near_low_{n}"] = ((c - rl) <= 0.25 * atr14).astype(int)
        out[f"near_high_{n}"] = ((rh - c) <= 0.25 * atr14).astype(int)

    path = (h - l).rolling(10, min_periods=10).sum()
    net = (c - c.shift(10)).abs()
    out["efficiency_10"] = net / path.replace(0.0, np.nan)
    out["overlap_1"] = (np.minimum(h, h.shift(1)) - np.maximum(l, l.shift(1))).clip(lower=0) / rng

    vma = vol.rolling(20, min_periods=20).mean()
    vstd = vol.rolling(20, min_periods=20).std()
    out["rel_volume"] = vol / vma.replace(0.0, np.nan)
    out["vol_z"] = (vol - vma) / vstd.replace(0.0, np.nan)
    out["vol_rising"] = (vol > vol.shift(1)).astype(int)

    idx = out.index
    if getattr(idx, "tz", None) is not None:
        et = idx.tz_convert("America/New_York")
    else:
        et = idx
    minutes = et.hour * 60 + et.minute
    out["rth"] = ((minutes >= 9 * 60 + 30) & (minutes <= 16 * 60)).astype(int)
    out["overnight"] = (1 - out["rth"]).astype(int)
    return out


def known_at_htf_close(index: pd.DatetimeIndex, minutes: int) -> pd.Series:
    """Timestamp when the containing HTF bar is known (at its close). Causal."""
    if getattr(index, "tz", None) is None:
        raise ValueError("index must be timezone-aware")
    floor = index.floor(f"{minutes}min")
    known = floor + pd.Timedelta(minutes=minutes)
    return pd.Series(known, index=index, name=f"known_at_{minutes}m")
