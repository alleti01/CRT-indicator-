#!/usr/bin/env python3
"""Run Phase 23 directional displacement edge discovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase16.config import FrozenConfig
from phase23.analyze_displacement import load_unified_market_data, run_displacement_study
from phase23.config import (
    BODY_ATR_THRESHOLDS,
    CONTAMINATED_WINDOWS,
    DATA_PATHS,
    DEDUP_SAME_DIRECTION_BARS,
    ERAS,
    HORIZONS,
    MIN_BODY_ATR_EVENT,
    RESULTS,
    STRUCTURE_LOOKBACK,
)


def write_static_docs(output: Path, config: FrozenConfig) -> None:
    market = load_unified_market_data(config)
    (output / "data_audit.md").write_text(
        "\n".join(
            [
                "# Phase 23 Data Audit",
                "",
                "Label: DEVELOPMENT / DISCOVERY",
                "",
                f"Range: `{market.index.min()}` → `{market.index.max()}`",
                f"Bars: {len(market):,}",
                "",
                "## Eras",
                *[f"- {era}: {bounds[0]} → {bounds[1]}" for era, bounds in ERAS.items()],
            ]
        )
        + "\n"
    )
    (output / "event_definitions.md").write_text(
        "\n".join(
            [
                "# Displacement Event Definitions",
                "",
                f"Minimum body/ATR24: {MIN_BODY_ATR_EVENT}",
                f"Strength thresholds: {BODY_ATR_THRESHOLDS}",
                f"Structure lookback: {STRUCTURE_LOOKBACK} bars excluding current bar",
                f"Dedup: suppress same-direction events for {DEDUP_SAME_DIRECTION_BARS} bars",
                f"Horizons: {HORIZONS}",
                "",
                "Follow-through signal time = follow-through bar close.",
                "Failure signal time = failure bar close (next bar beyond midpoint).",
            ]
        )
        + "\n"
    )


def main() -> int:
    config = FrozenConfig()
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_static_docs(RESULTS, config)
    manifest = run_displacement_study(output=RESULTS, config=config)
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
