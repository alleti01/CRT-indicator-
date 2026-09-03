"""Shadow position tracker — virtual M0 management without broker orders."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from phase73.config.loader import Phase73Config
from phase73.market_data.bar import Bar
from phase73.trader.fsm import TraderAction
from phase73.trader.management import ManagementState, build_management, evaluate_exit
from phase73.webhook.schemas import PineSignal


@dataclass
class ShadowPosition:
    signal_id: str
    direction: str
    signal_price: float
    entry_price: float
    entry_time: datetime
    atr: float
    mgmt: ManagementState
    mfe: float = 0.0
    mae: float = 0.0


@dataclass
class ShadowAction:
    action: str
    reason: str
    signal_id: str = ""
    exit_price: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class ShadowPositionTracker:
    """Tracks WOULD_ENTER positions and evaluates WOULD_HOLD / WOULD_EXIT_* on closed bars."""

    def __init__(self, cfg: Phase73Config) -> None:
        self.cfg = cfg
        self.position: ShadowPosition | None = None
        self.closed_trades: list[dict[str, Any]] = []

    @property
    def is_active(self) -> bool:
        return self.position is not None

    @property
    def side(self) -> str:
        return self.position.direction if self.position else "FLAT"

    def open_from_signal(self, signal: PineSignal, entry_price: float, entry_time: datetime) -> ShadowAction:
        if self.position is not None:
            return ShadowAction(
                f"WOULD_{TraderAction.PASS_POSITION_CONFLICT.value}",
                "shadow position active",
                signal.signal_id,
            )
        mgmt = build_management(signal.direction, entry_price, signal.atr, self.cfg, entry_time)
        direction = signal.direction
        self.position = ShadowPosition(
            signal_id=signal.signal_id,
            direction=direction,
            signal_price=signal.signal_price,
            entry_price=entry_price,
            entry_time=entry_time,
            atr=signal.atr,
            mgmt=mgmt,
        )
        label = f"WOULD_ENTER_{direction}"
        return ShadowAction(label, "shadow entry", signal.signal_id, entry_price)

    def on_bar(self, bar: Bar, now: datetime) -> ShadowAction | None:
        if self.position is None:
            return None
        mgmt = self.position.mgmt
        exit_dec = evaluate_exit(mgmt, bar, self.cfg, now)
        if exit_dec is None:
            self.position.mfe = mgmt.mfe_r
            self.position.mae = mgmt.mae_r
            hold = "WOULD_HOLD_LONG" if mgmt.side == "LONG" else "WOULD_HOLD_SHORT"
            return ShadowAction(hold, "manage", self.position.signal_id, bar.close, {"current_r": mgmt.current_r})

        action_map = {
            TraderAction.EXIT_STOP: "WOULD_EXIT_STOP",
            TraderAction.EXIT_PROFIT: "WOULD_EXIT_TARGET",
            TraderAction.EXIT_TIME: "WOULD_EXIT_TIME",
            TraderAction.EXIT_NO_PROGRESS: "WOULD_EXIT_TIME",
            TraderAction.EXIT_FAILURE: "WOULD_EXIT_STOP",
        }
        label = action_map.get(exit_dec.action, f"WOULD_{exit_dec.action.value}")
        rec = {
            "signal_id": self.position.signal_id,
            "direction": self.position.direction,
            "entry_price": self.position.entry_price,
            "exit_price": exit_dec.exit_price or bar.close,
            "exit_reason": exit_dec.reason,
            "action": label,
            "mfe_r": self.position.mfe,
            "mae_r": self.position.mae,
        }
        self.closed_trades.append(rec)
        sid = self.position.signal_id
        self.position = None
        return ShadowAction(label, exit_dec.reason, sid, exit_dec.exit_price or bar.close)

    def on_opposite_signal(self, signal: PineSignal) -> ShadowAction:
        if self.position is None:
            return ShadowAction("WOULD_WATCH", "flat", signal.signal_id)
        active = self.position.direction
        incoming = signal.direction
        if incoming == active:
            return ShadowAction("WOULD_SAME_DIRECTION", "duplicate while active", signal.signal_id)
        return ShadowAction("WOULD_OPPOSITE_SIGNAL", "opposite while active", signal.signal_id)
