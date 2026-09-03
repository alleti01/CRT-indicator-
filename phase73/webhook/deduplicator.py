"""Idempotent signal deduplication."""
from __future__ import annotations

import json
from pathlib import Path

from phase73.webhook.schemas import WebhookReason


class SignalDeduplicator:
    def __init__(self, store_path: Path | None = None) -> None:
        self.store_path = store_path
        self._seen: set[str] = set()
        if store_path and store_path.exists():
            for line in store_path.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self._seen.add(str(rec["signal_id"]))

    def is_duplicate(self, signal_id: str) -> bool:
        return signal_id in self._seen

    def record(self, signal_id: str) -> None:
        if signal_id in self._seen:
            return
        self._seen.add(signal_id)
        if self.store_path:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            with self.store_path.open("a") as f:
                f.write(json.dumps({"signal_id": signal_id}) + "\n")

    def check_and_record(self, signal_id: str) -> WebhookReason | None:
        if self.is_duplicate(signal_id):
            return WebhookReason.SIGNAL_DUPLICATE
        self.record(signal_id)
        return None
