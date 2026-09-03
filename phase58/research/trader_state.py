"""Trader finite-state machine — chronological bar-by-bar state transitions."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class State(str, Enum):
    WATCH = "WATCH"
    ARMED_LONG = "ARMED_LONG"
    ARMED_SHORT = "ARMED_SHORT"
    REACTION_LONG = "REACTION_LONG"
    REACTION_SHORT = "REACTION_SHORT"
    IN_LONG = "IN_LONG"
    IN_SHORT = "IN_SHORT"
    COOLDOWN = "COOLDOWN"
    INVALIDATED = "INVALIDATED"


class Decision(str, Enum):
    WATCH = "WATCH"
    ARMED = "ARMED"
    WAIT = "WAIT"
    TAKE_LONG = "TAKE_LONG"
    TAKE_SHORT = "TAKE_SHORT"
    PASS = "PASS"
    MISSED_NO_CHASE = "MISSED_NO_CHASE"
    INVALIDATED = "INVALIDATED"
    EXIT_STOP = "EXIT_STOP"
    EXIT_TARGET = "EXIT_TARGET"
    EXIT_TIME = "EXIT_TIME"
    HOLD = "HOLD"


@dataclass
class ActiveTrade:
    signal_i: int
    entry_i: int
    entry_price: float
    direction: str
    atr: float
    stop: float
    target: float
    exit_deadline_i: int
    mfe: float = 0.0
    mae: float = 0.0


@dataclass
class TraderSnapshot:
    """Complete state at one bar — stored for every bar in decision stream."""
    bar_i: int
    state: State
    decision: Decision
    direction: str
    context_dir: str
    context_confidence: int
    location_score: int
    reaction_score: int
    total_score: int
    armed_i: int
    armed_price: float
    pb_extreme_price: float
    entry_deterioration_atr: float
    reasons: list[str]
    trade: ActiveTrade | None = None


@dataclass
class TraderState:
    """Mutable state carried bar-to-bar."""
    state: State = State.WATCH
    direction: str = ""
    armed_i: int = -1
    armed_price: float = 0.0
    armed_bars: int = 0
    reaction_i: int = -1
    wait_bars: int = 0
    pb_extreme: float = 0.0
    cooldown_remaining: int = 0
    trade: ActiveTrade | None = None
    signal_counter: int = 0
    trade_counter: int = 0
    decisions: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)

    def reset_to_watch(self) -> None:
        self.state = State.WATCH
        self.direction = ""
        self.armed_i = -1
        self.armed_price = 0.0
        self.armed_bars = 0
        self.reaction_i = -1
        self.wait_bars = 0
        self.pb_extreme = 0.0
