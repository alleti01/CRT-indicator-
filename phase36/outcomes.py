"""Post-hoc outcome scoring for replay signals — no influence on signal generation."""

from __future__ import annotations

import numpy as np
import pandas as pd


def score_outcomes(signals: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    pos = {ts: i for i, ts in enumerate(market.index)}
    rows = []
    for sig in signals.itertuples(index=False):
        ts = pd.Timestamp(sig.marker_bar_timestamp)
        if ts not in pos:
            continue
        entry_i = pos[ts]
        entry_px = float(sig.entry_price)
        stop = float(sig.stop)
        target = float(sig.target)
        direction = 1 if str(sig.direction).lower() == "long" else -1
        max_bars = 4 if sig.signal_type in ("L", "S") else 3
        risk = abs(entry_px - stop)
        if risk <= 0:
            risk = 1e-9
        mfe = mae = 0.0
        exit_type = "DATA_END"
        exit_ts = ts
        exit_px = entry_px
        realized_r = 0.0
        for elapsed, j in enumerate(range(entry_i + 1, len(market)), start=1):
            bar = market.iloc[j]
            hi, lo, close = float(bar.high), float(bar.low), float(bar.close)
            if direction == 1:
                bar_mfe = (hi - entry_px) / risk
                bar_mae = (entry_px - lo) / risk
                hit_stop = lo <= stop
                hit_tgt = hi >= target
            else:
                bar_mfe = (entry_px - lo) / risk
                bar_mae = (hi - entry_px) / risk
                hit_stop = hi >= stop
                hit_tgt = lo <= target
            mfe = max(mfe, bar_mfe)
            mae = max(mae, bar_mae)
            if hit_stop:
                exit_type = "STOP"
                exit_ts = market.index[j]
                exit_px = stop
                realized_r = (stop - entry_px) / risk if direction == 1 else (entry_px - stop) / risk
                break
            if hit_tgt:
                exit_type = "TARGET"
                exit_ts = market.index[j]
                exit_px = target
                target_r = 3.0 if sig.signal_type in ("L", "S") else 2.5
                realized_r = target_r
                break
            if elapsed >= max_bars:
                exit_type = "TIME"
                exit_ts = market.index[j]
                exit_px = close
                realized_r = (close - entry_px) / risk if direction == 1 else (entry_px - close) / risk
                break
        rows.append(
            {
                "signal_id": sig.signal_id,
                "marker_bar_timestamp": ts,
                "signal_type": sig.signal_type,
                "exit_type": exit_type,
                "exit_timestamp": exit_ts,
                "exit_price": exit_px,
                "realized_R": realized_r,
                "MFE_R": mfe,
                "MAE_R": mae,
            }
        )
    return pd.DataFrame(rows)
