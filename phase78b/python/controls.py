"""Random-direction and matched-timestamp controls."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from phase78.python.analysis import directional_gate, deterministic_flip, random_directions
from phase78.python.paths import first_passage_r_arrays, risk_points, symmetric_stop, _slice_by_time

from .config import MIN_EFFECT, MIN_SOURCE_N


def random_direction_by_group(entries: pd.DataFrame, df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    index = df.index
    highs = df["high"].values
    lows = df["low"].values
    rows = []
    for grp, g in entries.groupby(group_col):
        if len(g) < MIN_SOURCE_N:
            continue
        valid = g[g.apply(lambda r: risk_points(r["entry_price"], r["stop"], r["direction"]) > 0, axis=1)]
        if len(valid) < MIN_SOURCE_N:
            continue
        real_fps, rand_fps, flip_fps = [], [], []
        for _, row in valid.iterrows():
            h60, l60 = _slice_by_time(index, highs, lows, row["entry_time"], 60)
            real_fps.append(row.get("plus_1.0R_before_minus_1R", np.nan))
            fd = deterministic_flip(row["direction"])
            flip_fps.append(
                first_passage_r_arrays(
                    h60, l60, row["entry_price"], symmetric_stop(row["entry_price"], row["stop"], fd), fd
                ).get("plus_1.0R_before_minus_1R", 0)
            )
            eid = f"{row['entry_time']}|{row['entry_price']}"
            rand_fps.append(
                float(
                    np.mean(
                        [
                            first_passage_r_arrays(
                                h60, l60, row["entry_price"], symmetric_stop(row["entry_price"], row["stop"], d), d
                            ).get("plus_1.0R_before_minus_1R", 0)
                            for d in random_directions(eid)
                        ]
                    )
                )
            )
        gate = directional_gate(float(np.nanmean(real_fps)), rand_fps, float(np.mean(flip_fps)))
        rows.append(
            {
                "group": grp,
                "n": len(valid),
                "real_plus1": float(np.nanmean(real_fps)),
                "random_plus1": float(np.mean(rand_fps)),
                "flip_plus1": float(np.mean(flip_fps)),
                "pass": gate["pass"],
                "gross_avg_r": float(valid["outcome_r"].mean()),
                "mfe_15m": float(valid["mfe_15m"].mean()),
                "mae_15m": float(valid["mae_15m"].mean()),
            }
        )
    return pd.DataFrame(rows)


def build_control_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ts_et"] = out.index.tz_convert("America/New_York") if out.index.tz else out.index
    out["hour"] = out["ts_et"].dt.hour + out["ts_et"].dt.minute / 60.0
    out["year"] = out["ts_et"].dt.year
    d = out["ts_et"].dt.date
    out["session_progress"] = out.groupby(d, sort=False)["close"].cumcount() / out.groupby(d, sort=False)["close"].transform("count")
    out["range_5m"] = out["high"].rolling(5).max() - out["low"].rolling(5).min()
    out["range_15m"] = out["high"].rolling(15).max() - out["low"].rolling(15).min()
    out["disp_5m"] = (out["close"] - out["close"].shift(5)).abs()
    session_open = out.groupby(d, sort=False)["open"].transform("first")
    out["dist_session_open"] = (out["close"] - session_open).abs()
    return out


def matched_timestamp_control(
    entries: pd.DataFrame,
    df: pd.DataFrame,
    window_forensics: pd.DataFrame,
    max_smd: float = 0.10,
    sample_n: int = 500,
) -> dict:
    """Lightweight match on ATR + hour within same SB window."""
    entries = entries.sample(min(sample_n, len(entries)), random_state=78002)
    if "atr" not in df.columns:
        return {"matched": 0, "pass": False}
    sb_mfe, sb_mae, ctrl_mfe, ctrl_mae, matched = [], [], [], [], 0
    for _, e in entries.iterrows():
        et = e["entry_time"]
        if et not in df.index:
            continue
        cal = str(e["calendar_date"])
        wid = e["window_id"]
        wf = window_forensics[(window_forensics["calendar_date"].astype(str) == cal) & (window_forensics["window_id"] == wid)]
        if wf.empty:
            continue
        ws = wf.iloc[0]["window_start"]
        we = ws + pd.Timedelta(hours=1)
        pool = df.loc[(df.index >= ws) & (df.index <= we) & (df.index != et)]
        if pool.empty:
            continue
        atr = float(df.loc[et, "atr"])
        hour = et.hour + et.minute / 60
        pool = pool.copy()
        pool["smd"] = (pool["atr"] - atr).abs() / max(atr, 1e-6)
        pool = pool[pool["smd"] <= max_smd]
        if pool.empty:
            continue
        idx = pool.index[0]
        matched += 1
        sb_mfe.append(float(e["mfe_15m"]))
        sb_mae.append(float(e["mae_15m"]))
        ep = float(df.loc[idx, "open"])
        h15 = df.loc[idx : idx + pd.Timedelta(minutes=15), "high"].max()
        l15 = df.loc[idx : idx + pd.Timedelta(minutes=15), "low"].min()
        ctrl_mfe.append(float(h15 - ep))
        ctrl_mae.append(float(ep - l15))
    if not matched:
        return {"matched": 0, "pass": False}
    return {
        "matched": matched,
        "match_rate": matched / len(entries),
        "sb_mfe_15m": float(np.mean(sb_mfe)),
        "sb_mae_15m": float(np.mean(sb_mae)),
        "ctrl_mfe_15m": float(np.mean(ctrl_mfe)),
        "ctrl_mae_15m": float(np.mean(ctrl_mae)),
        "mfe_lift": float(np.mean(sb_mfe) - np.mean(ctrl_mfe)),
        "unusual_location": float(np.mean(sb_mfe)) > float(np.mean(ctrl_mfe)) * 1.05,
    }
