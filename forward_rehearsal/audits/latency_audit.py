"""Latency distribution audit for forward sessions."""
from __future__ import annotations

from typing import Any


def latency_distribution(samples: list[float]) -> dict[str, Any]:
    if not samples:
        return {"count": 0, "median": None, "p90": None, "p95": None, "max": None}
    s = sorted(samples)
    n = len(s)

    def pct(p: float) -> float:
        idx = int((n - 1) * p)
        return s[idx]

    spikes = [v for v in s if v > pct(0.95) * 2 and v > 1000]
    return {
        "count": n,
        "median": pct(0.5),
        "p90": pct(0.9),
        "p95": pct(0.95),
        "max": s[-1],
        "abnormal_spikes_ms": spikes,
    }


def latency_audit_report(
    *,
    pine_to_webhook: list[float],
    webhook_to_decision: list[float],
    signal_to_fill: list[float],
) -> dict[str, Any]:
    return {
        "pine_to_webhook_ms": latency_distribution(pine_to_webhook),
        "webhook_to_decision_ms": latency_distribution(webhook_to_decision),
        "signal_to_fill_ms": latency_distribution(signal_to_fill),
    }
