"""Append-only vision ledger. Rows are never rewritten."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from cdx_vision.models import VisionResult

CSV_COLUMNS = (
    "signal_id",
    "timestamp",
    "direction",
    "fill_price",
    "cdx_entry",
    "cdx_stop",
    "cdx_tp1",
    "cdx_tp2",
    "cdx_stop_points",
    "bot_stop",
    "bot_stop_points",
    "cdx_stop_hit",
    "bot_stop_hit",
    "reached_cdx_tp1",
    "reached_cdx_tp2",
    "vision_status",
    "cdx_visual_entry",
    "webhook_entry",
    "actual_fill",
    "cdx_native_entry",
    "entry_source",
    "native_r_points",
    "native_r_source",
    "tp1_R",
    "tp2_R",
    "visual_vs_webhook_points",
    "fill_vs_visual_points",
    "fill_vs_webhook_points",
    "absolute_fill_vs_visual_points",
    "reason_codes",
    "capture_method",
    "initial_levels_visible",
    "auto_right_enabled",
    "auto_right_triggered",
    "auto_right_attempts",
    "auto_right_success",
)
CSV_HEADER = ",".join(CSV_COLUMNS) + "\n"


def _dec(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")


def level_metrics(result: VisionResult) -> dict[str, Decimal | str | None]:
    """R and entry differences. Webhook fallback is not labeled as native R."""
    visual = result.visual_entry
    webhook = result.webhook_entry
    fill = result.actual_fill
    native = result.entry
    stop = result.stop
    native_r: Decimal | None = None
    native_r_source = ""
    if result.entry_source == "VISION" and visual is not None and stop is not None:
        native_r = abs(visual - stop)
        native_r_source = "VISION"
    elif result.entry_source == "WEBHOOK" and webhook is not None and stop is not None:
        native_r = abs(webhook - stop)
        native_r_source = "WEBHOOK_FALLBACK"
    elif result.entry_source == "FILL" and fill is not None and stop is not None:
        native_r = abs(fill - stop)
        native_r_source = "FILL_FALLBACK"
    tp1_r = tp2_r = None
    if native is not None and stop is not None and abs(native - stop) != 0:
        risk = abs(native - stop)
        if result.tp1 is not None:
            tp1_r = abs(result.tp1 - native) / risk
        if result.tp2 is not None:
            tp2_r = abs(result.tp2 - native) / risk

    def sub(left: Decimal | None, right: Decimal | None) -> Decimal | None:
        if left is None or right is None:
            return None
        return left - right

    fill_vs_visual = sub(fill, visual)
    return {
        "native_r_points": native_r,
        "native_r_source": native_r_source,
        "tp1_R": tp1_r,
        "tp2_R": tp2_r,
        "visual_vs_webhook_points": sub(webhook, visual),
        "fill_vs_visual_points": fill_vs_visual,
        "fill_vs_webhook_points": sub(fill, webhook),
        "absolute_fill_vs_visual_points": None if fill_vs_visual is None else abs(fill_vs_visual),
    }


def load_rows(path: Path) -> list[dict]:
    """Read the ledger. Older rows simply lack the visual-entry fields."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row.setdefault("schema_version", "1.0")
        row.setdefault("cdx_visual_entry", "")
        row.setdefault("webhook_entry", "")
        row.setdefault("actual_fill", "")
        row.setdefault("cdx_native_entry", row.get("entry", ""))
        row.setdefault("entry_source", row.get("entry_source", ""))
        row.setdefault("auto_right_triggered", False)
        row.setdefault("auto_right_attempts", 0)
        rows.append(row)
    return rows


