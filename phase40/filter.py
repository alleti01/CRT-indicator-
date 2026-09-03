"""Impulse filter — causal entry-bar calculation matching Phase 39."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import IMPULSE_THRESHOLD


def compute_impulse_3bar(market: pd.DataFrame) -> pd.Series:
    """abs(close - close[3]) / ATR — same as phase35.features.build_features."""
    atr = market["atr"].astype(float)
    impulse = (market["close"].astype(float) - market["close"].shift(3)).abs() / atr.replace(0, np.nan)
    return impulse.rename("impulse_3bar")


def attach_entry_impulse(signals: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    """Attach impulse and filter fields at frozen entry bar."""
    impulse = compute_impulse_3bar(market)
    pos = {ts: i for i, ts in enumerate(market.index)}

    rows = []
    for sig in signals.itertuples(index=False):
        ts = pd.Timestamp(sig.marker_bar_timestamp)
        if ts not in pos:
            continue
        i = pos[ts]
        bar = market.iloc[i]
        imp = float(impulse.iloc[i]) if np.isfinite(impulse.iloc[i]) else np.nan
        close_3 = float(market.iloc[i - 3]["close"]) if i >= 3 else np.nan
        accepted = bool(np.isfinite(imp) and imp >= IMPULSE_THRESHOLD)
        rows.append(
            {
                "signal_id": sig.signal_id,
                "marker_bar_timestamp": ts,
                "timestamp_ct": getattr(sig, "timestamp_ct", ts),
                "signal_type": sig.signal_type,
                "direction": sig.direction,
                "entry_price": float(sig.entry_price),
                "stop": float(sig.stop),
                "target": float(sig.target),
                "atr": float(bar.atr),
                "close": float(bar.close),
                "close_3": close_3,
                "impulse_3bar": imp,
                "filter_threshold": IMPULSE_THRESHOLD,
                "accepted": accepted,
                "reject_reason": "" if accepted else "IMPULSE_FILTER",
                "architecture": getattr(sig, "architecture", ""),
                "candidate_id": getattr(sig, "candidate_id", np.nan),
                "event_id": getattr(sig, "event_id", ""),
            }
        )
    return pd.DataFrame(rows)


def apply_filter(signals: pd.DataFrame, market: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (all_with_filter, accepted, rejected)."""
    all_sig = attach_entry_impulse(signals, market)
    accepted = all_sig.loc[all_sig["accepted"]].copy()
    rejected = all_sig.loc[~all_sig["accepted"]].copy()
    return all_sig, accepted, rejected
