"""Observational market regime labels — no entry impact."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RegimeSnapshot:
    regime: str  # CHOP | TREND | UNCERTAIN
    efficiency: float
    atr_ratio: float
    overlap_ratio: float
    range_points: float
    detail: str


def _true_range(df: pd.DataFrame) -> pd.Series:
    prev_c = df["close"].shift(1)
    return pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_c).abs(),
            (df["low"] - prev_c).abs(),
        ],
        axis=1,
    ).max(axis=1)


def compute_regime_frame(df: pd.DataFrame, *, lookback: int = 30) -> pd.DataFrame:
    """Return dataframe indexed like input with regime columns per bar."""
    out = df.copy()
    if "timestamp" in out.columns:
        out = out.set_index("timestamp")
    out.index = pd.to_datetime(out.index, utc=True)

    path = (out["close"] - out["close"].shift(lookback)).abs()
    travel = _true_range(out).rolling(lookback).sum()
    efficiency = (path / travel.replace(0, pd.NA)).fillna(0.0)

    tr = _true_range(out)
    atr = tr.rolling(14).mean()
    atr_med = atr.rolling(100, min_periods=20).median()
    atr_ratio = (atr / atr_med.replace(0, pd.NA)).fillna(1.0)

    body_mid = (out["open"] + out["close"]) / 2
    prev_mid = body_mid.shift(1)
    overlap = (
        (out["low"] <= prev_mid) & (out["high"] >= prev_mid)
    ).astype(float).rolling(lookback).mean().fillna(0.0)

    hi = out["high"].rolling(lookback).max()
    lo = out["low"].rolling(lookback).min()
    range_pts = hi - lo

    regime = pd.Series("UNCERTAIN", index=out.index, dtype=object)
    chop = (efficiency < 0.28) & ((overlap > 0.62) | (atr_ratio < 0.85) | (range_pts < atr * 4))
    trend = (efficiency > 0.42) & (atr_ratio >= 0.9) & (range_pts >= atr * 6)
    regime[chop] = "CHOP"
    regime[trend] = "TREND"

    return pd.DataFrame(
        {
            "regime": regime,
            "efficiency": efficiency,
            "atr_ratio": atr_ratio,
            "overlap_ratio": overlap,
            "range_points": range_pts,
        },
        index=out.index,
    )


def regime_at_time(regime_df: pd.DataFrame, ts: pd.Timestamp) -> RegimeSnapshot:
    ts = pd.Timestamp(ts).tz_convert("UTC") if pd.Timestamp(ts).tzinfo else pd.Timestamp(ts, tz="UTC")
    if ts not in regime_df.index:
        idx = regime_df.index.searchsorted(ts, side="right") - 1
        if idx < 0:
            row = regime_df.iloc[0]
        else:
            row = regime_df.iloc[idx]
    else:
        row = regime_df.loc[ts]
    return RegimeSnapshot(
        regime=str(row["regime"]),
        efficiency=float(row["efficiency"]),
        atr_ratio=float(row["atr_ratio"]),
        overlap_ratio=float(row["overlap_ratio"]),
        range_points=float(row["range_points"]),
        detail=f"eff={row['efficiency']:.2f} atr_r={row['atr_ratio']:.2f} ovl={row['overlap_ratio']:.2f}",
    )
