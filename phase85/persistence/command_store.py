"""Persistent command_id / signal_id dedup that survives process restart."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CommandStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._commands: dict[str, dict[str, Any]] = {}
        self._signals: dict[str, str] = {}
        self._events: dict[str, str] = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                cid = str(rec.get("command_id", ""))
                if cid:
                    self._commands[cid] = rec
                sid = str(rec.get("signal_id", ""))
                if sid:
                    self._signals[sid] = cid
                eid = str(rec.get("event_id", ""))
                if eid:
                    self._events[eid] = cid

    def seen_command(self, command_id: str) -> bool:
        return command_id in self._commands

    def seen_signal(self, signal_id: str) -> bool:
        return bool(signal_id) and signal_id in self._signals

    def seen_event(self, event_id: str) -> bool:
        return bool(event_id) and event_id in self._events

    def get(self, command_id: str) -> dict[str, Any] | None:
        return self._commands.get(command_id)

    def record(
        self,
        *,
        command_id: str,
        command: str,
        signal_id: str = "",
        event_id: str = "",
        order_id: str = "",
        state: str = "",
    ) -> dict[str, Any]:
        if command_id in self._commands:
            return self._commands[command_id]
        rec = {
            "command_id": command_id,
            "command": command,
            "signal_id": signal_id,
            "event_id": event_id,
            "order_id": order_id,
            "state": state,
        }
        self._commands[command_id] = rec
        if signal_id:
            self._signals[signal_id] = command_id
        if event_id:
            self._events[event_id] = command_id
        with self.path.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        return rec

    def update_order(self, command_id: str, *, order_id: str = "", state: str = "") -> None:
        rec = self._commands.get(command_id)
        if not rec:
            return
        if order_id:
            rec["order_id"] = order_id
        if state:
            rec["state"] = state
