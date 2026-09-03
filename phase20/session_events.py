"""Session liquidity interaction events with deterministic de-duplication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig

from .config import APPROACH_ATR, ERAS, EVENT_TYPES, LEVELS, RESET_ATR
from .forward_returns import attach_forward_returns
from .session_levels import level_side, prepare_session_liquidity_frame, time_bucket_label


@dataclass
class DedupState:
    last_bar: int = -1
    armed: bool = True


def assign_era(timestamp: pd.Timestamp, tz: str) -> str:
    ts = pd.Timestamp(timestamp).tz_convert(tz)
    for era, (start, end) in ERAS.items():
        if pd.Timestamp(start, tz=tz) <= ts <= pd.Timestamp(end, tz=tz):
            return era
    return "outside"


def displacement_features(row, level_value: float, atr: float) -> Dict[str, float]:
    if not np.isfinite(level_value) or not np.isfinite(atr) or atr <= 0:
        return {
            "body_atr": np.nan,
            "range_atr": np.nan,
            "close_location": np.nan,
            "close_beyond_atr": np.nan,
            "wick_penetration_atr": np.nan,
        }
    rng = float(row.high) - float(row.low)
    body = abs(float(row.close) - float(row.open))
    close_beyond = max(float(row.close) - level_value, level_value - float(row.close), 0.0)
    wick_up = max(float(row.high) - level_value, 0.0)
    wick_down = max(level_value - float(row.low), 0.0)
    wick_pen = max(wick_up, wick_down)
    close_loc = (float(row.close) - float(row.low)) / rng if rng > 0 else 0.5
    return {
        "body_atr": body / atr,
        "range_atr": rng / atr,
        "close_location": close_loc,
        "close_beyond_atr": close_beyond / atr,
        "wick_penetration_atr": wick_pen / atr,
    }


def detect_interactions(row, prev_row, level_value: float) -> Dict[str, bool]:
    out = {name: False for name in EVENT_TYPES}
    if not np.isfinite(level_value):
        return out
    high = float(row.high)
    low = float(row.low)
    close = float(row.close)
    prev_close = float(prev_row.close) if prev_row is not None else close
    prev_high = float(prev_row.high) if prev_row is not None else high
    prev_low = float(prev_row.low) if prev_row is not None else low

    distance = abs(close - level_value)
    prev_distance = abs(prev_close - level_value)
    atr = float(row.atr) if np.isfinite(row.atr) and row.atr > 0 else np.nan
    if np.isfinite(atr) and atr > 0:
        out["APPROACH"] = distance <= APPROACH_ATR * atr and prev_distance > APPROACH_ATR * atr

    touched = high >= level_value and low <= level_value
    prev_touched = prev_high >= level_value and prev_low <= level_value
    out["TOUCH"] = touched and not prev_touched

    out["SWEEP"] = (high > level_value and close < level_value) or (low < level_value and close > level_value)
    out["BREAK"] = (prev_close <= level_value and close > level_value) or (prev_close >= level_value and close < level_value)
    return out


def can_fire(
    *,
    bar_index: int,
    close: float,
    level_value: float,
    atr: float,
    state: DedupState,
) -> bool:
    if not state.armed:
        if np.isfinite(atr) and atr > 0 and abs(close - level_value) > RESET_ATR * atr:
            state.armed = True
        return False
    if state.last_bar >= 0 and bar_index == state.last_bar:
        return False
    return True


def extract_session_liquidity_events(frame: pd.DataFrame, config: FrozenConfig) -> pd.DataFrame:
    data = prepare_session_liquidity_frame(frame, config)
    events: List[Dict] = []
    dedup: Dict[Tuple, DedupState] = {}
    pending_break: Dict[Tuple, Dict] = {}
    event_id = 0

    for bar_index in range(1, len(data)):
        row = data.iloc[bar_index]
        prev = data.iloc[bar_index - 1]
        timestamp = data.index[bar_index]
        era = assign_era(timestamp, config.exchange_timezone)
        if era == "outside":
            continue
        atr = float(row.atr) if np.isfinite(row.atr) else np.nan
        session_key = row.cme_session_date

        for level in LEVELS:
            level_value = float(row[f"level_{level}"])
            if not np.isfinite(level_value):
                continue
            interactions = detect_interactions(row, prev, level_value)
            disp = displacement_features(row, level_value, atr)

            for event_type in ("APPROACH", "TOUCH", "SWEEP", "BREAK"):
                if not interactions[event_type]:
                    continue
                key = (session_key, level, event_type)
                state = dedup.setdefault(key, DedupState())
                if not can_fire(
                    bar_index=bar_index,
                    close=float(row.close),
                    level_value=level_value,
                    atr=atr,
                    state=state,
                ):
                    continue
                event_id += 1
                state.last_bar = bar_index
                state.armed = False
                events.append(
                    {
                        "event_id": event_id,
                        "timestamp": timestamp,
                        "bar_index": bar_index,
                        "era": era,
                        "level": level,
                        "level_side": level_side(level),
                        "event_type": event_type,
                        "time_bucket": row.time_bucket,
                        "level_value": level_value,
                        "close": float(row.close),
                        "atr": atr,
                        "htf_vol_regime": "high_vol" if row.atr_percentile >= 0.66 else "low_vol",
                        "above_prior_rth_close": bool(row.above_prior_rth_close),
                        "overnight_gap_direction": int(row.overnight_gap_direction)
                        if np.isfinite(row.overnight_gap_direction)
                        else 0,
                        **disp,
                    }
                )
                if event_type == "BREAK":
                    pending_break[(session_key, level, bar_index)] = {
                        "parent_event_id": event_id,
                        "break_direction": "up" if float(row.close) > level_value else "down",
                        "level_value": level_value,
                    }

        for key, payload in list(pending_break.items()):
            session_key, level, break_bar = key
            if break_bar != bar_index - 1:
                continue
            level_value = payload["level_value"]
            break_dir = payload["break_direction"]
            held = (break_dir == "up" and float(row.close) > level_value) or (
                break_dir == "down" and float(row.close) < level_value
            )
            failed = not held
            for subtype in ("BREAK_HOLD", "BREAK_FAILURE"):
                if (subtype == "BREAK_HOLD" and not held) or (subtype == "BREAK_FAILURE" and not failed):
                    continue
                dedup_key = (session_key, level, subtype)
                state = dedup.setdefault(dedup_key, DedupState())
                if not can_fire(
                    bar_index=bar_index,
                    close=float(row.close),
                    level_value=level_value,
                    atr=atr,
                    state=state,
                ):
                    continue
                event_id += 1
                state.last_bar = bar_index
                state.armed = False
                disp = displacement_features(row, level_value, atr)
                events.append(
                    {
                        "event_id": event_id,
                        "timestamp": timestamp,
                        "bar_index": bar_index,
                        "era": era,
                        "level": level,
                        "level_side": level_side(level),
                        "event_type": subtype,
                        "time_bucket": row.time_bucket,
                        "level_value": level_value,
                        "close": float(row.close),
                        "atr": atr,
                        "htf_vol_regime": "high_vol" if row.atr_percentile >= 0.66 else "low_vol",
                        "above_prior_rth_close": bool(row.above_prior_rth_close),
                        "overnight_gap_direction": int(row.overnight_gap_direction)
                        if np.isfinite(row.overnight_gap_direction)
                        else 0,
                        **disp,
                    }
                )
            pending_break.pop(key, None)

    events_df = pd.DataFrame(events)
    if events_df.empty:
        return events_df
    events_df = attach_forward_returns(data, events_df)
    return events_df
