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
    tick: Decimal = Decimal("0.25")
    window_title_pattern: str = "TradingView"
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
