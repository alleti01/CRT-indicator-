"""Sequence-order placebo detection within Silver Bullet windows."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from phase78.python.liquidity import LiquidityMap
from phase78.python.sequence import _detect_fvg, _detect_sweep, _displacement_ok, _mss_ok


@dataclass
class PlaceboEvent:
    calendar_date: object
    window_id: str
    placebo_type: str
    event_time: pd.Timestamp
    direction: str
    bar_idx: int


def detect_placebos(
    df_slice: pd.DataFrame,
    liq_map: LiquidityMap,
    calendar_date: object,
    window_id: str,
    window_end: pd.Timestamp,
) -> list[PlaceboEvent]:
    """Find naturally occurring wrong-order component events before canonical sweep."""
    events: list[PlaceboEvent] = []
    if len(df_slice) < 5:
        return events

    highs = df_slice["high"].values
    lows = df_slice["low"].values
    closes = df_slice["close"].values
    atrs = df_slice["atr"].values
    index = df_slice.index

    first_sweep_i: int | None = None
    for local_i in range(len(df_slice)):
        ts = index[local_i]
        if ts > window_end:
            break
        h, l, c, atr = highs[local_i], lows[local_i], closes[local_i], atrs[local_i]
        if first_sweep_i is None:
            for liq in liq_map.levels:
                swept, _, _ = _detect_sweep(h, l, liq)
                if swept:
                    first_sweep_i = local_i
                    break
        pre_sweep = first_sweep_i is None or local_i < first_sweep_i
        if not pre_sweep and first_sweep_i is not None and local_i == first_sweep_i:
            continue

        # FVG before sweep
        for d in ("LONG", "SHORT"):
            fvg = _detect_fvg(d, highs, lows, local_i)
            if fvg and pre_sweep:
                events.append(PlaceboEvent(calendar_date, window_id, "FVG_BEFORE_SWEEP", ts, d, local_i))

        # MSS before sweep
        for d in ("LONG", "SHORT"):
            ok, _ = _mss_ok(d, c, lows, highs, local_i)
            if ok and pre_sweep:
                events.append(PlaceboEvent(calendar_date, window_id, "MSS_BEFORE_SWEEP", ts, d, local_i))

        # Displacement before sweep (using bar extreme as pseudo sweep)
        for d in ("LONG", "SHORT"):
            pseudo = h if d == "SHORT" else l
            ok, _ = _displacement_ok(d, pseudo, c, atr)
            if ok and pre_sweep:
                events.append(PlaceboEvent(calendar_date, window_id, "DISPLACEMENT_BEFORE_SWEEP", ts, d, local_i))

    # Dedupe by type/time
    seen = set()
    uniq = []
    for e in events:
        k = (e.placebo_type, str(e.event_time), e.direction)
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq
