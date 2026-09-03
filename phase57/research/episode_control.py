"""Phase57 episode consolidation — prevent counting the same move multiple times."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class EpisodeState:
    """Per-direction time-window deduplication (adapted from Phase54 Family A)."""

    window_min: int = 30
    last_start: dict[str, pd.Timestamp] = field(default_factory=dict)
    episode_counter: int = 0
    suppressed_count: int = 0

    def reset(self) -> None:
        self.last_start.clear()
        self.episode_counter = 0
        self.suppressed_count = 0

    def process(self, ts: pd.Timestamp, direction: str) -> dict:
        d = direction
        start_new = True
        if d in self.last_start:
            gap = (pd.Timestamp(ts) - self.last_start[d]).total_seconds() / 60.0
            if gap <= self.window_min:
                start_new = False
        if start_new:
            self.episode_counter += 1
            self.last_start[d] = pd.Timestamp(ts)
            return {
                "episode_id": f"P57-EP-{self.episode_counter:07d}",
                "suppressed": False,
                "new_episode": True,
            }
        self.suppressed_count += 1
        return {"episode_id": None, "suppressed": True, "new_episode": False}


def consolidate_events(
    events: pd.DataFrame,
    window_min: int = 30,
    ts_col: str = "timestamp_ct",
    dir_col: str = "direction",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split events into retained (first per episode) and suppressed."""
    st = EpisodeState(window_min=window_min)
    retained, suppressed = [], []
    for _, row in events.sort_values(ts_col).iterrows():
        act = st.process(row[ts_col], row[dir_col])
        r = row.to_dict()
        r.update(act)
        (retained if act["new_episode"] else suppressed).append(r)
    return pd.DataFrame(retained), pd.DataFrame(suppressed)
