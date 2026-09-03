"""Runtime state persistence for forward validation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from phase55.implementation.s54_episodes import S54EpisodeState
from phase56.config import STATE


def save_runtime_state(
    *,
    bar_index: int,
    event_counter: int,
    signal_counter: int,
    episode_state: S54EpisodeState,
    last_bar_timestamp: str | None = None,
) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    payload = {
        "bar_index": bar_index,
        "event_counter": event_counter,
        "signal_counter": signal_counter,
        "last_long_episode_timestamp": str(episode_state.last_start.get("LONG", "")),
        "last_short_episode_timestamp": str(episode_state.last_start.get("SHORT", "")),
        "suppressed_count": episode_state.suppressed_count,
        "episode_counter": episode_state.episode_counter,
        "last_bar_timestamp": last_bar_timestamp,
    }
    (STATE / "runtime_state.json").write_text(json.dumps(payload, indent=2) + "\n")


def load_runtime_state() -> dict:
    path = STATE / "runtime_state.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_open_position(payload: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "open_position.json").write_text(json.dumps(payload, indent=2) + "\n")


def load_open_position() -> dict:
    path = STATE / "open_position.json"
    if not path.exists():
        return {"state": "FLAT"}
    return json.loads(path.read_text())


def restore_episode_state(data: dict) -> S54EpisodeState:
    st = S54EpisodeState()
    st.episode_counter = int(data.get("episode_counter", 0))
    st.suppressed_count = int(data.get("suppressed_count", 0))
    tz = "America/Chicago"
    ll = data.get("last_long_episode_timestamp") or data.get("last_start_long")
    ls = data.get("last_short_episode_timestamp") or data.get("last_start_short")
    if ll:
        st.last_start["LONG"] = pd.Timestamp(ll)
    if ls:
        st.last_start["SHORT"] = pd.Timestamp(ls)
    return st
