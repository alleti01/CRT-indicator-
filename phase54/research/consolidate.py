"""Causal episode consolidation families E0, A–F."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _sorted_events(events: pd.DataFrame) -> pd.DataFrame:
    return events.sort_values("timestamp_ct").reset_index(drop=True)


def consolidate_e0(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Raw — every event is its own episode."""
    ev = _sorted_events(events)
    retained = ev.copy()
    retained["episode_id"] = [f"EP-{i:07d}" for i in range(len(retained))]
    retained["suppressed"] = False
    suppressed = ev.iloc[0:0].copy()
    return retained, suppressed


def consolidate_time(events: pd.DataFrame, window_min: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    ev = _sorted_events(events)
    retained_rows: list[dict] = []
    suppressed_rows: list[dict] = []
    last_start: dict[str, pd.Timestamp] = {}
    ep = 0
    for _, row in ev.iterrows():
        d = row["direction"]
        ts = pd.Timestamp(row["timestamp_ct"])
        start_new = True
        if d in last_start:
            gap = (ts - last_start[d]).total_seconds() / 60.0
            if gap <= window_min:
                start_new = False
        r = row.to_dict()
        if start_new:
            ep += 1
            r["episode_id"] = f"EP-{ep:07d}"
            r["suppressed"] = False
            retained_rows.append(r)
            last_start[d] = ts
        else:
            r["suppressed"] = True
            suppressed_rows.append(r)
    return pd.DataFrame(retained_rows), pd.DataFrame(suppressed_rows)


def consolidate_opposite_reset(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Family C — opposite HQ event resets; same-dir suppressed until opposite."""
    ev = _sorted_events(events)
    retained_rows: list[dict] = []
    suppressed_rows: list[dict] = []
    active_dir: str | None = None
    ep = 0
    for _, row in ev.iterrows():
        d = row["direction"]
        r = row.to_dict()
        if active_dir is None or d != active_dir:
            ep += 1
            r["episode_id"] = f"EP-{ep:07d}"
            r["suppressed"] = False
            retained_rows.append(r)
            active_dir = d
        else:
            r["suppressed"] = True
            suppressed_rows.append(r)
    return pd.DataFrame(retained_rows), pd.DataFrame(suppressed_rows)


def consolidate_structural_reset(events: pd.DataFrame, use_reversal_flag: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Family B — reset on is_reversal or opposite direction event type."""
    ev = _sorted_events(events)
    retained_rows: list[dict] = []
    suppressed_rows: list[dict] = []
    active_dir: str | None = None
    ep = 0
    for _, row in ev.iterrows():
        d = row["direction"]
        r = row.to_dict()
        reset = active_dir is not None and d != active_dir
        if use_reversal_flag and row.get("is_reversal", 0) == 1 and active_dir is not None:
            reset = True
        if active_dir is None or reset or d != active_dir:
            ep += 1
            r["episode_id"] = f"EP-{ep:07d}"
            r["suppressed"] = False
            retained_rows.append(r)
            active_dir = d
        else:
            r["suppressed"] = True
            suppressed_rows.append(r)
    return pd.DataFrame(retained_rows), pd.DataFrame(suppressed_rows)


def consolidate_time_structure(events: pd.DataFrame, window_min: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Family D — new same-dir episode needs time gap OR opposite between."""
    ev = _sorted_events(events)
    retained_rows: list[dict] = []
    suppressed_rows: list[dict] = []
    active_dir: str | None = None
    last_start: pd.Timestamp | None = None
    ep = 0
    for _, row in ev.iterrows():
        d = row["direction"]
        ts = pd.Timestamp(row["timestamp_ct"])
        r = row.to_dict()
        start_new = active_dir is None or d != active_dir
        if not start_new and last_start is not None:
            gap = (ts - last_start).total_seconds() / 60.0
            if gap > window_min:
                start_new = True
        if start_new:
            ep += 1
            r["episode_id"] = f"EP-{ep:07d}"
            r["suppressed"] = False
            retained_rows.append(r)
            active_dir = d
            last_start = ts
        else:
            r["suppressed"] = True
            suppressed_rows.append(r)
    return pd.DataFrame(retained_rows), pd.DataFrame(suppressed_rows)


def consolidate_price_sep(events: pd.DataFrame, atr_mult: float, m1_close: np.ndarray | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Family E — new same-dir episode after price moved atr_mult * ATR from last entry."""
    ev = _sorted_events(events)
    retained_rows: list[dict] = []
    suppressed_rows: list[dict] = []
    last_entry_px: dict[str, float] = {}
    active_dir: str | None = None
    ep = 0
    for _, row in ev.iterrows():
        d = row["direction"]
        r = row.to_dict()
        i = int(row["entry_i"])
        if m1_close is not None:
            px = float(m1_close[i])
        else:
            px = float(row.get("break_dist_atr", 0))  # fallback
        atr = float(row.get("atr", np.nan))
        start_new = active_dir is None or d != active_dir
        if not start_new and np.isfinite(atr) and atr > 0 and d in last_entry_px:
            if abs(px - last_entry_px[d]) / atr >= atr_mult:
                start_new = True
            else:
                start_new = False
        if start_new:
            ep += 1
            r["episode_id"] = f"EP-{ep:07d}"
            r["suppressed"] = False
            retained_rows.append(r)
            last_entry_px[d] = px
            active_dir = d
        else:
            r["suppressed"] = True
            suppressed_rows.append(r)
    return pd.DataFrame(retained_rows), pd.DataFrame(suppressed_rows)


def consolidate_state_machine(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Family F — NEUTRAL / LONG_EPISODE / SHORT_EPISODE."""
    return consolidate_opposite_reset(events)


CONSOLIDATORS = {
    "E0": lambda ev, **_: consolidate_e0(ev),
    "A": lambda ev, window_min=15, **_: consolidate_time(ev, window_min),
    "B": lambda ev, **_: consolidate_structural_reset(ev),
    "C": lambda ev, **_: consolidate_opposite_reset(ev),
    "D": lambda ev, window_min=15, **_: consolidate_time_structure(ev, window_min),
    "E": lambda ev, atr_mult=1.0, m1_close=None, **_: consolidate_price_sep(ev, atr_mult, m1_close),
    "F": lambda ev, **_: consolidate_state_machine(ev),
}


def apply_consolidator(family: str, events: pd.DataFrame, **kwargs) -> tuple[pd.DataFrame, pd.DataFrame]:
    fn = CONSOLIDATORS[family]
    return fn(events, **kwargs)
