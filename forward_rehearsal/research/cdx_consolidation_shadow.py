"""Log what the structural trail would do. It never places or changes an order."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from forward_rehearsal.research.cdx_directional_consolidation import Bar, NativeSim

OUT = (
    Path(__file__).resolve().parents[2]
    / "forward_rehearsal"
    / "reports"
    / "cdx_directional_consolidation"
    / "shadow_live.jsonl"
)

_BOOKS: dict[tuple[str, float], NativeSim] = {}


def shadow_enabled() -> bool:
    return os.environ.get("CDX_CONSOLIDATION_SHADOW", "0") in {"1", "true", "TRUE"}


def observe_live_bar(
    *,
    side: str,
    entry: float,
    stop: float,
    bar_open: datetime,
    high: float,
    low: float,
    close: float,
    legacy_reason: str,
) -> None:
    if not shadow_enabled():
        return
    if bar_open.tzinfo is None:
        bar_open = bar_open.replace(tzinfo=timezone.utc)
    key = (side, round(entry, 4))
    sim = _BOOKS.get(key)
    if sim is None:
        sim = NativeSim(
            side=side,
            fill=entry,
            sl=stop,
            tp1=entry + (10_000 if side == "LONG" else -10_000),
            cdx_entry=entry,
            variant="V2",
            use_structure=True,
        )
        sim.entry_open = bar_open
        _BOOKS[key] = sim
    if sim.result is not None:
        return
    sim.on_bar(Bar(bar_open, high, low, close), manage=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.open("a", encoding="utf-8").write(
        json.dumps(
            {
                "bar_open": bar_open.isoformat(),
                "side": side,
                "entry": entry,
                "chart_stop": stop,
                "hypothetical_structural_stop": sim.stop,
                "protection_armed": sim.armed,
                "legacy_chop_exit_would_fire": legacy_reason == "REVERSAL",
                "legacy_reason": legacy_reason,
                "hypothetical_exit": None if sim.result is None else sim.result.reason,
            }
        )
        + "\n"
    )
