"""Forward magnitude and directional outcomes from event bar close."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import HORIZONS


def compute_forward(data: pd.DataFrame, row: pd.Series) -> dict:
    metrics: dict = {}
    idx = int(row.bar_index)
    if idx >= len(data) - 1:
        return metrics
    atr = float(row.atr) if np.isfinite(row.atr) and row.atr > 0 else np.nan
    if not np.isfinite(atr) or atr <= 0:
        return metrics

    event_close = float(row.close)
    direction = str(row.transition_direction)
    sign = 1 if direction == "UP" else (-1 if direction == "DOWN" else 0)
    highs = data["high"].to_numpy(dtype=float)
    lows = data["low"].to_numpy(dtype=float)
    closes = data["close"].to_numpy(dtype=float)
    returns = data["returns"].to_numpy(dtype=float)

    for horizon in HORIZONS:
        end_idx = min(idx + horizon, len(data) - 1)
        if end_idx <= idx:
            continue
        window_high = float(highs[idx + 1 : end_idx + 1].max())
        window_low = float(lows[idx + 1 : end_idx + 1].min())
        end_close = float(closes[end_idx])
        raw = end_close - event_close
        signed_atr = raw / atr
        abs_atr = abs(raw) / atr
        window_returns = returns[idx + 1 : end_idx + 1]
        window_returns = window_returns[np.isfinite(window_returns)]
        future_rv = float(window_returns.std()) if len(window_returns) >= 2 else float("nan")
        cum_tr = float(np.nansum(data["true_range"].to_numpy()[idx + 1 : end_idx + 1])) / atr

        metrics[f"signed_return_atr_{horizon}"] = signed_atr
        metrics[f"abs_return_atr_{horizon}"] = abs_atr
        metrics[f"mfe_atr_{horizon}"] = (window_high - event_close) / atr
        metrics[f"mae_atr_{horizon}"] = (event_close - window_low) / atr
        metrics[f"future_rv_{horizon}"] = future_rv
        metrics[f"cumulative_tr_atr_{horizon}"] = cum_tr

        if sign == 0:
            metrics[f"continuation_atr_{horizon}"] = signed_atr
            metrics[f"reversal_atr_{horizon}"] = -signed_atr
        elif sign > 0:
            metrics[f"continuation_atr_{horizon}"] = signed_atr
            metrics[f"reversal_atr_{horizon}"] = -signed_atr
        else:
            metrics[f"continuation_atr_{horizon}"] = -signed_atr
            metrics[f"reversal_atr_{horizon}"] = signed_atr

    return metrics


def attach_forward_outcomes(data: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, event in events.iterrows():
        payload = event.to_dict()
        payload.update(compute_forward(data, event))
        rows.append(payload)
    return pd.DataFrame(rows)


def compute_unconditional_baselines(data: pd.DataFrame, *, era_mask: pd.Series | None = None) -> pd.DataFrame:
    rows = []
    indices = np.arange(len(data))
    if era_mask is not None:
        indices = indices[era_mask.to_numpy()]
    pseudo = pd.DataFrame(
        {
            "bar_index": indices,
            "close": data["close"].iloc[indices].to_numpy(),
            "atr": data["atr_24"].iloc[indices].to_numpy(),
            "transition_direction": data["transition_direction"].iloc[indices].to_numpy(),
        }
    )
    enriched = attach_forward_outcomes(data, pseudo)
    for horizon in HORIZONS:
        signed = enriched[f"signed_return_atr_{horizon}"].astype(float)
        absolute = enriched[f"abs_return_atr_{horizon}"].astype(float)
        signed = signed[np.isfinite(signed)]
        absolute = absolute[np.isfinite(absolute)]
        rows.append(
            {
                "horizon": horizon,
                "minutes_approx": horizon * 5,
                "N": len(signed),
                "mean_signed_return_atr": float(signed.mean()) if len(signed) else float("nan"),
                "mean_abs_return_atr": float(absolute.mean()) if len(absolute) else float("nan"),
                "median_abs_return_atr": float(np.median(absolute)) if len(absolute) else float("nan"),
                "mean_future_rv": float(enriched[f"future_rv_{horizon}"].astype(float).mean()),
                "mean_mfe_atr": float(enriched[f"mfe_atr_{horizon}"].astype(float).mean()),
                "mean_mae_atr": float(enriched[f"mae_atr_{horizon}"].astype(float).mean()),
                "mean_cumulative_tr_atr": float(enriched[f"cumulative_tr_atr_{horizon}"].astype(float).mean()),
            }
        )
    return pd.DataFrame(rows)
