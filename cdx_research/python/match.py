"""Match screenshot labels to NQ 1m bars. Never invent missing bars."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "signal_labels.csv"


def load_labels(path: Path | None = None) -> pd.DataFrame:
    df = pd.read_csv(path or LABELS)
    df["signal_time_et"] = pd.to_datetime(df["signal_time_et"])
    return df


def match_labels(labels: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    if m1.index.tz is None:
        raise ValueError("m1 index must be timezone-aware")
    rows = []
    m1_et = m1.copy()
    m1_et.index = m1.index.tz_convert("America/New_York")
    data_min = m1_et.index.min()
    data_max = m1_et.index.max()
    for rec in labels.itertuples(index=False):
        ts = rec.signal_time_et
        if ts.tzinfo is None:
            ts = ts.tz_localize("America/New_York")
        else:
            ts = ts.tz_convert("America/New_York")
        ts = ts.replace(second=0, microsecond=0)
        in_range = bool(data_min <= ts <= data_max)
        exact = ts in m1_et.index
        row = {
            "screenshot_id": rec.screenshot_id,
            "date": rec.date,
            "signal_time_et": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "direction": rec.direction,
            "timestamp_confidence": rec.timestamp_confidence,
            "approximate_price": rec.approximate_price,
            "outcome_visible": rec.outcome_visible,
            "visible_R": rec.visible_R,
            "notes": rec.notes,
            "data_in_range": in_range,
            "exact_bar_found": exact,
            "match_status": "MATCHED" if exact else ("OUT_OF_RANGE" if not in_range else "NO_EXACT_BAR"),
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "volume": None,
        }
        if exact:
            bar = m1_et.loc[ts]
            row.update(
                {
                    "open": float(bar["open"]),
                    "high": float(bar["high"]),
                    "low": float(bar["low"]),
                    "close": float(bar["close"]),
                    "volume": float(bar["volume"]),
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def context_windows(matched: pd.DataFrame, m1: pd.DataFrame, before: int = 100, after: int = 20) -> pd.DataFrame:
    """Store context around MATCHED bars only. After-bars are outcome-only."""
    if matched.empty or not (matched["match_status"] == "MATCHED").any():
        return pd.DataFrame()
    m1_et = m1.copy()
    m1_et.index = m1.index.tz_convert("America/New_York")
    chunks = []
    for rec in matched[matched["match_status"] == "MATCHED"].itertuples(index=False):
        ts = pd.Timestamp(rec.signal_time_et).tz_localize("America/New_York")
        loc = m1_et.index.get_loc(ts)
        start = max(0, int(loc) - before)
        end = min(len(m1_et), int(loc) + after + 1)
        win = m1_et.iloc[start:end][["open", "high", "low", "close", "volume"]].copy()
        win["screenshot_id"] = rec.screenshot_id
        win["signal_time_et"] = rec.signal_time_et
        win["direction"] = rec.direction
        win["offset"] = range(start - int(loc), start - int(loc) + len(win))
        win["role"] = ["PRE" if o < 0 else ("SIGNAL" if o == 0 else "POST_OUTCOME_ONLY") for o in win["offset"]]
        chunks.append(win.reset_index())
    return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
