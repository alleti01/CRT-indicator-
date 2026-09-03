"""Extended market data loader for Phase58J last-week forward replay."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from phase16.data_loader import load_ohlcv_csv
from phase16.indicators import add_base_indicators, pine_sma
from phase28.resample_timeframes import aggregate_from_5m
from phase31.config import frozen_config_15m
from phase45.execution.config import RAW_1M_PATHS
from phase53.research.data import resample_5m_causal

ROOT = Path(__file__).resolve().parents[2]
LW_DIR = ROOT / "phase58j" / "data"
BRIDGE = ROOT / "phase16" / "data" / "raw" / "nq_continuous_1m_postwindow_to_20260629T0000CT.csv"
EXTENSION = LW_DIR / "nq_continuous_1m_lw_extension.csv"


def lw_1m_paths() -> tuple[Path, ...]:
    paths = list(RAW_1M_PATHS)
    if BRIDGE.exists() and BRIDGE.stat().st_size > 200:
        paths.append(BRIDGE)
    if EXTENSION.exists() and EXTENSION.stat().st_size > 200:
        paths.append(EXTENSION)
    return tuple(paths)


def load_market_1m_lw() -> pd.DataFrame:
    parts = [load_ohlcv_csv(str(p), source_timezone="UTC") for p in lw_1m_paths() if Path(p).exists()]
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    atr = (df["high"] - df["low"]).rolling(14).mean()
    df["atr"] = atr
    vol_sma = pine_sma(df["volume"].astype(float), 20)
    df["rel_volume"] = df["volume"].astype(float) / vol_sma.replace(0, pd.NA)
    df["vol_ma5"] = df["volume"].astype(float).rolling(5).mean()
    return df


def load_markets_lw() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """1M + causal 5M + causal 15M resampled from extended 1M."""
    m1 = load_market_1m_lw()
    m5 = resample_5m_causal(m1)
    if "volume" not in m5.columns and "volume" in m1.columns:
        m5["volume"] = m1["volume"].resample("5min").sum()
    m15 = add_base_indicators(aggregate_from_5m(m5, 15), frozen_config_15m())
    return m1, m5, m15


def data_compatibility_report(hist_m1: pd.DataFrame, ext_m1: pd.DataFrame) -> dict:
    """Compare historical tail vs extension head."""
    if ext_m1.empty:
        return {"status": "FAIL", "reason": "no extension data"}
    h = hist_m1.tail(5000)
    overlap = h.index.intersection(ext_m1.index)
    report = {
        "hist_last": str(hist_m1.index.max()),
        "ext_first": str(ext_m1.index.min()),
        "ext_last": str(ext_m1.index.max()),
        "overlap_bars": len(overlap),
        "columns_hist": list(hist_m1.columns),
        "columns_ext": list(ext_m1.columns),
        "timezone": str(hist_m1.index.tz),
        "duplicate_ext": int(ext_m1.index.duplicated().sum()),
        "ohlc_bad_ext": int((ext_m1["high"] < ext_m1["low"]).sum()),
    }
    if len(overlap) > 0:
        for ts in list(overlap[:3]):
            row_h = hist_m1.loc[ts]
            row_e = ext_m1.loc[ts]
            report[f"overlap_close_{ts}"] = abs(float(row_h["close"]) - float(row_e["close"]))
    report["status"] = "PASS" if report["ohlc_bad_ext"] == 0 and ext_m1.index.max() > hist_m1.index.max() else "FAIL"
    return report


def build_mtf_arrays_lw(swing_5m: int = 5, swing_15m: int = 5):
    """MTFArrays from extended 1M data — mirrors phase58b.precompute.build_mtf_arrays."""
    import numpy as np

    from phase52.research.swings import (
        precompute_last2_swing_highs,
        precompute_last2_swing_lows,
        precompute_swing_highs,
        precompute_swing_lows,
    )
    from phase53.research.data import align_htf_to_1m, htf_bar_index
    from phase58b.research.precompute import MTFArrays

    m1_df, m5_df, m15_df = load_markets_lw()
    m15_on_m5 = align_htf_to_1m(m5_df, m15_df)

    m1_hi = m1_df["high"].values.astype(float)
    m1_lo = m1_df["low"].values.astype(float)
    m1_cl = m1_df["close"].values.astype(float)
    m1_op = m1_df["open"].values.astype(float)
    m1_atr = m1_df["atr"].values.astype(float)

    m5_hi = m5_df["high"].values.astype(float)
    m5_lo = m5_df["low"].values.astype(float)
    m5_cl = m5_df["close"].values.astype(float)
    m5_op = m5_df["open"].values.astype(float)
    m5_atr = m5_df["atr"].values.astype(float) if "atr" in m5_df.columns else np.full(len(m5_df), np.nan)
    m5_body = np.abs(m5_cl - m5_op)

    _sh1, _sh2 = precompute_last2_swing_highs(m5_hi, swing_5m)
    _sl1, _sl2 = precompute_last2_swing_lows(m5_lo, swing_5m)

    m15_cl = m15_on_m5["close"].values.astype(float)
    m15_op = m15_on_m5["open"].values.astype(float)
    m15_hi = m15_on_m5["high"].values.astype(float)
    m15_lo = m15_on_m5["low"].values.astype(float)
    m15_atr = (
        m15_on_m5["atr"].values.astype(float)
        if "atr" in m15_on_m5.columns
        else np.full(len(m15_on_m5), np.nan)
    )
    m15_idx_on_m5 = htf_bar_index(m5_df.index, m15_df.index)

    m1_to_m5 = htf_bar_index(m1_df.index, m5_df.index)
    m5_close_m1_i = np.zeros(len(m5_df), dtype=int)
    m5_signal_m1_i = np.zeros(len(m5_df), dtype=int)
    m5_ts = m5_df.index.values
    m1_ts = m1_df.index.values
    for j in range(len(m5_df)):
        if j + 1 < len(m5_ts):
            close_ts = m5_ts[j + 1]
        else:
            close_ts = m5_ts[j] + np.timedelta64(5, "m")
        pos = int(np.searchsorted(m1_ts, close_ts, side="left"))
        m5_close_m1_i[j] = min(pos, len(m1_df) - 1)
        pos_sig = int(np.searchsorted(m1_ts, m5_ts[j + 1] if j + 1 < len(m5_ts) else close_ts, side="left")) - 1
        m5_signal_m1_i[j] = max(0, min(pos_sig, len(m1_df) - 1))

    return MTFArrays(
        m1_hi=m1_hi, m1_lo=m1_lo, m1_cl=m1_cl, m1_op=m1_op, m1_atr=m1_atr,
        m1_n=len(m1_df), m1_idx=m1_df.index,
        m5_hi=m5_hi, m5_lo=m5_lo, m5_cl=m5_cl, m5_op=m5_op, m5_atr=m5_atr,
        m5_n=len(m5_df), m5_idx=m5_df.index,
        m5_sh=precompute_swing_highs(m5_hi, swing_5m),
        m5_sl=precompute_swing_lows(m5_lo, swing_5m),
        m5_sh1=_sh1, m5_sh2=_sh2, m5_sl1=_sl1, m5_sl2=_sl2, m5_body=m5_body,
        m15_cl=m15_cl, m15_op=m15_op, m15_hi=m15_hi, m15_lo=m15_lo, m15_atr=m15_atr,
        m15_idx_on_m5=m15_idx_on_m5, m1_to_m5=m1_to_m5,
        m5_close_m1_i=m5_close_m1_i, m5_signal_m1_i=m5_signal_m1_i,
    )


def build_market_arrays_lw(swing: int = 5):
    """MarketArrays for Phase58 v1 engine on extended data."""
    import numpy as np
    import pandas as pd

    from phase52.research.swings import (
        precompute_last2_swing_highs,
        precompute_last2_swing_lows,
        precompute_swing_highs,
        precompute_swing_lows,
    )
    from phase53.research.data import align_htf_to_1m, htf_bar_index
    from phase58.research.precompute import MarketArrays

    m1, m5, m15 = load_markets_lw()
    m5a = align_htf_to_1m(m1, m5)
    m15a = align_htf_to_1m(m1, m15)
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    body = np.abs(cl - op)
    avg_body = pd.Series(body).rolling(20, min_periods=1).mean().values
    _sh1, _sh2 = precompute_last2_swing_highs(hi, swing)
    _sl1, _sl2 = precompute_last2_swing_lows(lo, swing)
    return MarketArrays(
        hi=hi, lo=lo, cl=cl, op=op, atr=atr, n=len(m1), idx=m1.index,
        sh=precompute_swing_highs(hi, swing), sl=precompute_swing_lows(lo, swing),
        sh1=_sh1, sh2=_sh2, sl1=_sl1, sl2=_sl2,
        m5_cl=m5a["close"].values.astype(float), m5_op=m5a["open"].values.astype(float),
        m5_hi=m5a["high"].values.astype(float), m5_lo=m5a["low"].values.astype(float),
        m5_atr=m5a["atr"].values.astype(float) if "atr" in m5a.columns else np.full(len(m5a), np.nan),
        m5_idx=htf_bar_index(m1.index, m5.index),
        m15_cl=m15a["close"].values.astype(float), m15_op=m15a["open"].values.astype(float),
        m15_hi=m15a["high"].values.astype(float), m15_lo=m15a["low"].values.astype(float),
        m15_atr=m15a["atr"].values.astype(float) if "atr" in m15a.columns else np.full(len(m15a), np.nan),
        m15_idx=htf_bar_index(m1.index, m15.index),
        body=body, avg_body=avg_body,
    )
