"""Immutable forward session event logging."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionLogger:
    """Append-only JSONL logs under forward_rehearsal/sessions/YYYY-MM-DD/."""

    STREAMS = (
        "signals",
        "market_health",
        "decisions",
        "orders",
        "fills",
        "positions",
        "errors",
        "shadow_events",
        "state_transitions",
    )

    def __init__(
        self,
        session_dir: Path,
        *,
        session_id: str,
        software_hashes: dict[str, str],
        symbol: str,
        contract: str,
        stage: str,
    ) -> None:
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id
        self.software_hashes = software_hashes
        self.symbol = symbol
        self.contract = contract
        self.stage = stage
        self._handles: dict[str, Any] = {}

    def _path(self, stream: str) -> Path:
        return self.session_dir / f"{stream}.jsonl"

    def _write(self, stream: str, payload: dict[str, Any]) -> None:
        envelope = {
            "event_id": str(uuid.uuid4()),
            "session_id": self.session_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "symbol": self.symbol,
            "contract": self.contract,
            "stage": self.stage,
            "software_hashes": self.software_hashes,
            **payload,
        }
        with self._path(stream).open("a") as f:
            f.write(json.dumps(envelope, default=str) + "\n")

    def log_signal(self, **payload: Any) -> None:
        self._write("signals", payload)

    def log_market_health(self, **payload: Any) -> None:
        self._write("market_health", payload)

    def log_decision(self, **payload: Any) -> None:
        self._write("decisions", payload)

    def log_order(self, **payload: Any) -> None:
        self._write("orders", payload)

    def log_fill(self, **payload: Any) -> None:
        self._write("fills", payload)

    def log_position(self, **payload: Any) -> None:
        self._write("positions", payload)

    def log_error(self, **payload: Any) -> None:
        self._write("errors", payload)

    def log_shadow(self, **payload: Any) -> None:
        self._write("shadow_events", payload)

    def log_state_transition(self, **payload: Any) -> None:
        self._write("state_transitions", payload)

    def write_summary(self, summary: dict[str, Any]) -> None:
        out = {**summary, "session_id": self.session_id, "generated_at_utc": datetime.now(timezone.utc).isoformat()}
        (self.session_dir / "session_summary.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
