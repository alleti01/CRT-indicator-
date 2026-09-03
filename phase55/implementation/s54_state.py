"""S54 realtime state container."""

from __future__ import annotations

from dataclasses import dataclass, field

from phase55.implementation.s54_episodes import S54EpisodeState


@dataclass
class S54State:
    bar_index: int = -1
    event_count: int = 0
    d10_count: int = 0
    episode_state: S54EpisodeState = field(default_factory=S54EpisodeState)
    last_signal: dict | None = None
    signal_count: int = 0
    warmup_complete: bool = False

    def snapshot(self) -> dict:
        return {
            "bar_index": self.bar_index,
            "event_count": self.event_count,
            "d10_count": self.d10_count,
            "signal_count": self.signal_count,
            "last_start_long": self.episode_state.last_start.get("LONG"),
            "last_start_short": self.episode_state.last_start.get("SHORT"),
            "suppressed_count": self.episode_state.suppressed_count,
        }
