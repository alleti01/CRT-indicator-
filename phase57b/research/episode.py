"""Episode consolidation for causal turns — one entry per structural opportunity."""
from __future__ import annotations

import pandas as pd
from phase57.research.episode_control import EpisodeState


def consolidate_turns(
    turns_df: pd.DataFrame,
    window_min: int = 30,
    ts_col: str = "timestamp_ct",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Deduplicate turns: first same-direction turn within window_min."""
    if turns_df.empty:
        return turns_df, pd.DataFrame()
    st = EpisodeState(window_min=window_min)
    retained, suppressed = [], []
    for _, row in turns_df.sort_values("entry_i").iterrows():
        ts = pd.Timestamp(row[ts_col]) if ts_col in row.index else pd.Timestamp(row.get("timestamp_ct", "2000-01-01"))
        # Use entry bar timestamp for episode timing
        if "entry_i" in row.index:
            ts = row.get("timestamp_ct", ts)
        act = st.process(ts, row["direction"])
        r = row.to_dict()
        r.update(act)
        (retained if act["new_episode"] else suppressed).append(r)
    return pd.DataFrame(retained), pd.DataFrame(suppressed)
