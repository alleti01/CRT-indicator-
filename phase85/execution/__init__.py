"""Phase85 execution adapter surface."""

from phase85.execution.adapter import NinjaTraderExecutionAdapter
from phase85.execution.intent import ExecutionIntent
from phase85.execution.kill_switch import ExecutionKillSwitch, KillState
from phase85.execution.state_machine import ExecutionState

__all__ = [
    "ExecutionIntent",
    "ExecutionKillSwitch",
    "ExecutionState",
    "KillState",
    "NinjaTraderExecutionAdapter",
]
