"""Append-only vision ledger. Rows are never rewritten."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from cdx_vision.models import VisionResult

CSV_HEADER = (
    "signal_id,timestamp,direction,fill_price,cdx_entry,cdx_stop,cdx_tp1,cdx_tp2,"
    "cdx_stop_points,bot_stop,bot_stop_points,cdx_stop_hit,bot_stop_hit,"
    "reached_cdx_tp1,reached_cdx_tp2,vision_status\n"
)


def _dec(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")


class VisionLedger:
    def __init__(self, path: Path, research_csv: Path) -> None:
        self.path = path
        self.research_csv = research_csv

    def append(self, result: VisionResult, *, ticker: str = "NQ") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stop_pts = tp1_pts = tp2_pts = None
        r1 = r2 = None
        if result.entry is not None and result.stop is not None:
            stop_pts = abs(result.entry - result.stop)
        if result.entry is not None and result.tp1 is not None:
            tp1_pts = abs(result.entry - result.tp1)
        if result.entry is not None and result.tp2 is not None:
            tp2_pts = abs(result.entry - result.tp2)
        if stop_pts and tp1_pts:
            r1 = tp1_pts / stop_pts
        if stop_pts and tp2_pts:
            r2 = tp2_pts / stop_pts
        record = {
            "schema_version": "1.0",
            "signal_id": result.signal_id,
            "ticker": ticker,
            "webhook_direction": result.direction,
            "webhook_received_at": _iso(result.webhook_received_at),
            "capture_started_at": _iso(result.capture_started_at),
            "confirmed_at": _iso(result.confirmed_at),
            "window_title": result.window_title,
            "window_bounds": result.window_bounds,
            "entry": _dec(result.entry),
            "entry_source": result.entry_source,
            "stop": _dec(result.stop),
            "tp1": _dec(result.tp1),
            "tp2": _dec(result.tp2),
            "stop_distance_points": _dec(stop_pts),
            "tp1_distance_points": _dec(tp1_pts),
            "tp2_distance_points": _dec(tp2_pts),
            "implied_r_tp1": _dec(r1),
            "implied_r_tp2": _dec(r2),
            "frame_count": result.frame_count,
            "agreeing_frame_count": result.agreeing_frame_count,
            "validation_status": result.state.value,
            "reason_codes": result.reasons,
            "ocr_unstable": result.ocr_unstable,
            "debug_capture_paths": result.debug_paths,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        self._append_csv(result)

    def _append_csv(self, result: VisionResult) -> None:
        self.research_csv.parent.mkdir(parents=True, exist_ok=True)
        if not self.research_csv.exists():
            self.research_csv.write_text(CSV_HEADER, encoding="utf-8")
        stop_pts = ""
        if result.entry is not None and result.stop is not None:
            stop_pts = format(abs(result.entry - result.stop), "f")
        line = ",".join(
            [
                result.signal_id,
                _iso(result.webhook_received_at),
                result.direction,
                "",
                _dec(result.entry),
                _dec(result.stop),
                _dec(result.tp1),
                _dec(result.tp2),
                stop_pts,
                "",
                "",
                "",
                "",
                "",
                "",
                result.state.value,
            ]
        )
        with self.research_csv.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
