"""Early no-movement exit tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import STATIC_EXIT_GRID
from .paths import max_hold_bars, target_r


def simulate_static_exit(sig, market: pd.DataFrame, pos: dict, *, check_bar: int, min_mfe_r: float) -> dict:
    ts = pd.Timestamp(sig.marker_bar_timestamp)
    if ts not in pos:
        return {}
    entry_i = pos[ts]
    entry_px = float(sig.entry_price)
    stop = float(sig.stop)
    target = float(sig.target)
    st = str(sig.signal_type)
    direction = 1 if str(sig.direction).lower() == "long" else -1
    risk = abs(entry_px - stop) or 1e-9
    max_bars = max_hold_bars(st)
    tgt = target_r(st)
    mfe = 0.0

    for elapsed, j in enumerate(range(entry_i + 1, len(market)), start=1):
        bar = market.iloc[j]
        hi, lo, cl = float(bar.high), float(bar.low), float(bar.close)
        if direction == 1:
            bar_mfe = (hi - entry_px) / risk
            hit_stop = lo <= stop
            hit_tgt = hi >= target
        else:
            bar_mfe = (entry_px - lo) / risk
            hit_stop = hi >= stop
            hit_tgt = lo <= target
        mfe = max(mfe, bar_mfe)
        if elapsed == check_bar and mfe < min_mfe_r:
            realized = (cl - entry_px) / risk * direction
            return {"realized_R": realized, "exit_type": "STATIC_EXIT", "bars_held": elapsed}
        if hit_stop:
            return {"realized_R": -1.0, "exit_type": "STOP", "bars_held": elapsed}
        if hit_tgt:
            return {"realized_R": tgt, "exit_type": "TARGET", "bars_held": elapsed}
        if elapsed >= max_bars:
            realized = (cl - entry_px) / risk * direction
            return {"realized_R": realized, "exit_type": "TIME", "bars_held": elapsed}
    return {"realized_R": 0.0, "exit_type": "DATA_END", "bars_held": 0}


def static_exit_comparison(signals: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    pos = {ts: i for i, ts in enumerate(market.index)}
    rows = []
    for sig in signals.itertuples(index=False):
        base = simulate_static_exit(sig, market, pos, check_bar=999, min_mfe_r=-1)
        rows.append(
            {
                "signal_id": sig.signal_id,
                "signal_type": sig.signal_type,
                "rule": "FROZEN",
                "realized_R": base.get("realized_R", np.nan),
            }
        )
        for check_bar, min_mfe in STATIC_EXIT_GRID:
            r = simulate_static_exit(sig, market, pos, check_bar=check_bar, min_mfe_r=min_mfe)
            rows.append(
                {
                    "signal_id": sig.signal_id,
                    "signal_type": sig.signal_type,
                    "rule": f"exit_if_bar{check_bar}_mfe_lt_{min_mfe}",
                    "realized_R": r.get("realized_R", np.nan),
                }
            )
    return pd.DataFrame(rows)
