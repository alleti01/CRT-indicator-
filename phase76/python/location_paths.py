"""Two-sided path metrics after location interaction — no prescribed direction."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .location_config import (
    CLEAN_EXP_HORIZON,
    CLEAN_EXP_MAJOR_ATR,
    CLEAN_EXP_OPPOSITE_MAX_ATR,
    CONTINUATION_EXT_ATR,
    CONTINUATION_HORIZON,
    FIRST_BREAK_ATR,
    PATH_HORIZONS,
    REJECTION_HORIZON,
    THRESHOLD_ATR_LEVELS,
)


def _scan_two_sided(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    start: int,
    ref_price: float,
    atr: float,
    max_bars: int,
) -> dict[str, float]:
    end = min(start + max_bars, len(highs))
    if start >= end or atr <= 0 or np.isnan(atr):
        return {}

    h = highs[start:end]
    l = lows[start:end]
    c = closes[start:end]
    n = len(h)

    cummax_h = np.maximum.accumulate(h)
    cummin_l = np.minimum.accumulate(l)
    mfe_up = (cummax_h - ref_price) / atr
    mfe_down = (ref_price - cummin_l) / atr

    out: dict[str, float] = {}
    for horizon in PATH_HORIZONS:
        w = min(horizon, n)
        if w == 0:
            continue
        up = float(mfe_up[w - 1])
        dn = float(mfe_down[w - 1])
        out[f"abs_excursion_{horizon}m"] = max(up, dn)
        out[f"mfe_up_{horizon}m"] = up
        out[f"mfe_down_{horizon}m"] = dn
        out[f"two_sided_range_{horizon}m"] = up + dn
        out[f"largest_side_{horizon}m"] = max(up, dn)
        net = (c[w - 1] - ref_price) / atr
        total = up + dn
        out[f"net_displacement_{horizon}m"] = float(net)
        out[f"directional_efficiency_{horizon}m"] = float(abs(net) / total) if total > 0 else np.nan

    for thr in THRESHOLD_ATR_LEVELS:
        hit_up = mfe_up >= thr
        hit_dn = mfe_down >= thr
        t_up = np.argmax(hit_up) + 1 if hit_up.any() else np.nan
        t_dn = np.argmax(hit_dn) + 1 if hit_dn.any() else np.nan
        out[f"time_to_up_{thr}atr"] = float(t_up) if not np.isnan(t_up) else np.nan
        out[f"time_to_down_{thr}atr"] = float(t_dn) if not np.isnan(t_dn) else np.nan

    hit_up05 = mfe_up >= 0.5
    hit_dn05 = mfe_down >= 0.5
    first_side = "NONE"
    if hit_up05.any() or hit_dn05.any():
        i_up = np.argmax(hit_up05) if hit_up05.any() else 9999
        i_dn = np.argmax(hit_dn05) if hit_dn05.any() else 9999
        if i_up == i_dn and hit_up05[i_up] and hit_dn05[i_dn]:
            first_side = "TIE"
        elif i_up < i_dn:
            first_side = "UP"
        elif i_dn < i_up:
            first_side = "DOWN"
    out["first_side_05"] = {"UP": 1.0, "DOWN": 0.0, "TIE": 0.5, "NONE": np.nan}.get(first_side, np.nan)

    w60 = min(60, n)
    up60 = float(mfe_up[w60 - 1]) if w60 else 0.0
    dn60 = float(mfe_down[w60 - 1]) if w60 else 0.0
    for thr in (0.5, 1.0, 1.5, 2.0):
        out[f"sweep_both_{thr}"] = 1.0 if (up60 >= thr and dn60 >= thr) else 0.0

    w15 = min(CLEAN_EXP_HORIZON, n)
    if w15:
        up15 = float(mfe_up[w15 - 1])
        dn15 = float(mfe_down[w15 - 1])
        clean = (up15 >= CLEAN_EXP_MAJOR_ATR and dn15 <= CLEAN_EXP_OPPOSITE_MAX_ATR) or (
            dn15 >= CLEAN_EXP_MAJOR_ATR and up15 <= CLEAN_EXP_OPPOSITE_MAX_ATR
        )
        out["clean_expansion"] = 1.0 if clean else 0.0
        out["rejection_rotation"] = 1.0 if (out["sweep_both_0.5"] >= 1.0 and not clean) else 0.0
    else:
        out["clean_expansion"] = np.nan
        out["rejection_rotation"] = np.nan

    first_break_side = None
    break_bar = None
    lim = min(CONTINUATION_HORIZON, n)
    for j in range(lim):
        if mfe_up[j] >= FIRST_BREAK_ATR:
            first_break_side, break_bar = "UP", j
            break
        if mfe_down[j] >= FIRST_BREAK_ATR:
            first_break_side, break_bar = "DOWN", j
            break
    if first_break_side is not None and break_bar is not None:
        rem_up = float(mfe_up[lim - 1] - mfe_up[break_bar])
        rem_dn = float(mfe_down[lim - 1] - mfe_down[break_bar])
        if first_break_side == "UP":
            out["continuation_after_break"] = 1.0 if rem_up >= CONTINUATION_EXT_ATR else 0.0
            out["failure_after_break"] = 1.0 if rem_dn >= FIRST_BREAK_ATR else 0.0
        else:
            out["continuation_after_break"] = 1.0 if rem_dn >= CONTINUATION_EXT_ATR else 0.0
            out["failure_after_break"] = 1.0 if rem_up >= FIRST_BREAK_ATR else 0.0
    else:
        out["continuation_after_break"] = np.nan
        out["failure_after_break"] = np.nan

    return out


def attach_path_metrics(events: pd.DataFrame, ohlc: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events
    highs = ohlc["high"].to_numpy(dtype=float)
    lows = ohlc["low"].to_numpy(dtype=float)
    closes = ohlc["close"].to_numpy(dtype=float)
    pos = {ts: i for i, ts in enumerate(ohlc.index)}

    base_cols = list(events.columns)
    path_keys: list[str] | None = None
    path_matrix: list[list[float]] = []
    keep_rows: list[int] = []

    for ri, ev in enumerate(events.itertuples(index=False)):
        ts = ev.interaction_ts
        start = pos.get(ts)
        if start is None:
            continue
        atr = ev.atr
        if pd.isna(atr) or atr <= 0:
            continue
        paths = _scan_two_sided(highs, lows, closes, start, float(ev.price), float(atr), 60)
        if not paths:
            continue
        if path_keys is None:
            path_keys = list(paths.keys())
        path_matrix.append([paths[k] for k in path_keys])
        keep_rows.append(ri)

    if not keep_rows or path_keys is None:
        return pd.DataFrame()

    out = events.iloc[keep_rows].reset_index(drop=True)
    path_df = pd.DataFrame(path_matrix, columns=path_keys)
    return pd.concat([out, path_df], axis=1)


def aggregate_path_metrics(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {"n": 0}
    out: dict[str, float] = {"n": len(df)}
    metric_cols = [c for c in df.columns if any(
        c.startswith(p) for p in (
            "abs_excursion_", "two_sided_range_", "largest_side_", "directional_efficiency_",
            "clean_expansion", "rejection_rotation", "sweep_both_", "continuation_after_break",
            "failure_after_break", "time_to_up_", "time_to_down_",
        )
    )]
    for col in metric_cols:
        s = df[col].dropna()
        if len(s):
            out[f"{col}_mean"] = float(s.mean())
    return out
