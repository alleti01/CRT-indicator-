"""Forward direction-normalized outcomes from signal bar close."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import HORIZONS


def directional_multiplier(direction: str, raw_atr: float) -> float:
    if direction == "BULLISH":
        return raw_atr
    if direction == "BEARISH":
        return -raw_atr
    return raw_atr


def compute_forward(data: pd.DataFrame, row: pd.Series, *, direction: str, orientation: str = "continuation") -> dict:
    metrics: dict = {}
    idx = int(row.bar_index)
    if idx >= len(data) - 1:
        return metrics
    atr = float(row.atr24) if np.isfinite(row.atr24) and row.atr24 > 0 else float("nan")
    if not np.isfinite(atr) or atr <= 0:
        return metrics

    event_close = float(row.close)
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
        raw_points = end_close - event_close
        raw_atr = raw_points / atr
        cont = directional_multiplier(direction, raw_atr)
        rev = -cont
        metrics[f"raw_points_{horizon}"] = raw_points
        metrics[f"signed_return_atr_{horizon}"] = raw_atr
        metrics[f"directional_atr_{horizon}"] = cont if orientation == "continuation" else rev
        if direction == "BULLISH":
            metrics[f"mfe_atr_{horizon}"] = (window_high - event_close) / atr
            metrics[f"mae_atr_{horizon}"] = (event_close - window_low) / atr
        elif direction == "BEARISH":
            metrics[f"mfe_atr_{horizon}"] = (event_close - window_low) / atr
            metrics[f"mae_atr_{horizon}"] = (window_high - event_close) / atr
        else:
            metrics[f"mfe_atr_{horizon}"] = float("nan")
            metrics[f"mae_atr_{horizon}"] = float("nan")
    return metrics


def attach_forward_outcomes(data: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, event in events.iterrows():
        payload = event.to_dict()
        payload.update(
            compute_forward(
                data,
                event,
                direction=str(event.direction),
                orientation=str(event.get("orientation", "continuation")),
            )
        )
        rows.append(payload)
    return pd.DataFrame(rows)
