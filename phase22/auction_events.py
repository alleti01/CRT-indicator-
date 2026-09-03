"""Auction event extraction and forward outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig

from .config import ERAS, HORIZONS, RESET_ATR, RTH_SESSION
from .profile_construction import attach_prior_profile_to_bars, build_daily_profiles, rth_time_bucket
from phase16.indicators import is_in_session


@dataclass
class DedupState:
    armed: bool = True
    last_bar: int = -1


def assign_era(timestamp: pd.Timestamp, tz: str) -> str:
    ts = pd.Timestamp(timestamp).tz_convert(tz)
    for era, (start, end) in ERAS.items():
        if pd.Timestamp(start, tz=tz) <= ts <= pd.Timestamp(end, tz=tz):
            return era
    return "outside"


def orientation_for_event(event_type: str) -> str:
    mapping = {
        "ACCEPTANCE_ABOVE_VAH": "continuation_up",
        "ACCEPTANCE_BELOW_VAL": "continuation_down",
        "REJECTION_ABOVE_VAH": "reversal_down",
        "REJECTION_BELOW_VAL": "reversal_up",
        "CLOSE_ABOVE_VAH": "continuation_up",
        "CLOSE_BELOW_VAL": "continuation_down",
        "HOLD_ABOVE_VAH": "continuation_up",
        "HOLD_BELOW_VAL": "continuation_down",
        "RETURN_INTO_VALUE_AFTER_ABOVE": "reversal_down",
        "RETURN_INTO_VALUE_AFTER_BELOW": "reversal_up",
        "TEST_VAH_FROM_BELOW": "continuation_up",
        "TEST_VAH_FROM_ABOVE": "reversal_down",
        "TEST_VAL_FROM_ABOVE": "continuation_down",
        "TEST_VAL_FROM_BELOW": "reversal_up",
        "POC_TEST": "both",
        "FULL_VALUE_TRAVERSAL": "both",
        "POC_CROSS_AFTER_OUTSIDE_OPEN": "both",
    }
    return mapping.get(event_type, "both")


def directional_multiplier(orientation: str, raw_atr: float) -> float:
    if orientation == "continuation_up" or orientation == "reversal_up":
        return raw_atr
    if orientation == "continuation_down" or orientation == "reversal_down":
        return -raw_atr
    return raw_atr


def compute_forward(data: pd.DataFrame, row: pd.Series, orientation: str) -> dict:
    metrics: dict = {}
    idx = int(row.bar_index)
    if idx >= len(data) - 1:
        return metrics
    atr = float(row.atr) if np.isfinite(row.atr) and row.atr > 0 else np.nan
    if not np.isfinite(atr) or atr <= 0:
        return metrics
    event_close = float(row.close)
    bar = data.iloc[idx]
    event_high = float(bar.high)
    event_low = float(bar.low)
    poc = float(row.prior_poc)
    val = float(row.prior_val)
    vah = float(row.prior_vah)
    value_width = float(row.prior_value_width)
    highs = data["high"].to_numpy(dtype=float)
    lows = data["low"].to_numpy(dtype=float)
    closes = data["close"].to_numpy(dtype=float)

    for horizon in HORIZONS:
        end_idx = min(idx + horizon, len(data) - 1)
        if end_idx <= idx:
            continue
        window_high = float(highs[idx + 1 : end_idx + 1].max())
        window_low = float(lows[idx + 1 : end_idx + 1].min())
        end_close = float(closes[end_idx])
        raw = end_close - event_close
        raw_atr = raw / atr
        metrics[f"signed_return_atr_{horizon}"] = raw_atr
        metrics[f"raw_points_{horizon}"] = raw
        if orientation == "both":
            metrics[f"directional_atr_{horizon}"] = raw_atr
            metrics[f"directional_up_atr_{horizon}"] = raw_atr
            metrics[f"directional_down_atr_{horizon}"] = -raw_atr
        else:
            metrics[f"directional_atr_{horizon}"] = directional_multiplier(orientation, raw_atr)
        metrics[f"mfe_atr_{horizon}"] = (window_high - event_close) / atr
        metrics[f"mae_atr_{horizon}"] = (event_close - window_low) / atr

    # Auction path metrics (fixed references).
    future_high = highs[idx + 1 :]
    future_low = lows[idx + 1 :]
    future_close = closes[idx + 1 :]
    if len(future_close) == 0:
        return metrics
    if orientation in {"reversal_down", "continuation_up"} or row.event_type in {"REJECTION_ABOVE_VAH", "ACCEPTANCE_ABOVE_VAH"}:
        hit_poc = bool(np.any(future_low <= poc))
        hit_val = bool(np.any(future_low <= val))
        extend_target = vah + 0.5 * value_width
        hit_extend = bool(np.any(future_high >= extend_target))
        metrics["path_hit_poc_before_rejection_high"] = bool(
            np.argmax(future_low <= poc) < np.argmax(future_high > event_high) if hit_poc and np.any(future_high > event_high) else hit_poc
        )
        metrics["path_hit_val_before_rejection_high"] = bool(
            np.argmax(future_low <= val) < np.argmax(future_high > event_high) if hit_val and np.any(future_high > event_high) else hit_val
        )
        metrics["path_hit_half_width_extension"] = hit_extend
    if orientation in {"reversal_up", "continuation_down"} or row.event_type in {"REJECTION_BELOW_VAL", "ACCEPTANCE_BELOW_VAL"}:
        hit_poc = bool(np.any(future_high >= poc))
        hit_vah = bool(np.any(future_high >= vah))
        extend_target = val - 0.5 * value_width
        hit_extend = bool(np.any(future_low <= extend_target))
        metrics["path_hit_poc_before_rejection_low"] = bool(
            np.argmax(future_high >= poc) < np.argmax(future_low < event_low) if hit_poc and np.any(future_low < event_low) else hit_poc
        )
        metrics["path_hit_vah_before_rejection_low"] = bool(
            np.argmax(future_high >= vah) < np.argmax(future_low < event_low) if hit_vah and np.any(future_low < event_low) else hit_vah
        )
        metrics["path_hit_half_width_extension_down"] = hit_extend
    return metrics


def attach_forward_outcomes(data: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, event in events.iterrows():
        payload = event.to_dict()
        orientation = str(event.orientation)
        payload.update(compute_forward(data, event, orientation))
        rows.append(payload)
    return pd.DataFrame(rows)


def inside_value(close: float, val: float, vah: float) -> bool:
    return val <= close <= vah


def can_fire(state: DedupState, *, bar_index: int, close: float, level: float, atr: float) -> bool:
    if not state.armed:
        if np.isfinite(atr) and atr > 0 and abs(close - level) > RESET_ATR * atr:
            state.armed = True
        return False
    if state.last_bar == bar_index:
        return False
    return True


def extract_auction_events(
    frame: pd.DataFrame,
    config: FrozenConfig,
    *,
    profiles: pd.DataFrame | None = None,
    prepared: pd.DataFrame | None = None,
) -> pd.DataFrame:
    profiles = profiles if profiles is not None else build_daily_profiles(frame, config)
    data = prepared if prepared is not None else attach_prior_profile_to_bars(frame, profiles, config)
    events: List[dict] = []
    dedup: Dict[Tuple, DedupState] = {}
    event_id = 0
    session_flags: Dict[str, dict] = {}

    for bar_index in range(2, len(data)):
        row = data.iloc[bar_index]
        prev = data.iloc[bar_index - 1]
        prev2 = data.iloc[bar_index - 2]
        timestamp = data.index[bar_index]
        if not row.in_rth:
            continue
        era = assign_era(timestamp, config.exchange_timezone)
        if era == "outside":
            continue
        if not np.isfinite(row.prior_vah) or not np.isfinite(row.prior_val) or not np.isfinite(row.prior_poc):
            continue

        vah = float(row.prior_vah)
        val = float(row.prior_val)
        poc = float(row.prior_poc)
        close = float(row.close)
        prev_close = float(prev.close)
        high = float(row.high)
        low = float(row.low)
        prev_high = float(prev.high)
        prev_low = float(prev.low)
        atr = float(row.atr) if np.isfinite(row.atr) else np.nan
        session_key = str(row.cme_session_date)
        flags = session_flags.setdefault(
            session_key,
            {
                "closed_above_vah": False,
                "closed_below_val": False,
                "outside_open": row.open_location in {"ABOVE_VAH", "BELOW_VAL"},
                "visited_vah": False,
                "visited_val": False,
            },
        )

        candidates: List[Tuple[str, str, float]] = []

        if prev_close < vah and high >= vah:
            candidates.append(("TEST_VAH_FROM_BELOW", "VAH", vah))
        if prev_close > vah and low <= vah:
            candidates.append(("TEST_VAH_FROM_ABOVE", "VAH", vah))
        if prev_close > val and low <= val:
            candidates.append(("TEST_VAL_FROM_ABOVE", "VAL", val))
        if prev_close < val and high >= val:
            candidates.append(("TEST_VAL_FROM_BELOW", "VAL", val))
        if prev_low > poc and low <= poc <= high:
            candidates.append(("POC_TEST", "POC", poc))
        if prev_close <= vah and close > vah:
            candidates.append(("CLOSE_ABOVE_VAH", "VAH", vah))
            flags["closed_above_vah"] = True
        if prev_close >= val and close < val:
            candidates.append(("CLOSE_BELOW_VAL", "VAL", val))
            flags["closed_below_val"] = True
        if close > vah and float(prev.close) > vah:
            candidates.append(("HOLD_ABOVE_VAH", "VAH", vah))
        if close < val and float(prev.close) < val:
            candidates.append(("HOLD_BELOW_VAL", "VAL", val))

        if prev_close > vah and close > vah:
            candidates.append(("ACCEPTANCE_ABOVE_VAH", "VAH", vah))
        if prev_close < val and close < val:
            candidates.append(("ACCEPTANCE_BELOW_VAL", "VAL", val))
        if (float(prev.close) > vah or float(prev.high) > vah) and inside_value(close, val, vah) and float(prev.close) > vah:
            candidates.append(("REJECTION_ABOVE_VAH", "VAH", vah))
        if (float(prev.close) < val or float(prev.low) < val) and inside_value(close, val, vah) and float(prev.close) < val:
            candidates.append(("REJECTION_BELOW_VAL", "VAL", val))

        if flags["closed_above_vah"] and inside_value(close, val, vah) and not inside_value(prev_close, val, vah):
            candidates.append(("RETURN_INTO_VALUE_AFTER_ABOVE", "VALUE", vah))
        if flags["closed_below_val"] and inside_value(close, val, vah) and not inside_value(prev_close, val, vah):
            candidates.append(("RETURN_INTO_VALUE_AFTER_BELOW", "VALUE", val))

        if flags["visited_vah"] and low <= val:
            candidates.append(("FULL_VALUE_TRAVERSAL", "VALUE", poc))
        if flags["visited_val"] and high >= vah:
            candidates.append(("FULL_VALUE_TRAVERSAL", "VALUE", poc))
        if high >= vah:
            flags["visited_vah"] = True
        if low <= val:
            flags["visited_val"] = True

        if flags["outside_open"] and ((prev_close < poc <= close) or (prev_close > poc >= close)):
            candidates.append(("POC_CROSS_AFTER_OUTSIDE_OPEN", "POC", poc))

        for event_type, profile_level, level_value in candidates:
            orientation = orientation_for_event(event_type)
            key = (session_key, event_type, profile_level)
            state = dedup.setdefault(key, DedupState())
            if not can_fire(state, bar_index=bar_index, close=close, level=level_value, atr=atr):
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
                    "event_type": event_type,
                    "profile_level": profile_level,
                    "orientation": orientation,
                    "open_location": row.open_location,
                    "value_migration": row.prior_value_migration,
                    "value_width_quartile": row.prior_value_width_quartile,
                    "time_bucket": row.rth_time_bucket,
                    "prior_poc": poc,
                    "prior_vah": vah,
                    "prior_val": val,
                    "prior_value_width": float(row.prior_value_width),
                    "prior_value_width_atr": float(row.prior_value_width_atr),
                    "level_value": level_value,
                    "close": close,
                    "atr": atr,
                    "close_beyond_atr": (close - level_value) / atr if np.isfinite(atr) and atr > 0 else np.nan,
                }
            )

    events_df = pd.DataFrame(events)
    if events_df.empty:
        return events_df
    return attach_forward_outcomes(data, events_df)
