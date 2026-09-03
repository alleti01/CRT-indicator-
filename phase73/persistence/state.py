"""Crash-safe trader state persistence."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class PersistedState:
    version: str = "1.0"
    trader_state: str = "FLAT"
    last_signal_id: str = ""
    open_side: str = "FLAT"
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    signal_atr: float | None = None
    entry_time: str = ""
    mfe_r: float = 0.0
    mae_r: float = 0.0
    bars_in_trade: int = 0
    pending_orders: list[dict[str, Any]] = field(default_factory=list)
    halted: bool = False


class StatePersistence:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, state: PersistedState) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(state), indent=2))
        tmp.replace(self.path)

    def load(self) -> PersistedState | None:
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text())
        return PersistedState(**data)
