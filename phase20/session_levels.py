"""Causal session liquidity level construction for Phase 20."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig
from phase16.indicators import add_base_indicators, is_in_session, session_bucket
from phase16.resample import cme_session_date

from .config import OR_END_MINUTE, OR_START_MINUTE


def minute_of_day(timestamp: pd.Timestamp) -> int:
    return int(timestamp.hour * 60 + timestamp.minute)


def time_bucket_label(timestamp: pd.Timestamp) -> str:
    minute = minute_of_day(timestamp)
    if minute >= 18 * 60 or minute < 4 * 60:
        return "OVERNIGHT"
    if minute < OR_START_MINUTE:
        return "PREMARKET"
    if minute < 10 * 60 + 30:
        return "RTH_OPEN"
    if minute < 12 * 60:
        return "RTH_MID_MORNING"
    if minute < 14 * 60:
        return "MIDDAY"
    if minute < 16 * 60:
        return "RTH_AFTERNOON"
    return "OTHER"


def prepare_session_liquidity_frame(frame: pd.DataFrame, config: FrozenConfig) -> pd.DataFrame:
    data = frame.sort_index().copy()
    if data.index.tz is None:
        raise TypeError("expected timezone-aware index")
    data = add_base_indicators(data, config)
    session_dates = pd.Series(cme_session_date(data.index), index=data.index, name="cme_session_date")
    data["cme_session_date"] = session_dates
    data["session_bucket"] = [session_bucket(ts) for ts in data.index]
    data["time_bucket"] = [time_bucket_label(ts) for ts in data.index]
    data["minute_of_day"] = [minute_of_day(ts) for ts in data.index]
    data["in_rth"] = [is_in_session(ts, "0930-1600") for ts in data.index]
    data["in_or_window"] = [
        OR_START_MINUTE <= minute_of_day(ts) < OR_END_MINUTE for ts in data.index
    ]
    data["is_overnight_window"] = data["minute_of_day"].lt(OR_START_MINUTE)

    session_high = data.groupby(session_dates)["high"].transform("max")
    session_low = data.groupby(session_dates)["low"].transform("min")
    data["session_high_to_date"] = session_high
    data["session_low_to_date"] = session_low

    overnight_high = (
        data.loc[data["is_overnight_window"]]
        .groupby(session_dates)["high"]
        .cummax()
        .reindex(data.index)
    )
    overnight_low = (
        data.loc[data["is_overnight_window"]]
        .groupby(session_dates)["low"]
        .cummin()
        .reindex(data.index)
    )
    data["onh_build"] = overnight_high
    data["onl_build"] = overnight_low
    data["onh"] = data.groupby(session_dates)["onh_build"].ffill()
    data["onl"] = data.groupby(session_dates)["onl_build"].ffill()

    or_high = (
        data.loc[data["in_or_window"]]
        .groupby(session_dates)["high"]
        .cummax()
        .reindex(data.index)
    )
    or_low = (
        data.loc[data["in_or_window"]]
        .groupby(session_dates)["low"]
        .cummin()
        .reindex(data.index)
    )
    data["orh_build"] = or_high
    data["orl_build"] = or_low
    data["orh"] = data.groupby(session_dates)["orh_build"].ffill()
    data["orl"] = data.groupby(session_dates)["orl_build"].ffill()

    rth_close = data.loc[data["in_rth"]].groupby(session_dates)["close"].last()
    data["prior_rth_close"] = session_dates.map(rth_close.shift(1))

    session_open = (
        data.loc[data["minute_of_day"] >= OR_START_MINUTE]
        .groupby(session_dates)["open"]
        .first()
    )
    data["session_open"] = session_dates.map(session_open)

    data["pdh"] = session_dates.map(session_high.groupby(session_dates).max().shift(1))
    data["pdl"] = session_dates.map(session_low.groupby(session_dates).min().shift(1))

    data["atr_percentile"] = data["atr"].expanding(min_periods=50).rank(pct=True)

    data["above_prior_rth_close"] = data["close"] > data["prior_rth_close"]
    data["overnight_gap_direction"] = np.sign(data["session_open"] - data["prior_rth_close"])

    level_map = {
        "PDH": "pdh",
        "PDL": "pdl",
        "ONH": "onh",
        "ONL": "onl",
        "ORH": "orh",
        "ORL": "orl",
        "PRIOR_RTH_CLOSE": "prior_rth_close",
        "SESSION_OPEN": "session_open",
    }
    for name, column in level_map.items():
        data[f"level_{name}"] = data[column]
    return data


def level_side(level: str) -> str:
    if level in {"PDH", "ONH", "ORH"}:
        return "upper"
    if level in {"PDL", "ONL", "ORL"}:
        return "lower"
    return "neutral"
