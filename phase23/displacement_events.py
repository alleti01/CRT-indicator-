"""Displacement event extraction with deduplication and variants."""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig

from .config import DEDUP_SAME_DIRECTION_BARS, ERAS, MIN_BODY_ATR_EVENT, PERCENTILE_THRESHOLDS, STRUCTURE_LOOKBACK
from .displacement_features import prepare_displacement_frame
from .forward_returns import attach_forward_outcomes


def assign_era(timestamp: pd.Timestamp, tz: str) -> str:
    ts = pd.Timestamp(timestamp).tz_convert(tz)
    for era, (start, end) in ERAS.items():
        if pd.Timestamp(start, tz=tz) <= ts <= pd.Timestamp(end, tz=tz):
            return era
    return "outside"


def _base_event(
    event_id: int,
    row,
    bar_index: int,
    timestamp,
    era: str,
    *,
    event_definition: str,
    direction: str,
    orientation: str = "continuation",
) -> dict:
    return {
        "event_id": event_id,
        "timestamp": timestamp,
        "bar_index": bar_index,
        "era": era,
        "event_definition": event_definition,
        "direction": direction,
        "orientation": orientation,
        "body_atr24": float(row.body_atr24),
        "strength_bucket": str(row.strength_bucket),
        "body_range": float(row.body_range) if np.isfinite(row.body_range) else np.nan,
        "close_location": float(row.close_location) if np.isfinite(row.close_location) else np.nan,
        "structure_break": bool(row.structure_break),
        "body_atr_pct": float(row.body_atr_pct) if np.isfinite(row.body_atr_pct) else np.nan,
        "volume_ratio24": float(row.volume_ratio24) if np.isfinite(row.volume_ratio24) else np.nan,
        "path_efficiency_12": float(row.path_efficiency_12) if np.isfinite(row.path_efficiency_12) else np.nan,
        "accel_vs_3": float(row.accel_vs_3) if np.isfinite(row.accel_vs_3) else np.nan,
        "session_bucket": str(row.session_bucket),
        "close": float(row.close),
        "atr24": float(row.atr24),
        "deduplicated": True,
    }


def extract_displacement_events(
    frame: pd.DataFrame,
    config: FrozenConfig,
    *,
    prepared: pd.DataFrame | None = None,
    deduplicate: bool = True,
) -> pd.DataFrame:
    data = prepared if prepared is not None else prepare_displacement_frame(frame, config)
    events: List[dict] = []
    cooldown: Dict[str, int] = {}
    event_id = 0

    for bar_index in range(max(13, STRUCTURE_LOOKBACK + 1), len(data) - 2):
        row = data.iloc[bar_index]
        timestamp = data.index[bar_index]
        direction = str(row.direction)
        if direction not in {"BULLISH", "BEARISH"}:
            continue
        if not np.isfinite(row.body_atr24) or row.body_atr24 < MIN_BODY_ATR_EVENT:
            continue
        era = assign_era(timestamp, config.exchange_timezone)
        if era == "outside":
            continue

        if deduplicate:
            until = cooldown.get(direction, -1)
            if bar_index <= until:
                continue
            cooldown[direction] = bar_index + DEDUP_SAME_DIRECTION_BARS

        event_id += 1
        events.append(_base_event(event_id, row, bar_index, timestamp, era, event_definition="DISPLACEMENT_ALONE", direction=direction))

        if bool(row.structure_break):
            event_id += 1
            events.append(
                _base_event(
                    event_id,
                    row,
                    bar_index,
                    timestamp,
                    era,
                    event_definition="DISPLACEMENT_STRUCTURE_BREAK",
                    direction=direction,
                )
            )

        nxt = data.iloc[bar_index + 1]
        if direction == "BULLISH" and float(nxt.close) > float(row.close):
            event_id += 1
            ft = _base_event(
                event_id,
                nxt,
                bar_index + 1,
                data.index[bar_index + 1],
                era,
                event_definition="DISPLACEMENT_FOLLOWTHROUGH",
                direction=direction,
            )
            events.append(ft)
        elif direction == "BEARISH" and float(nxt.close) < float(row.close):
            event_id += 1
            ft = _base_event(
                event_id,
                nxt,
                bar_index + 1,
                data.index[bar_index + 1],
                era,
                event_definition="DISPLACEMENT_FOLLOWTHROUGH",
                direction=direction,
            )
            events.append(ft)

        failed = (direction == "BULLISH" and float(nxt.close) < float(row.midpoint)) or (
            direction == "BEARISH" and float(nxt.close) > float(row.midpoint)
        )
        if failed:
            event_id += 1
            events.append(
                _base_event(
                    event_id,
                    nxt,
                    bar_index + 1,
                    data.index[bar_index + 1],
                    era,
                    event_definition="DISPLACEMENT_FAILURE",
                    direction=direction,
                    orientation="reversal",
                )
            )

        for pct in PERCENTILE_THRESHOLDS:
            if np.isfinite(row.body_atr_pct) and row.body_atr_pct >= pct:
                event_id += 1
                ev = _base_event(
                    event_id,
                    row,
                    bar_index,
                    timestamp,
                    era,
                    event_definition=f"DISPLACEMENT_PCT_{int(pct*100)}",
                    direction=direction,
                )
                ev["percentile_threshold"] = pct
                events.append(ev)

    events_df = pd.DataFrame(events)
    if events_df.empty:
        return pd.DataFrame(
            columns=[
                "event_id",
                "timestamp",
                "bar_index",
                "era",
                "event_definition",
                "direction",
                "orientation",
                "body_atr24",
                "strength_bucket",
                "close",
                "atr24",
            ]
        )
    return attach_forward_outcomes(data, events_df)
