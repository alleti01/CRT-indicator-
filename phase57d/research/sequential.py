"""Sequential replay engine — chronological processing without future arrays."""

from __future__ import annotations

from typing import Iterator, Optional

import pandas as pd

from phase57d.research.execution import CausalExecutionModel
from phase57d.research.interactions import CausalInteractionDetector, interactions_to_df
from phase57d.research.interfaces import OptionsSnapshot
from phase57d.research.wall_snapshot import WallSnapshotEngine, snapshots_to_df


class SequentialReplayEngine:
    """Process options snapshots + underlying bars in chronological order."""

    def __init__(
        self,
        wall_engine: Optional[WallSnapshotEngine] = None,
        interaction_detector: Optional[CausalInteractionDetector] = None,
        execution_model: Optional[CausalExecutionModel] = None,
    ):
        self.wall_engine = wall_engine or WallSnapshotEngine()
        self.interactions = interaction_detector or CausalInteractionDetector()
        self.execution = execution_model or CausalExecutionModel()
        self._interaction_log: list[dict] = []
        self._wall_log: list = []

    def replay(
        self,
        bars: pd.DataFrame,
        snapshots: Iterator[OptionsSnapshot],
        atr_series: pd.Series,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Replay snapshots interleaved with closed underlying bars."""
        snap_list = sorted(snapshots, key=lambda s: s.known_at)
        snap_idx = 0
        n_snaps = len(snap_list)

        for bar_i, (ts, bar) in enumerate(bars.iterrows()):
            while snap_idx < n_snaps and snap_list[snap_idx].known_at <= ts:
                snap = snap_list[snap_idx]
                atr = float(atr_series.get(ts, atr_series.iloc[max(0, bar_i - 1)]))
                emitted = self.wall_engine.process_snapshot(snap, atr)
                self._wall_log.extend(emitted)
                snap_idx += 1

            atr = float(atr_series.get(ts, bar.get("atr", 1.0)))
            active = self.wall_engine.active_walls_at(ts)
            events = self.interactions.update(bar, bar_i, ts, active, atr)
            self._interaction_log.extend(events)

        walls_df = snapshots_to_df(self._wall_log)
        inter_df = interactions_to_df(self._interaction_log)
        return walls_df, inter_df

    def compare_batch(
        self,
        batch_walls: pd.DataFrame,
        batch_interactions: pd.DataFrame,
    ) -> dict:
        """Compare sequential vs batch outputs for parity check."""
        seq_walls = snapshots_to_df(self._wall_log)
        seq_inter = interactions_to_df(self._interaction_log)

        wall_parity = True
        if not batch_walls.empty and not seq_walls.empty:
            wall_parity = (
                len(batch_walls) == len(seq_walls)
                and set(batch_walls["wall_id"]) == set(seq_walls["wall_id"])
            )
        elif batch_walls.empty and seq_walls.empty:
            wall_parity = True
        else:
            wall_parity = False

        inter_parity = True
        if not batch_interactions.empty and not seq_inter.empty:
            inter_parity = (
                len(batch_interactions) == len(seq_inter)
                and set(batch_interactions["interaction_id"])
                == set(seq_inter["interaction_id"])
            )
        elif batch_interactions.empty and seq_inter.empty:
            inter_parity = True
        else:
            inter_parity = False

        return {
            "wall_parity": wall_parity,
            "interaction_parity": inter_parity,
            "sequential_parity": wall_parity and inter_parity,
            "batch_walls": len(batch_walls),
            "seq_walls": len(seq_walls),
            "batch_interactions": len(batch_interactions),
            "seq_interactions": len(seq_inter),
        }
