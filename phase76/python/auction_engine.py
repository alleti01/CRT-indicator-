"""Strictly causal auction feature engine — incremental, prefix-safe."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from .config import PROFILE_BIN_SIZE, PROFILE_TYPE
from .data_loader import add_atr, to_et
from .profile import hvn_lvn_bins, poc_vah_val_from_hist, price_in_bins
from .sessions import DevelopingSession, OvernightTracker, SessionSnapshot, is_rth, rth_session_date


def causal_rolling_extreme(series: pd.Series, window: int, *, kind: str) -> pd.Series:
    """Causal rolling high/low — uses only past bars including current."""
    if kind == "high":
        return series.rolling(window, min_periods=1).max()
    return series.rolling(window, min_periods=1).min()


def build_auction_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bar-by-bar auction features. Only information with known_at <= bar timestamp.

    Profile type: BAR_APPROX_PROFILE (volume uniformly distributed across bar range).
    """
    df = add_atr(df)
    df = to_et(df)
    n = len(df)
    cols: dict[str, list[Any]] = {
        "in_rth": [],
        "session_date": [],
        "prior_high": [],
        "prior_low": [],
        "prior_close": [],
        "prior_vwap": [],
        "prior_poc": [],
        "prior_vah": [],
        "prior_val": [],
        "prior_value_width": [],
        "dev_high": [],
        "dev_low": [],
        "dev_close": [],
        "dev_vwap": [],
        "dev_poc": [],
        "dev_vah": [],
        "dev_val": [],
        "dev_value_width": [],
        "dist_vwap": [],
        "dist_poc": [],
        "dist_vah": [],
        "dist_val": [],
        "overnight_high": [],
        "overnight_low": [],
        "or_high": [],
        "or_low": [],
        "roll_high_5": [],
        "roll_low_5": [],
        "roll_high_10": [],
        "roll_low_10": [],
        "roll_high_20": [],
        "roll_low_20": [],
        "roll_high_30": [],
        "roll_low_30": [],
        "in_hvn": [],
        "in_lvn": [],
        "profile_type": [],
    }

    prior: SessionSnapshot | None = None
    developing: DevelopingSession | None = None
    last_session_date = None
    overnight = OvernightTracker()

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    opens = df["open"].values
    vols = df["volume"].astype(float).values
    ts_ets = df["ts_et"]

    roll_h5 = causal_rolling_extreme(df["high"], 5, kind="high").values
    roll_l5 = causal_rolling_extreme(df["low"], 5, kind="low").values
    roll_h10 = causal_rolling_extreme(df["high"], 10, kind="high").values
    roll_l10 = causal_rolling_extreme(df["low"], 10, kind="low").values
    roll_h20 = causal_rolling_extreme(df["high"], 20, kind="high").values
    roll_l20 = causal_rolling_extreme(df["low"], 20, kind="low").values
    roll_h30 = causal_rolling_extreme(df["high"], 30, kind="high").values
    roll_l30 = causal_rolling_extreme(df["low"], 30, kind="low").values

    for i in range(n):
        ts_et = ts_ets.iloc[i]
        o, h, l, c, v = opens[i], highs[i], lows[i], closes[i], vols[i]
        in_r = is_rth(ts_et)
        sess_d = rth_session_date(ts_et)

        on_hi, on_lo = overnight.update(ts_et, h, l)

        # finalize prior session when RTH date rolls
        if sess_d is not None and last_session_date is not None and sess_d != last_session_date and developing is not None:
            prior = developing.to_snapshot(PROFILE_TYPE)
        if sess_d is not None and (developing is None or developing.session_date != sess_d):
            developing = DevelopingSession(session_date=sess_d)
        if sess_d is not None:
            last_session_date = sess_d
            developing.update_bar(o, h, l, c, v, ts_et, bin_size=PROFILE_BIN_SIZE)

        dev_poc = dev_vah = dev_val = np.nan
        dev_vwap = np.nan
        in_hvn = in_lvn = False
        if developing is not None and in_r:
            dev_poc, dev_vah, dev_val = poc_vah_val_from_hist(developing.histogram)
            dev_vwap = developing.vwap
            hvn_bins, lvn_bins = hvn_lvn_bins(developing.histogram, hvn_pct=0.80, lvn_pct=0.20)
            in_hvn = price_in_bins(c, hvn_bins, PROFILE_BIN_SIZE)
            in_lvn = price_in_bins(c, lvn_bins, PROFILE_BIN_SIZE)

        def _prior(field: str) -> float:
            if prior is None:
                return np.nan
            return getattr(prior, field)

        cols["in_rth"].append(in_r)
        cols["session_date"].append(str(sess_d) if sess_d else "")
        cols["prior_high"].append(_prior("high"))
        cols["prior_low"].append(_prior("low"))
        cols["prior_close"].append(_prior("close"))
        cols["prior_vwap"].append(_prior("vwap"))
        cols["prior_poc"].append(_prior("poc"))
        cols["prior_vah"].append(_prior("vah"))
        cols["prior_val"].append(_prior("val"))
        cols["prior_value_width"].append(_prior("value_width"))
        cols["dev_high"].append(developing.high if developing and in_r else np.nan)
        cols["dev_low"].append(developing.low if developing and in_r else np.nan)
        cols["dev_close"].append(developing.close if developing and in_r else np.nan)
        cols["dev_vwap"].append(dev_vwap if in_r else np.nan)
        cols["dev_poc"].append(dev_poc if in_r else np.nan)
        cols["dev_vah"].append(dev_vah if in_r else np.nan)
        cols["dev_val"].append(dev_val if in_r else np.nan)
        cols["dev_value_width"].append(
            (dev_vah - dev_val) if in_r and not (np.isnan(dev_vah) or np.isnan(dev_val)) else np.nan
        )
        cols["dist_vwap"].append(c - dev_vwap if in_r and not np.isnan(dev_vwap) else np.nan)
        cols["dist_poc"].append(c - dev_poc if in_r and not np.isnan(dev_poc) else np.nan)
        cols["dist_vah"].append(c - dev_vah if in_r and not np.isnan(dev_vah) else np.nan)
        cols["dist_val"].append(c - dev_val if in_r and not np.isnan(dev_val) else np.nan)
        cols["overnight_high"].append(on_hi)
        cols["overnight_low"].append(on_lo)
        cols["or_high"].append(developing.or_high if developing and in_r else np.nan)
        cols["or_low"].append(developing.or_low if developing and in_r else np.nan)
        cols["roll_high_5"].append(roll_h5[i])
        cols["roll_low_5"].append(roll_l5[i])
        cols["roll_high_10"].append(roll_h10[i])
        cols["roll_low_10"].append(roll_l10[i])
        cols["roll_high_20"].append(roll_h20[i])
        cols["roll_low_20"].append(roll_l20[i])
        cols["roll_high_30"].append(roll_h30[i])
        cols["roll_low_30"].append(roll_l30[i])
        cols["in_hvn"].append(in_hvn)
        cols["in_lvn"].append(in_lvn)
        cols["profile_type"].append(PROFILE_TYPE)

    feat = pd.DataFrame(cols, index=df.index)
    out = pd.concat([df, feat], axis=1)
    return out


def snapshot_prior(session: DevelopingSession) -> dict:
    return asdict(session.to_snapshot(PROFILE_TYPE))
