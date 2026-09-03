"""Sequential S54 realtime engine."""

from __future__ import annotations

import pandas as pd

from phase55.config import WARMUP_BARS
from phase55.implementation.s54_episodes import S54EpisodeState, build_d10_order_map, episode_event_order
from phase55.implementation.s54_events import S54EventDetector
from phase55.implementation.s54_state import S54State


class S54RealtimeEngine:
    """Process closed 1M bars sequentially without future access."""

    def __init__(
        self,
        market: pd.DataFrame,
        *,
        scored_events: pd.DataFrame | None = None,
        d10_order: dict[str, int] | None = None,
    ):
        self.market = market
        self.detector = S54EventDetector(market, start_i=WARMUP_BARS)
        self.state = S54State()
        self.events: list[dict] = []
        self.signals: list[dict] = []
        self.scored_lookup: dict[tuple, dict] = {}
        self.d10_order = d10_order or {}
        if scored_events is not None and not scored_events.empty:
            for _, r in scored_events.iterrows():
                key = (pd.Timestamp(r["timestamp_ct"]), r["event_type"], r["direction"])
                self.scored_lookup[key] = r.to_dict()

    def warm_episode_history(self, global_d10: pd.DataFrame, before: pd.Timestamp | None = None) -> None:
        """Warm episode clocks from pre-window D10 in global frozen order."""
        ordered = episode_event_order(global_d10)
        if before is not None:
            ordered = ordered.loc[pd.to_datetime(ordered["timestamp_ct"]) < before]
        for _, r in ordered.iterrows():
            self.state.episode_state.process(r["timestamp_ct"], r["direction"])

    def _bar_event_rank(self, ev: dict) -> int:
        key = (pd.Timestamp(ev["timestamp_ct"]), ev["event_type"], ev["direction"])
        ref = self.scored_lookup.get(key, {})
        eid = str(ref.get("event_id", ev.get("event_id", "")))
        return self.d10_order.get(eid, 10**12)

    def warm_bar(self, i: int) -> None:
        if i >= WARMUP_BARS:
            self.detector.step(i)

    def on_bar_close(self, i: int) -> list[dict]:
        self.state.bar_index = i
        if i < WARMUP_BARS:
            return []
        self.state.warmup_complete = True
        new_signals: list[dict] = []
        bar_events = self.detector.step(i)
        bar_events.sort(key=self._bar_event_rank)
        for ev in bar_events:
            self.state.event_count += 1
            self.events.append(ev)
            key = (pd.Timestamp(ev["timestamp_ct"]), ev["event_type"], ev["direction"])
            ref = self.scored_lookup.get(key)
            if ref is None or not ref.get("top10", False):
                continue
            self.state.d10_count += 1
            ep_act = self.state.episode_state.process(ev["timestamp_ct"], ev["direction"])
            if ep_act["s54_entry"]:
                sig = {
                    **ev,
                    **ep_act,
                    "score": ref.get("score"),
                    "event_id": ref.get("event_id", ev.get("event_id")),
                    "signal_id": f"S54-{self.state.signal_count + 1:06d}",
                    "signal_type": f"S54 {ev['direction']}",
                }
                self.state.signal_count += 1
                self.state.last_signal = sig
                self.signals.append(sig)
                new_signals.append(sig)
        return new_signals

    def run_sequential(self, *, end_i: int | None = None, start_i: int | None = None) -> pd.DataFrame:
        n = end_i if end_i is not None else len(self.market) - 61
        s = start_i if start_i is not None else WARMUP_BARS
        for i in range(WARMUP_BARS, s):
            self.warm_bar(i)
        for i in range(s, n + 1):
            self.on_bar_close(i)
        return pd.DataFrame(self.signals)
