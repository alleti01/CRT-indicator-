"""Latency telemetry. Do not claim performance without measurement."""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _ms(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds() * 1000.0)


@dataclass
class LatencySample:
    command_id: str
    signal_id: str = ""
    t0_signal: datetime | None = None
    t1_webhook: datetime | None = None
    t2_decision: datetime | None = None
    t3_command: datetime | None = None
    t4_bridge: datetime | None = None
    t5_submit: datetime | None = None
    t6_ack: datetime | None = None
    t7_first_fill: datetime | None = None
    t8_final_fill: datetime | None = None
    t9_protection_submit: datetime | None = None
    t10_protection_working: datetime | None = None

    def deltas_ms(self) -> dict[str, float | None]:
        return {
            "tv_to_webhook_ms": _ms(self.t0_signal, self.t1_webhook),
            "webhook_to_decision_ms": _ms(self.t1_webhook, self.t2_decision),
            "decision_to_bridge_ms": _ms(self.t2_decision, self.t4_bridge or self.t3_command),
            "bridge_to_submit_ms": _ms(self.t4_bridge or self.t3_command, self.t5_submit),
            "submit_to_ack_ms": _ms(self.t5_submit, self.t6_ack),
            "submit_to_fill_ms": _ms(self.t5_submit, self.t8_final_fill or self.t7_first_fill),
            "fill_to_protection_ms": _ms(self.t8_final_fill or self.t7_first_fill, self.t10_protection_working or self.t9_protection_submit),
            "end_to_end_ms": _ms(self.t0_signal, self.t10_protection_working or self.t8_final_fill),
        }


@dataclass
class LatencyTracker:
    path: Path | None = None
    samples: list[LatencySample] = field(default_factory=list)

    def add(self, sample: LatencySample) -> None:
        self.samples.append(sample)
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rec: dict[str, Any] = {"command_id": sample.command_id, "signal_id": sample.signal_id}
        rec.update({k: _iso(getattr(sample, k)) for k in vars(sample) if k.startswith("t")})
        rec.update(sample.deltas_ms())
        with self.path.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")

    def summary(self) -> dict[str, Any]:
        keys = [
            "tv_to_webhook_ms",
            "webhook_to_decision_ms",
            "decision_to_bridge_ms",
            "bridge_to_submit_ms",
            "submit_to_ack_ms",
            "submit_to_fill_ms",
            "fill_to_protection_ms",
            "end_to_end_ms",
        ]
        out: dict[str, Any] = {"n": len(self.samples)}
        for key in keys:
            vals = [s.deltas_ms()[key] for s in self.samples if s.deltas_ms()[key] is not None]
            if not vals:
                out[key] = {"median": None, "p95": None, "max": None, "n": 0}
                continue
            vals_sorted = sorted(vals)
            p95_idx = min(len(vals_sorted) - 1, max(0, int(round(0.95 * (len(vals_sorted) - 1)))))
            out[key] = {
                "median": statistics.median(vals_sorted),
                "p95": vals_sorted[p95_idx],
                "max": vals_sorted[-1],
                "n": len(vals_sorted),
            }
        return out
