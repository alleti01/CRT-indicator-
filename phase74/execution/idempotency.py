"""Order idempotency — prevent duplicate entries from retries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class OrderIdempotencyStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._keys: set[str] = set()
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    self._keys.add(json.loads(line)["key"])

    @staticmethod
    def make_key(signal_id: str, action: str, attempt: int = 0) -> str:
        raw = f"{signal_id}|{action}|{attempt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def seen(self, signal_id: str, action: str, attempt: int = 0) -> bool:
        return self.make_key(signal_id, action, attempt) in self._keys

    def record(self, signal_id: str, action: str, attempt: int = 0, *, order_id: str = "") -> str:
        key = self.make_key(signal_id, action, attempt)
        if key in self._keys:
            return key
        self._keys.add(key)
        with self.path.open("a") as f:
            f.write(json.dumps({"key": key, "signal_id": signal_id, "action": action, "attempt": attempt, "order_id": order_id}) + "\n")
        return key
