"""Causal location interaction detection — non-directional, episode-deduplicated."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import RTH_OPEN, TIMEZONE
from .location_config import DISTANCE_BANDS_ATR, NON_LEVEL_EXCLUSION_ATR
from .location_levels import ALL_LEVELS, LevelSpec


def _bar_distance_atr(high: float, low: float, level: float, atr: float) -> float:
    if np.isnan(level) or np.isnan(atr) or atr <= 0:
        return np.nan
    if low <= level <= high:
        return 0.0
    return min(abs(high - level), abs(low - level)) / atr


def add_context_columns(feat: pd.DataFrame) -> pd.DataFrame:
    """Covariates for matching and event records — causal only."""
    out = feat.copy()
    c = out["close"].values

    out["range_5m"] = out["high"].rolling(5, min_periods=1).max() - out["low"].rolling(5, min_periods=1).min()
    out["range_15m"] = out["high"].rolling(15, min_periods=1).max() - out["low"].rolling(15, min_periods=1).min()
    out["range_30m"] = out["high"].rolling(30, min_periods=1).max() - out["low"].rolling(30, min_periods=1).min()
    out["disp_5m"] = c - np.roll(c, 5)
    out["disp_15m"] = c - np.roll(c, 15)
    out["disp_30m"] = c - np.roll(c, 30)
    out.loc[out.index[:30], ["disp_5m", "disp_15m", "disp_30m"]] = np.nan

    # Session open reference (first RTH bar per session_date)
    sess = out["session_date"].astype(str)
    out["session_open"] = np.nan
    for sd in sess.unique():
        if not sd or sd == "nan":
            continue
        mask = (sess == sd) & out["in_rth"]
        if not mask.any():
            continue
        first_idx = out.index[mask][0]
        out.loc[mask, "session_open"] = out.loc[first_idx, "open"]
    out["dist_from_session_open"] = out["close"] - out["session_open"]

    dev_h = out["dev_high"].values
    dev_l = out["dev_low"].values
    width = dev_h - dev_l
    out["session_range_pct"] = np.where(width > 0, (c - dev_l) / width, np.nan)

    # Time of day: minutes from RTH open
    open_min = RTH_OPEN[0] * 60 + RTH_OPEN[1]
    tod = out["ts_et"].dt.hour * 60 + out["ts_et"].dt.minute - open_min
    out["time_of_day_min"] = tod.where(out["in_rth"], np.nan)
    out["year"] = out["ts_et"].dt.year
    out["month"] = out["ts_et"].dt.month

    # Carry overnight H/L into RTH (fixed at open — causal)
    latched_hi = latched_lo = np.nan
    on_hi_sess, on_lo_sess = [], []
    in_rth_arr = out["in_rth"].fillna(False).values
    raw_on_hi = out["overnight_high"].values
    raw_on_lo = out["overnight_low"].values
    for i in range(len(out)):
        if not np.isnan(raw_on_hi[i]):
            latched_hi, latched_lo = raw_on_hi[i], raw_on_lo[i]
        if in_rth_arr[i] and not np.isnan(latched_hi):
            on_hi_sess.append(latched_hi)
            on_lo_sess.append(latched_lo)
        else:
            on_hi_sess.append(np.nan)
            on_lo_sess.append(np.nan)
    out["overnight_high_session"] = on_hi_sess
    out["overnight_low_session"] = on_lo_sess
    return out


def _auction_level_prices(row: pd.Series) -> dict[str, float]:
    prices: dict[str, float] = {}
    for spec in ALL_LEVELS:
        if spec.category != "auction" or spec.column is None:
            continue
        prices[spec.code] = row.get(spec.column, np.nan)
    return prices


def is_non_level_bar(row: pd.Series, *, exclusion_atr: float = NON_LEVEL_EXCLUSION_ATR) -> bool:
    """True if bar is not near any auction price level (for matched pool)."""
    if not row.get("in_rth", False):
        return False
    atr = row.get("atr")
    if pd.isna(atr) or atr <= 0:
        return False
    h, l = row["high"], row["low"]
    for code, level in _auction_level_prices(row).items():
        if pd.isna(level):
            continue
        if _bar_distance_atr(h, l, float(level), float(atr)) <= exclusion_atr:
            return False
    if row.get("in_hvn") or row.get("in_lvn"):
        return False
    return True


def detect_level_interactions(
    feat: pd.DataFrame,
    spec: LevelSpec,
    *,
    band_atr: float,
) -> pd.DataFrame:
    """
    Detect episode-start interactions for one level type at one distance band.
    Non-directional: no LONG/SHORT assignment.
    """
    mask_rth = feat["in_rth"].fillna(False)
    sub = feat.loc[mask_rth]
    if sub.empty:
        return pd.DataFrame()

    highs = sub["high"].values
    lows = sub["low"].values
    closes = sub["close"].values
    atrs = sub["atr"].values
    idx = sub.index

    if spec.zone_flag:
        zone = sub[spec.zone_flag].fillna(False).astype(bool).values
        in_zone = zone
        levels = closes.copy()
    else:
        levels = sub[spec.column].values.astype(float)
        in_zone = np.zeros(len(sub), dtype=bool)
        for i in range(len(sub)):
            d = _bar_distance_atr(highs[i], lows[i], levels[i], atrs[i])
            in_zone[i] = not np.isnan(d) and d <= band_atr

    rows: list[dict] = []
    in_episode = False
    for i in range(len(sub)):
        if not in_zone[i] or np.isnan(atrs[i]) or atrs[i] <= 0:
            in_episode = False
            continue
        if in_episode:
            continue
        in_episode = True
        ts = idx[i]
        row = sub.iloc[i]
        lp = float(levels[i]) if not spec.zone_flag else float(closes[i])
        dist = _bar_distance_atr(highs[i], lows[i], lp, atrs[i])
        rows.append(
            {
                "interaction_ts": ts,
                "level_type": spec.code,
                "level_category": spec.category if spec.category != "hvn_lvn" else "auction",
                "level_price": lp,
                "price": float(closes[i]),
                "atr": float(atrs[i]),
                "distance_atr": float(dist) if not np.isnan(dist) else 0.0,
                "band_atr": band_atr,
                "time_of_day_min": row.get("time_of_day_min"),
                "session_date": row.get("session_date"),
                "session_progress": row.get("session_range_pct"),
                "range_5m": row.get("range_5m"),
                "range_15m": row.get("range_15m"),
                "range_30m": row.get("range_30m"),
                "disp_5m": row.get("disp_5m"),
                "disp_15m": row.get("disp_15m"),
                "disp_30m": row.get("disp_30m"),
                "dist_from_session_open": row.get("dist_from_session_open"),
                "session_range_pct": row.get("session_range_pct"),
                "volume": row.get("volume"),
                "auction_state": row.get("auction_state"),
                "year": row.get("year"),
                "month": row.get("month"),
            }
        )
    return pd.DataFrame(rows)


def detect_all_interactions(feat: pd.DataFrame, *, bands: tuple[float, ...] = DISTANCE_BANDS_ATR) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for spec in ALL_LEVELS:
        for band in bands:
            df = detect_level_interactions(feat, spec, band_atr=band)
            if not df.empty:
                parts.append(df)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def build_non_level_pool(feat: pd.DataFrame) -> pd.DataFrame:
    """All RTH bars eligible as matched non-level controls."""
    mask = feat.apply(is_non_level_bar, axis=1)
    pool = feat.loc[mask].copy()
    pool["interaction_ts"] = pool.index
    pool["level_type"] = "MATCHED_NON_LEVEL"
    pool["level_category"] = "control"
    pool["level_price"] = np.nan
    pool["price"] = pool["close"]
    pool["distance_atr"] = np.nan
    pool["band_atr"] = np.nan
    return pool
