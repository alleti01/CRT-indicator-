"""Transport contract: adapter never talks NT APIs directly."""
from __future__ import annotations

from typing import Protocol

from phase85.protocol.messages import Command, Event


class ExecutionTransport(Protocol):
    connected: bool
    authenticated: bool
    account: str
    instrument: str
    account_verified: bool
    contract_verified: bool

    def connect(self, token: str) -> bool: ...

    def disconnect(self) -> None: ...

    def send(self, command: Command) -> list[Event]: ...

    def snapshot(self) -> dict: ...
