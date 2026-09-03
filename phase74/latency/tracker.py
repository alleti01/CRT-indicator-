"""End-to-end latency measurement."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class LatencyTracker:
    pine_bar_close_at: datetime | None = None
    webhook_received_at: datetime | None = None
    webhook_validated_at: datetime | None = None
    decision_at: datetime | None = None
    order_submitted_at: datetime | None = None
    broker_ack_at: datetime | None = None
    fill_at: datetime | None = None
    pine_to_webhook_ms: float = 0.0
    webhook_validation_ms: float = 0.0
    decision_ms: float = 0.0
    decision_to_order_ms: float = 0.0
    broker_ack_ms: float = 0.0
    fill_ms: float = 0.0
    total_signal_to_fill_ms: float = 0.0
    samples: list[float] = field(default_factory=list)

    def finalize(self) -> dict[str, float]:
        if self.webhook_received_at and self.decision_at:
            self.decision_ms = (self.decision_at - self.webhook_received_at).total_seconds() * 1000
        if self.decision_at and self.order_submitted_at:
            self.decision_to_order_ms = (self.order_submitted_at - self.decision_at).total_seconds() * 1000
        if self.order_submitted_at and self.broker_ack_at:
            self.broker_ack_ms = (self.broker_ack_at - self.order_submitted_at).total_seconds() * 1000
        if self.order_submitted_at and self.fill_at:
            self.fill_ms = (self.fill_at - self.order_submitted_at).total_seconds() * 1000
        if self.webhook_received_at and self.fill_at:
            self.total_signal_to_fill_ms = (self.fill_at - self.webhook_received_at).total_seconds() * 1000
        out = {
            "pine_to_webhook_ms": self.pine_to_webhook_ms,
            "webhook_validation_ms": self.webhook_validation_ms,
            "decision_ms": self.decision_ms,
            "decision_to_order_ms": self.decision_to_order_ms,
            "broker_ack_ms": self.broker_ack_ms,
            "fill_ms": self.fill_ms,
            "total_signal_to_fill_ms": self.total_signal_to_fill_ms,
        }
        self.samples.append(self.total_signal_to_fill_ms)
        return out

    @staticmethod
    def distribution(samples: list[float]) -> dict[str, Any]:
        if not samples:
            return {"count": 0}
        s = sorted(samples)
        return {
            "count": len(s),
            "p50": s[len(s) // 2],
            "p95": s[int(len(s) * 0.95)] if len(s) > 1 else s[0],
            "max": s[-1],
        }
