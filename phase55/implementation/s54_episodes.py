"""Phase54 Family A episode state — causal 30-minute same-direction consolidation."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from phase54.research.consolidate import _sorted_events, consolidate_time
from phase55.config import S54_TIME_WINDOW_MIN


@dataclass
class S54EpisodeState:
    window_min: int = S54_TIME_WINDOW_MIN
    last_start: dict[str, pd.Timestamp] = field(default_factory=dict)
    episode_counter: int = 0
    suppressed_count: int = 0

    def reset(self) -> None:
        self.last_start.clear()
        self.episode_counter = 0
        self.suppressed_count = 0

    def process(self, ts: pd.Timestamp, direction: str) -> dict:
        """Return episode action for one D10-qualified event."""
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
                "episode_id": f"EP-{self.episode_counter:07d}",
                "suppressed": False,
                "s54_entry": True,
            }
        self.suppressed_count += 1
        return {
            "episode_id": None,
            "suppressed": True,
            "s54_entry": False,
        }


def build_d10_order_map(d10: pd.DataFrame) -> dict[str, int]:
    """Global frozen iteration rank — must not filter D10 before sorting."""
    ordered = episode_event_order(d10)
    return {str(eid): i for i, eid in enumerate(ordered["event_id"].astype(str))}


def episode_event_order(d10: pd.DataFrame) -> pd.DataFrame:
    """Exact frozen Phase54 iteration order (parquet D10 row order within timestamp ties)."""
    return _sorted_events(d10)


def consolidate_batch(events: pd.DataFrame, window_min: int = S54_TIME_WINDOW_MIN) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Do not pre-sort — consolidate_time applies frozen _sorted_events internally."""
    return consolidate_time(events, window_min)


def apply_episode_state(d10: pd.DataFrame, state: S54EpisodeState | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sequential episode pass matching consolidate_time decisions."""
    state = state or S54EpisodeState()
    retained_rows: list[dict] = []
    suppressed_rows: list[dict] = []
    for _, row in episode_event_order(d10).iterrows():
        act = state.process(row["timestamp_ct"], row["direction"])
        r = row.to_dict()
        r.update(act)
        if act["s54_entry"]:
            retained_rows.append(r)
        else:
            suppressed_rows.append(r)
    return pd.DataFrame(retained_rows), pd.DataFrame(suppressed_rows)
