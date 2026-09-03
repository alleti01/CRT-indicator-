"""Forward path labeling for every eligible RTH decision bar — labels only, no features."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session, session_bucket, session_bucket_name
from phase16.resample import cme_session_date

from .config import (
    ALT_STOP_ATR,
    LABEL_GOOD_TARGET_R,
    LABEL_STRONG_TARGET_R,
    PRIMARY_HORIZONS_MIN,
    PRIMARY_STOP_ATR,
    PRIMARY_TARGET_RS,
    RTH_SESSION,
)
from phase29.config import hold_bars


def _forward_path(
    direction: int,
    entry: float,
    risk: float,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    target_r: float,
    max_bars: int,
) -> Dict[str, float | str | bool | int]:
    """Conservative ambiguous-bar: STOP before TARGET."""
    mfe = mae = 0.0
    target = entry + direction * target_r * risk
    stop = entry - direction * risk
    exit_reason = "TIME"
    terminal_r = 0.0
    target_hit = stop_hit = False
    time_to_target = time_to_stop = np.nan
    first_event = "NONE"

    for step, (hi, lo, cl) in enumerate(zip(highs, lows, closes), start=1):
        if direction == 1:
            bar_mfe = (hi - entry) / risk if risk > 0 else 0.0
            bar_mae = (entry - lo) / risk if risk > 0 else 0.0
            hit_tgt = hi >= target
            hit_stp = lo <= stop
        else:
            bar_mfe = (entry - lo) / risk if risk > 0 else 0.0
            bar_mae = (hi - entry) / risk if risk > 0 else 0.0
            hit_tgt = lo <= target
            hit_stp = hi >= stop

        mfe = max(mfe, bar_mfe)
        mae = max(mae, bar_mae)

        if hit_stp and hit_tgt:
            stop_hit = True
            terminal_r = -1.0
            exit_reason = "STOP"
            time_to_stop = step
            first_event = "STOP"
            break
        if hit_stp:
            stop_hit = True
            terminal_r = -1.0
            exit_reason = "STOP"
            time_to_stop = step
            first_event = "STOP"
            break
        if hit_tgt:
            target_hit = True
            terminal_r = target_r
            exit_reason = "TARGET"
            time_to_target = step
            first_event = "TARGET"
            break
        if step >= max_bars:
            terminal_r = (cl - entry) / risk * direction if risk > 0 else 0.0
            exit_reason = "TIME"
            break

    return {
        "mfe_r": float(mfe),
        "mae_r": float(mae),
        "terminal_r": float(terminal_r),
        "exit_reason": exit_reason,
        "target_hit": bool(target_hit),
        "stop_hit": bool(stop_hit),
        "first_event": first_event,
        "time_to_target": float(time_to_target) if np.isfinite(time_to_target) else np.nan,
        "time_to_stop": float(time_to_stop) if np.isfinite(time_to_stop) else np.nan,
        "target_before_stop": bool(first_event == "TARGET"),
    }


def _quality_label(target_before_stop: bool, target_r: float, strong_r: float, good_r: float) -> str:
    if target_before_stop and target_r >= strong_r:
        return "STRONG"
    if target_before_stop and target_r >= good_r:
        return "GOOD"
    return "NEUTRAL"


def label_all_bars(market: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Label every RTH bar for independent LONG and SHORT hypothetical entries at bar close."""
    idx = market.index
    o = market["open"].to_numpy(float)
    h = market["high"].to_numpy(float)
    l = market["low"].to_numpy(float)
    c = market["close"].to_numpy(float)
    atr = market["atr"].to_numpy(float)
    vol = market["volume"].to_numpy(float) if "volume" in market.columns else np.zeros(len(market))

    rows: List[dict] = []
    opp_rows: List[dict] = []

    primary_horizon = hold_bars(60)
    risk_primary = PRIMARY_STOP_ATR

    for i in range(len(market)):
        ts = idx[i]
        if not is_in_session(ts, RTH_SESSION):
            continue
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue

        entry = float(c[i])
        risk = risk_primary * float(atr[i])
        fut_hi = h[i + 1 : i + 1 + primary_horizon]
        fut_lo = l[i + 1 : i + 1 + primary_horizon]
        fut_cl = c[i + 1 : i + 1 + primary_horizon]
        if len(fut_hi) == 0:
            continue

        row = {
            "timestamp": ts,
            "bar_index": i,
            "open": float(o[i]),
            "high": float(h[i]),
            "low": float(l[i]),
            "close": entry,
            "volume": float(vol[i]),
            "atr": float(atr[i]),
            "session_date": cme_session_date(pd.DatetimeIndex([ts]))[0],
            "session_bucket": session_bucket_name(session_bucket(ts)),
        }

        for direction, label_prefix in ((1, "long"), (-1, "short")):
            path_strong = _forward_path(
                direction, entry, risk, fut_hi, fut_lo, fut_cl,
                LABEL_STRONG_TARGET_R, primary_horizon,
            )
            path_good = _forward_path(
                direction, entry, risk, fut_hi, fut_lo, fut_cl,
                LABEL_GOOD_TARGET_R, primary_horizon,
            )

            qual = "NEUTRAL"
            if path_strong["target_before_stop"]:
                qual = "STRONG"
            elif path_good["target_before_stop"]:
                qual = "GOOD"

            for k, v in path_strong.items():
                row[f"{label_prefix}_{k}"] = v
            row[f"{label_prefix}_quality"] = qual
            row[f"{label_prefix}_strong"] = qual == "STRONG"
            row[f"{label_prefix}_good"] = qual in ("STRONG", "GOOD")

            # extra target geometries at primary horizon
            for tr in PRIMARY_TARGET_RS:
                p = _forward_path(direction, entry, risk, fut_hi, fut_lo, fut_cl, tr, primary_horizon)
                row[f"{label_prefix}_p{str(tr).replace('.', '')}R_before_1R"] = p["target_before_stop"]

            # alternate horizons for 2R target
            for hm in PRIMARY_HORIZONS_MIN:
                hb = hold_bars(hm)
                fut_hi_h = h[i + 1 : i + 1 + hb]
                fut_lo_h = l[i + 1 : i + 1 + hb]
                fut_cl_h = c[i + 1 : i + 1 + hb]
                if len(fut_hi_h) == 0:
                    continue
                p = _forward_path(direction, entry, risk, fut_hi_h, fut_lo_h, fut_cl_h, LABEL_STRONG_TARGET_R, hb)
                row[f"{label_prefix}_2R_before_1R_{hm}m"] = p["target_before_stop"]

            # 1.0 ATR stop variant
            risk_alt = ALT_STOP_ATR * float(atr[i])
            p_alt = _forward_path(direction, entry, risk_alt, fut_hi, fut_lo, fut_cl, LABEL_STRONG_TARGET_R, primary_horizon)
            row[f"{label_prefix}_2R_before_1R_stop1p0"] = p_alt["target_before_stop"]

            if qual in ("STRONG", "GOOD"):
                opp_rows.append(
                    {
                        "timestamp": ts,
                        "direction": "Long" if direction == 1 else "Short",
                        "quality": qual,
                        "entry_price": entry,
                        "atr": float(atr[i]),
                        "mfe_r": path_strong["mfe_r"],
                        "mae_r": path_strong["mae_r"],
                        "terminal_r": path_strong["terminal_r"],
                        "target_before_stop": path_strong["target_before_stop"],
                        "exit_reason": path_strong["exit_reason"],
                        "time_to_target": path_strong["time_to_target"],
                        "time_to_stop": path_strong["time_to_stop"],
                        "session_bucket": row["session_bucket"],
                    }
                )

        rows.append(row)

    labels = pd.DataFrame(rows)
    opportunities = pd.DataFrame(opp_rows)
    return labels, opportunities
