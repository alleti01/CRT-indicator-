"""Causal price-wall interaction detector."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from phase57d.config import BREAK_THRESHOLD_ATR, TOUCH_PROXIMITY_ATR
from phase57d.research.interfaces import WallSnapshot
from phase57d.research.schema import WALL_INTERACTION_COLUMNS


def _interaction_id(wall_id: str, ts: pd.Timestamp, itype: str) -> str:
    raw = f"{wall_id}|{ts.isoformat()}|{itype}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class InteractionState:
    """Track ongoing wall interaction episodes."""
    wall_id: str
    strike: float
    first_touch_i: Optional[int] = None
    touched: bool = False
    broken: bool = False
    reclaimed: bool = False
    approach_dir: Optional[str] = None
    events: list = field(default_factory=list)


class CausalInteractionDetector:
    """Detect APPROACH/TOUCH/BREAK/ACCEPTANCE/RECLAIM/RETEST causally."""

    def __init__(
        self,
        touch_atr: float = TOUCH_PROXIMITY_ATR,
        break_atr: float = BREAK_THRESHOLD_ATR,
    ):
        self.touch_atr = touch_atr
        self.break_atr = break_atr
        self._states: dict[str, InteractionState] = {}

    def _proximity(self, bar: pd.Series, strike: float, atr: float) -> bool:
        band = self.touch_atr * atr
        return float(bar["low"]) <= strike + band and float(bar["high"]) >= strike - band

    def _closed_beyond(
        self, close: float, strike: float, direction: str, atr: float
    ) -> bool:
        thresh = self.break_atr * atr
        if direction == "UP":
            return close > strike + thresh
        return close < strike - thresh

    def update(
        self,
        bar: pd.Series,
        bar_i: int,
        bar_ts: pd.Timestamp,
        active_walls: list[WallSnapshot],
        atr: float,
    ) -> list[dict]:
        """Process one closed bar against active walls."""
        events: list[dict] = []
        close = float(bar["close"])
        for w in active_walls:
            if bar_ts < w.valid_from:
                continue
            if w.valid_until is not None and bar_ts >= w.valid_until:
                continue

            st = self._states.setdefault(
                w.wall_id,
                InteractionState(wall_id=w.wall_id, strike=w.strike),
            )
            if not self._proximity(bar, w.strike, atr):
                continue

            # Approach direction from prior close if available
            if st.approach_dir is None:
                if close > w.strike:
                    st.approach_dir = "FROM_ABOVE"
                elif close < w.strike:
                    st.approach_dir = "FROM_BELOW"

            if not st.touched:
                st.touched = True
                st.first_touch_i = bar_i
                events.append(self._event(w, bar_ts, bar_i, "TOUCH", close, atr))

                # W1 rejection candidate: touch without break (direction TBD at label time)
                events.append(
                    self._event(w, bar_ts, bar_i, "W1_REJECTION_CANDIDATE", close, atr)
                )
                # W2 breakout candidate
                events.append(
                    self._event(w, bar_ts, bar_i, "W2_BREAKOUT_CANDIDATE", close, atr)
                )

            # Break detection (causal close beyond wall)
            up_break = self._closed_beyond(close, w.strike, "UP", atr)
            down_break = self._closed_beyond(close, w.strike, "DOWN", atr)
            if (up_break or down_break) and not st.broken:
                st.broken = True
                direction = "UP" if up_break else "DOWN"
                events.append(
                    self._event(w, bar_ts, bar_i, "W3_BREAK_ACCEPTANCE", close, atr, direction)
                )

            # W5 sweep/reclaim: penetrated then closed back
            if st.broken and not st.reclaimed:
                if up_break is False and down_break is False:
                    hi, lo = float(bar["high"]), float(bar["low"])
                    if lo < w.strike and close > w.strike:
                        st.reclaimed = True
                        events.append(
                            self._event(w, bar_ts, bar_i, "W5_SWEEP_RECLAIM", close, atr, "LONG")
                        )
                    elif hi > w.strike and close < w.strike:
                        st.reclaimed = True
                        events.append(
                            self._event(w, bar_ts, bar_i, "W5_SWEEP_RECLAIM", close, atr, "SHORT")
                        )

        return events

    def _event(
        self,
        w: WallSnapshot,
        ts: pd.Timestamp,
        bar_i: int,
        itype: str,
        close: float,
        atr: float,
        direction: str = "NEUTRAL",
    ) -> dict:
        iid = _interaction_id(w.wall_id, ts, itype)
        return {
            "interaction_id": iid,
            "wall_id": w.wall_id,
            "episode_id": "",
            "underlying": w.underlying,
            "mapping": w.mapping,
            "wall_family": w.wall_family,
            "interaction_type": itype,
            "direction": direction,
            "signal_timestamp": ts,
            "execution_timestamp": pd.NaT,
            "entry_price": np.nan,
            "stop_price": np.nan,
            "target_price": np.nan,
            "strike": w.strike,
            "spot_at_signal": close,
            "distance_atr_at_signal": abs(close - w.strike) / max(atr, 1e-9),
            "wall_strength_percentile": w.wall_strength_percentile,
            "expiration_bucket": w.expiration_bucket,
            "entry_stage": "E0",
            "valid_from": w.valid_from,
            "source_snapshot_timestamp": w.source_snapshot_timestamp,
            "bar_i": bar_i,
        }


def interactions_to_df(events: list[dict]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame(columns=WALL_INTERACTION_COLUMNS)
    return pd.DataFrame(events)
