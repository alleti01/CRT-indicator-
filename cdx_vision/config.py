"""Defaults are fail-closed. Vision cannot route an order in this build."""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class VisionConfig:
    enabled: bool = False
    shadow_only: bool = True
    execution_enabled: bool = False
    require_consensus: bool = True
    require_tradingview_visible: bool = True
    save_debug_images: bool = False
    timeout_seconds: float = 5.0
    sanity_points: Decimal = Decimal("500")
    entry_mismatch_points: Decimal = Decimal("100")
    auto_right_enabled: bool = False
    auto_right_max_attempts: int = 3
    redraw_delay_ms: int = 1500
    chart_focus_x: float = 0.40
    chart_focus_y: float = 0.45
    tick: Decimal = Decimal("0.25")
    window_title_pattern: str = "TradingView"
    required_timeframe: str = "3m"
    dedicated_window: bool = False
    auto_restore_timeframe: bool = False
    timeframe_restore_timeout_ms: int = 8000
    redraw_wait_ms: int = 1500
    max_total_acquisition_ms: int = 20000
    root: Path = Path("cdx_vision")

    @classmethod
    def from_env(cls) -> "VisionConfig":
        return cls(
            enabled=_flag("CDX_VISION_ENABLED", "false"),
            shadow_only=_flag("CDX_VISION_SHADOW_ONLY", "true"),
            execution_enabled=_flag("CDX_VISION_EXECUTION_ENABLED", "false"),
            require_consensus=_flag("CDX_VISION_REQUIRE_CONSENSUS", "true"),
            require_tradingview_visible=_flag("CDX_VISION_REQUIRE_TRADINGVIEW_VISIBLE", "true"),
            save_debug_images=_flag("CDX_VISION_SAVE_DEBUG_IMAGES", "false"),
            timeout_seconds=float(os.environ.get("CDX_VISION_TIMEOUT_SECONDS", "5")),
            sanity_points=Decimal(os.environ.get("CDX_VISION_SANITY_POINTS", "500")),
            entry_mismatch_points=Decimal(os.environ.get("CDX_VISION_ENTRY_MISMATCH_POINTS", "100")),
            auto_right_enabled=_flag("CDX_VISION_AUTO_RIGHT_ENABLED", "false"),
            auto_right_max_attempts=int(os.environ.get("CDX_VISION_AUTO_RIGHT_MAX_ATTEMPTS", "3")),
            redraw_delay_ms=int(os.environ.get("CDX_VISION_REDRAW_DELAY_MS", "1500")),
            chart_focus_x=float(os.environ.get("CDX_VISION_CHART_FOCUS_X", "0.40")),
            chart_focus_y=float(os.environ.get("CDX_VISION_CHART_FOCUS_Y", "0.45")),
            required_timeframe=os.environ.get("CDX_VISION_REQUIRED_TIMEFRAME", "3m").strip().lower() or "3m",
            dedicated_window=_flag("CDX_VISION_DEDICATED_WINDOW", "true"),
            auto_restore_timeframe=_flag("CDX_VISION_AUTO_RESTORE_TIMEFRAME", "true"),
            timeframe_restore_timeout_ms=int(os.environ.get("CDX_VISION_TIMEFRAME_RESTORE_TIMEOUT_MS", "8000")),
            redraw_wait_ms=int(os.environ.get("CDX_VISION_REDRAW_WAIT_MS", "1500")),
            max_total_acquisition_ms=int(os.environ.get("CDX_VISION_MAX_TOTAL_ACQUISITION_MS", "20000")),
            window_title_pattern=os.environ.get("CDX_VISION_WINDOW_TITLE", "MNQ"),
        )

    def may_route_orders(self) -> bool:
        """V1 never routes. A later phase would have to change this method."""
        return False

    @property
    def ledger_path(self) -> Path:
        return self.root / "logs" / "vision_levels.jsonl"

    @property
    def research_csv(self) -> Path:
        return Path("forward_rehearsal") / "cdx_native_levels.csv"