class VisionLedger:
    def __init__(self, path: Path, research_csv: Path) -> None:
        self.path = path
        self.research_csv = research_csv

    def append(self, result: VisionResult, *, ticker: str = "NQ") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stats = level_metrics(result)
        stop_pts = stats["native_r_points"] if isinstance(stats["native_r_points"], Decimal) else None
        if stop_pts is None and result.entry is not None and result.stop is not None:
            stop_pts = abs(result.entry - result.stop)
        tp1_pts = abs(result.entry - result.tp1) if result.entry is not None and result.tp1 is not None else None
        tp2_pts = abs(result.entry - result.tp2) if result.entry is not None and result.tp2 is not None else None
        record = {
            "schema_version": "2",
            "signal_id": result.signal_id,
            "ticker": ticker,
            "webhook_direction": result.direction,
            "webhook_received_at": _iso(result.webhook_received_at),
            "capture_started_at": _iso(result.capture_started_at),
            "confirmed_at": _iso(result.confirmed_at),
            "window_title": result.window_title,
            "window_bounds": result.window_bounds,
            "entry": _dec(result.entry),
            "entry_source": result.entry_source or "MISSING",
            "cdx_visual_entry": _dec(result.visual_entry),
            "webhook_entry": _dec(result.webhook_entry),
            "actual_fill": _dec(result.actual_fill),
            "cdx_native_entry": _dec(result.entry),
            "stop": _dec(result.stop),
            "tp1": _dec(result.tp1),
            "tp2": _dec(result.tp2),
            "cdx_stop": _dec(result.stop),
            "cdx_tp1": _dec(result.tp1),
            "cdx_tp2": _dec(result.tp2),
            "stop_distance_points": _dec(stop_pts),
            "tp1_distance_points": _dec(tp1_pts),
            "tp2_distance_points": _dec(tp2_pts),
            "native_r_points": _dec(stats["native_r_points"] if isinstance(stats["native_r_points"], Decimal) else None),
            "native_r_source": stats["native_r_source"],
            "implied_r_tp1": _dec(stats["tp1_R"] if isinstance(stats["tp1_R"], Decimal) else None),
            "implied_r_tp2": _dec(stats["tp2_R"] if isinstance(stats["tp2_R"], Decimal) else None),
            "tp1_R": _dec(stats["tp1_R"] if isinstance(stats["tp1_R"], Decimal) else None),
            "tp2_R": _dec(stats["tp2_R"] if isinstance(stats["tp2_R"], Decimal) else None),
            "visual_vs_webhook_points": _dec(stats["visual_vs_webhook_points"] if isinstance(stats["visual_vs_webhook_points"], Decimal) else None),
            "fill_vs_visual_points": _dec(stats["fill_vs_visual_points"] if isinstance(stats["fill_vs_visual_points"], Decimal) else None),
            "fill_vs_webhook_points": _dec(stats["fill_vs_webhook_points"] if isinstance(stats["fill_vs_webhook_points"], Decimal) else None),
            "absolute_fill_vs_visual_points": _dec(
                stats["absolute_fill_vs_visual_points"] if isinstance(stats["absolute_fill_vs_visual_points"], Decimal) else None
            ),
            "frame_count": result.frame_count,
            "agreeing_frame_count": result.agreeing_frame_count,
            "validation_status": result.state.value,
            "vision_status": result.state.value,
            "reason_codes": result.reasons,
            "ocr_unstable": result.ocr_unstable,
            "debug_capture_paths": result.debug_paths,
            "capture_method": result.window_bounds,
            "initial_levels_visible": result.initial_levels_visible,
            "auto_right_enabled": result.auto_right_enabled,
            "auto_right_triggered": result.auto_right_triggered,
            "auto_right_attempts": result.auto_right_attempts,
            "auto_right_success": result.auto_right_success,
            "navigation_reason": result.navigation_reason,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        self._append_csv(result)

    def _append_csv(self, result: VisionResult) -> None:
        self.research_csv.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_header()
        stats = level_metrics(result)
        native_r = stats["native_r_points"] if isinstance(stats["native_r_points"], Decimal) else None
        values = {
            "signal_id": result.signal_id,
            "timestamp": _iso(result.webhook_received_at),
            "direction": result.direction,
            "fill_price": _dec(result.actual_fill),
            "cdx_entry": _dec(result.entry),
            "cdx_stop": _dec(result.stop),
            "cdx_tp1": _dec(result.tp1),
            "cdx_tp2": _dec(result.tp2),
            "cdx_stop_points": _dec(native_r),
            "bot_stop": "",
            "bot_stop_points": "",
            "cdx_stop_hit": "",
            "bot_stop_hit": "",
            "reached_cdx_tp1": "",
            "reached_cdx_tp2": "",
            "vision_status": result.state.value,
            "cdx_visual_entry": _dec(result.visual_entry),
            "webhook_entry": _dec(result.webhook_entry),
            "actual_fill": _dec(result.actual_fill),
            "cdx_native_entry": _dec(result.entry),
            "entry_source": result.entry_source or "MISSING",
            "native_r_points": _dec(native_r),
            "native_r_source": str(stats["native_r_source"]),
            "tp1_R": _dec(stats["tp1_R"] if isinstance(stats["tp1_R"], Decimal) else None),
            "tp2_R": _dec(stats["tp2_R"] if isinstance(stats["tp2_R"], Decimal) else None),
            "visual_vs_webhook_points": _dec(stats["visual_vs_webhook_points"] if isinstance(stats["visual_vs_webhook_points"], Decimal) else None),
            "fill_vs_visual_points": _dec(stats["fill_vs_visual_points"] if isinstance(stats["fill_vs_visual_points"], Decimal) else None),
            "fill_vs_webhook_points": _dec(stats["fill_vs_webhook_points"] if isinstance(stats["fill_vs_webhook_points"], Decimal) else None),
            "absolute_fill_vs_visual_points": _dec(
                stats["absolute_fill_vs_visual_points"] if isinstance(stats["absolute_fill_vs_visual_points"], Decimal) else None
            ),
            "reason_codes": "|".join(result.reasons),
            "capture_method": result.window_bounds,
            "initial_levels_visible": "true" if result.initial_levels_visible else "false",
            "auto_right_enabled": "true" if result.auto_right_enabled else "false",
            "auto_right_triggered": "true" if result.auto_right_triggered else "false",
            "auto_right_attempts": str(result.auto_right_attempts),
            "auto_right_success": "true" if result.auto_right_success else "false",
        }
        line = ",".join(values[name] for name in CSV_COLUMNS)
        with self.research_csv.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _ensure_header(self) -> None:
        if not self.research_csv.exists() or self.research_csv.stat().st_size == 0:
            self.research_csv.write_text(CSV_HEADER, encoding="utf-8")
            return
        lines = self.research_csv.read_text(encoding="utf-8").splitlines()
        wanted = ",".join(CSV_COLUMNS)
        if lines and lines[0] == wanted:
            return
        if not lines:
            self.research_csv.write_text(CSV_HEADER, encoding="utf-8")
            return
        # New columns are appended. Existing data rows are left as they were.
        lines[0] = wanted
        self.research_csv.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
