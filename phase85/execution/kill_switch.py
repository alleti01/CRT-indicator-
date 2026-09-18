"""Software kill switch. HALTED requires deliberate operator reset."""
from __future__ import annotations

from enum import Enum


class KillState(str, Enum):
    EXECUTION_ENABLED = "EXECUTION_ENABLED"
    EXECUTION_DISABLED = "EXECUTION_DISABLED"
    EXECUTION_HALTED = "EXECUTION_HALTED"


class ExecutionKillSwitch:
    def __init__(self, initial: KillState = KillState.EXECUTION_DISABLED) -> None:
        self.state = initial

    @property
    def allows_new_entries(self) -> bool:
        return self.state is KillState.EXECUTION_ENABLED

    def disable(self) -> None:
        if self.state is not KillState.EXECUTION_HALTED:
            self.state = KillState.EXECUTION_DISABLED

    def enable(self) -> None:
        if self.state is KillState.EXECUTION_HALTED:
            return
        self.state = KillState.EXECUTION_ENABLED

    def halt(self, reason: str = "") -> None:
        self.state = KillState.EXECUTION_HALTED
        self.last_halt_reason = reason

    def reset_halt(self, *, operator_ack: bool) -> bool:
        if not operator_ack:
            return False
        if self.state is KillState.EXECUTION_HALTED:
            self.state = KillState.EXECUTION_DISABLED
            return True
        return False
