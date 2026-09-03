"""Episode consolidation — one opportunity per wall interaction arc."""

from __future__ import annotations

import hashlib

import pandas as pd

from phase57d.config import EPISODE_RESET_ATR, EPISODE_WINDOW_MIN


def _episode_id(wall_id: str, first_ts: pd.Timestamp) -> str:
    raw = f"{wall_id}|{first_ts.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class WallEpisodeEngine:
    """Consolidate repeated bars near same unresolved wall into one episode."""

    def __init__(
        self,
        window_min: int = EPISODE_WINDOW_MIN,
        reset_atr: float = EPISODE_RESET_ATR,
    ):
        self.window_min = window_min
        self.reset_atr = reset_atr

    def consolidate(self, interactions: pd.DataFrame) -> pd.DataFrame:
        if interactions.empty:
            interactions = interactions.copy()
            interactions["episode_id"] = pd.Series(dtype=str)
            interactions["is_distinct"] = pd.Series(dtype=bool)
            return interactions

        df = interactions.sort_values(
            ["wall_id", "signal_timestamp", "interaction_id"]
        ).copy()
        df["episode_id"] = ""
        df["is_distinct"] = False

        for wall_id, grp in df.groupby("wall_id", sort=False):
            episode_start = None
            last_ts = None
            eid = None
            for idx, row in grp.iterrows():
                ts = pd.Timestamp(row["signal_timestamp"])
                if episode_start is None:
                    episode_start = ts
                    eid = _episode_id(wall_id, ts)
                    df.at[idx, "is_distinct"] = True
                else:
                    gap = (ts - last_ts).total_seconds() / 60.0
                    if gap > self.window_min:
                        episode_start = ts
                        eid = _episode_id(wall_id, ts)
                        df.at[idx, "is_distinct"] = True
                df.at[idx, "episode_id"] = eid
                last_ts = ts

        return df

    def distinct_episodes(self, interactions: pd.DataFrame) -> pd.DataFrame:
        consolidated = self.consolidate(interactions)
        return consolidated[consolidated["is_distinct"]].copy()
