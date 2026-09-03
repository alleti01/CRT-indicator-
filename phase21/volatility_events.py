"""Volatility transition and shock event extraction."""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig

from .config import ERAS, EXPANSION_TRANSITIONS, MIN_PRIOR_STATE_BARS, PRIMARY_STATE_MEASURE, REGIME_TRANSITIONS, VOL_MEASURES
from .forward_returns import attach_forward_outcomes
from .volatility_measures import compression_duration_bins, prepare_volatility_frame


def assign_era(timestamp: pd.Timestamp, tz: str) -> str:
    ts = pd.Timestamp(timestamp).tz_convert(tz)
    for era, (start, end) in ERAS.items():
        if pd.Timestamp(start, tz=tz) <= ts <= pd.Timestamp(end, tz=tz):
            return era
    return "outside"


def extract_volatility_events(
    frame: pd.DataFrame,
    config: FrozenConfig,
    *,
    prepared: pd.DataFrame | None = None,
) -> pd.DataFrame:
    data = prepared if prepared is not None else prepare_volatility_frame(frame, config)
    events: List[Dict] = []
    event_id = 0
    shock_active = False

    for measure in VOL_MEASURES:
        data[f"compression_duration_{measure}"] = compression_duration_bins(data[f"state_{measure}"])

    prev_states = {m: "UNKNOWN" for m in VOL_MEASURES}
    prev_primary = "UNKNOWN"
    primary_run = 0
    measure_runs = {m: 0 for m in VOL_MEASURES}

    for bar_index in range(1, len(data)):
        row = data.iloc[bar_index]
        prev = data.iloc[bar_index - 1]
        timestamp = data.index[bar_index]
        era = assign_era(timestamp, config.exchange_timezone)
        if era == "outside":
            if row.primary_state == prev_primary:
                primary_run += 1
            else:
                primary_run = 1
            prev_primary = row.primary_state
            for measure in VOL_MEASURES:
                current = row[f"state_{measure}"]
                if current == prev_states[measure]:
                    measure_runs[measure] += 1
                else:
                    measure_runs[measure] = 1
                prev_states[measure] = current
            shock_active = bool(np.isfinite(row.shock_pct) and row.shock_pct >= 0.80)
            continue

        atr = float(row.atr_24) if np.isfinite(row.atr_24) else np.nan
        body = abs(float(row.close) - float(row.open))
        rng = float(row.high) - float(row.low)
        body_atr = body / atr if np.isfinite(atr) and atr > 0 else np.nan
        range_atr = rng / atr if np.isfinite(atr) and atr > 0 else np.nan
        bar_return_atr = (float(row.close) - float(row.open)) / atr if np.isfinite(atr) and atr > 0 else np.nan
        close_loc = (float(row.close) - float(row.low)) / rng if rng > 0 else 0.5

        if (
            prev_primary != "UNKNOWN"
            and row.primary_state != prev_primary
            and primary_run >= MIN_PRIOR_STATE_BARS
        ):
            transition = f"{prev_primary}->{row.primary_state}"
            if transition in REGIME_TRANSITIONS:
                event_id += 1
                events.append(
                    _base_event(
                        event_id,
                        row,
                        bar_index,
                        timestamp,
                        era,
                        event_family="REGIME_TRANSITION",
                        vol_measure=PRIMARY_STATE_MEASURE,
                        transition=transition,
                        compression_duration="n/a",
                        shock_bin="n/a",
                        compression_pct=float(prev.primary_pct) if np.isfinite(prev.primary_pct) else np.nan,
                        body_atr=body_atr,
                        range_atr=range_atr,
                        bar_return_atr=bar_return_atr,
                        close_location=close_loc,
                    )
                )

        for measure in VOL_MEASURES:
            current = row[f"state_{measure}"]
            previous = prev_states[measure]
            if previous == "LOW" and current != "LOW" and measure_runs[measure] >= MIN_PRIOR_STATE_BARS:
                trans = f"{previous}->{current}"
                if trans in EXPANSION_TRANSITIONS:
                    event_id += 1
                    events.append(
                        _base_event(
                            event_id,
                            row,
                            bar_index,
                            timestamp,
                            era,
                            event_family="COMPRESSION_EXPANSION",
                            vol_measure=measure,
                            transition=trans,
                            compression_duration=str(row[f"compression_duration_{measure}"]),
                            shock_bin="n/a",
                            compression_pct=float(prev[f"pct_{measure}"])
                            if np.isfinite(prev[f"pct_{measure}"])
                            else np.nan,
                            body_atr=body_atr,
                            range_atr=range_atr,
                            bar_return_atr=bar_return_atr,
                            close_location=close_loc,
                        )
                    )
            if current == "LOW" and previous != "LOW":
                event_id += 1
                events.append(
                    _base_event(
                        event_id,
                        row,
                        bar_index,
                        timestamp,
                        era,
                        event_family="COMPRESSION",
                        vol_measure=measure,
                        transition=f"ENTER_{current}",
                        compression_duration="1-3",
                        shock_bin="n/a",
                        compression_pct=float(row[f"pct_{measure}"])
                        if np.isfinite(row[f"pct_{measure}"])
                        else np.nan,
                        body_atr=body_atr,
                        range_atr=range_atr,
                        bar_return_atr=bar_return_atr,
                        close_location=close_loc,
                    )
                )

        shock_now = bool(np.isfinite(row.shock_pct) and row.shock_pct >= 0.80)
        if shock_now and not shock_active:
            event_id += 1
            events.append(
                _base_event(
                    event_id,
                    row,
                    bar_index,
                    timestamp,
                    era,
                    event_family="VOLATILITY_SHOCK",
                    vol_measure="SHOCK_SCORE",
                    transition="SHOCK_ONSET",
                    compression_duration="n/a",
                    shock_bin=str(row.shock_bin),
                    compression_pct=float(row.shock_pct) if np.isfinite(row.shock_pct) else np.nan,
                    body_atr=body_atr,
                    range_atr=range_atr,
                    bar_return_atr=bar_return_atr,
                    close_location=close_loc,
                )
            )
        shock_active = shock_now

        if row.primary_state == prev_primary:
            primary_run += 1
        else:
            primary_run = 1
        prev_primary = row.primary_state
        for measure in VOL_MEASURES:
            current = row[f"state_{measure}"]
            if current == prev_states[measure]:
                measure_runs[measure] += 1
            else:
                measure_runs[measure] = 1
            prev_states[measure] = current

    events_df = pd.DataFrame(events)
    if events_df.empty:
        return events_df
    return attach_forward_outcomes(data, events_df)


def _base_event(
    event_id: int,
    row,
    bar_index: int,
    timestamp,
    era: str,
    *,
    event_family: str,
    vol_measure: str,
    transition: str,
    compression_duration: str,
    shock_bin: str,
    compression_pct: float,
    body_atr: float,
    range_atr: float,
    bar_return_atr: float,
    close_location: float,
) -> Dict:
    return {
        "event_id": event_id,
        "timestamp": timestamp,
        "bar_index": bar_index,
        "era": era,
        "event_family": event_family,
        "vol_measure": vol_measure,
        "transition": transition,
        "compression_duration": compression_duration,
        "shock_percentile_bin": shock_bin,
        "compression_percentile": compression_pct,
        "transition_direction": row.transition_direction,
        "time_bucket": row.time_bucket,
        "close": float(row.close),
        "atr": float(row.atr_24),
        "body_atr": body_atr,
        "range_atr": range_atr,
        "bar_return_atr": bar_return_atr,
        "close_location": close_location,
    }
