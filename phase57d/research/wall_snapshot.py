"""Causal wall snapshot engine — maintains valid_from/valid_until lifecycle."""

from __future__ import annotations

from typing import Iterator, Optional

import pandas as pd

from phase57d.config import METHOD_VERSION
from phase57d.research.interfaces import OptionsSnapshot, WallCalculator, WallSnapshot
from phase57d.research.schema import WALL_CATALOG_COLUMNS, WALL_SNAPSHOT_COLUMNS
from phase57d.research.wall_calculator import all_calculators


def snapshots_to_df(walls: list[WallSnapshot]) -> pd.DataFrame:
    if not walls:
        return pd.DataFrame(columns=WALL_SNAPSHOT_COLUMNS)
    rows = [
        {
            "timestamp": w.timestamp,
            "underlying": w.underlying,
            "mapping": w.mapping,
            "wall_family": w.wall_family,
            "wall_id": w.wall_id,
            "strike": w.strike,
            "wall_value": w.wall_value,
            "wall_rank": w.wall_rank,
            "wall_strength_percentile": w.wall_strength_percentile,
            "expiration_bucket": w.expiration_bucket,
            "spot": w.spot,
            "distance_from_spot": w.distance_from_spot,
            "distance_atr": w.distance_atr,
            "source_snapshot_timestamp": w.source_snapshot_timestamp,
            "valid_from": w.valid_from,
            "valid_until": w.valid_until,
            "method_version": w.method_version,
        }
        for w in walls
    ]
    return pd.DataFrame(rows)


class WallSnapshotEngine:
    """Process options snapshots chronologically; emit wall candidates."""

    def __init__(
        self,
        calculators: Optional[list[WallCalculator]] = None,
        expiration_scopes: tuple[str, ...] = ("0-5D", "0-14D", "<=30D"),
    ):
        self.calculators = calculators or all_calculators()
        self.expiration_scopes = expiration_scopes
        self._active: dict[str, WallSnapshot] = {}
        self._history: list[WallSnapshot] = []

    def process_snapshot(
        self,
        snapshot: OptionsSnapshot,
        atr: float,
    ) -> list[WallSnapshot]:
        """Ingest one causal snapshot; return newly emitted walls."""
        emitted: list[WallSnapshot] = []
        ts = snapshot.known_at
        for calc in self.calculators:
            for scope in self.expiration_scopes:
                walls = calc.compute(snapshot, atr, scope)
                for w in walls:
                    self._active[w.wall_id] = w
                    self._history.append(w)
                    emitted.append(w)
        # Invalidate prior walls from same family/mapping when superseded
        for wid, w in list(self._active.items()):
            if w.valid_until is None and w.valid_from < ts:
                same_family = [
                    x for x in emitted
                    if x.wall_family == w.wall_family
                    and x.mapping == w.mapping
                    and x.expiration_bucket == w.expiration_bucket
                ]
                if same_family and w.wall_id not in {x.wall_id for x in same_family}:
                    self._active[wid] = WallSnapshot(
                        **{**w.__dict__, "valid_until": ts}
                    )
        return emitted

    def active_walls_at(self, ts: pd.Timestamp) -> list[WallSnapshot]:
        out = []
        for w in self._active.values():
            if w.valid_from <= ts and (w.valid_until is None or w.valid_until > ts):
                out.append(w)
        return sorted(out, key=lambda x: (x.wall_family, x.wall_rank))

    def run(
        self,
        snapshots: Iterator[OptionsSnapshot],
        atr_lookup: callable,
    ) -> pd.DataFrame:
        for snap in snapshots:
            atr = atr_lookup(snap.timestamp)
            self.process_snapshot(snap, atr)
        return snapshots_to_df(self._history)

    def build_catalog(self, snapshots_df: pd.DataFrame) -> pd.DataFrame:
        if snapshots_df.empty:
            return pd.DataFrame(columns=WALL_CATALOG_COLUMNS)
        cat = snapshots_df.copy()
        grp = cat.groupby("wall_id").agg(
            first_seen=("valid_from", "min"),
            last_seen=("timestamp", "max"),
            persistence_bars=("timestamp", "count"),
        )
        cat = cat.merge(grp, on="wall_id", how="left")
        cat = cat.drop_duplicates("wall_id", keep="last")
        return cat[WALL_CATALOG_COLUMNS] if all(c in cat.columns for c in WALL_CATALOG_COLUMNS) else cat
