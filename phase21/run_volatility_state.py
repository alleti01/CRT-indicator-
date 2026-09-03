#!/usr/bin/env python3
"""Run Phase 21 volatility-state transition edge discovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase16.config import FrozenConfig
from phase21.analyze_volatility_state import load_unified_market_data, run_volatility_state_study
from phase21.config import (
    CONTAMINATED_WINDOWS,
    DATA_PATHS,
    ERAS,
    HIGH_PERCENTILE,
    HORIZONS,
    LONG_BARS,
    LOW_PERCENTILE,
    MEDIUM_BARS,
    PERCENTILE_WINDOW_BARS,
    RESULTS,
    SHORT_BARS,
)


def write_static_docs(output: Path, config: FrozenConfig) -> None:
    market = load_unified_market_data(config)
    audit = [
        "# Phase 21 Data Audit",
        "",
        "Discovery label: **DEVELOPMENT / DISCOVERY** — no historical slice treated as genuinely OOS.",
        "",
        "## Contaminated windows",
    ]
    for window in CONTAMINATED_WINDOWS:
        audit.append(f"- {window}")
    audit.extend(["", "## Merged datasets"])
    for path in DATA_PATHS:
        audit.append(f"- `{path}`")
    audit.extend(
        [
            "",
            f"Unified range: `{market.index.min()}` → `{market.index.max()}`",
            f"5m bars: **{len(market):,}**",
            "",
            "## Eras",
        ]
    )
    for era, bounds in ERAS.items():
        audit.append(f"- {era}: {bounds[0]} → {bounds[1]}")
    (output / "data_audit.md").write_text("\n".join(audit) + "\n")

    defs = [
        "# Volatility Event Definitions",
        "",
        f"Timezone: `{config.exchange_timezone}`",
        "",
        "## Horizons",
        f"- short={SHORT_BARS}, medium={MEDIUM_BARS}, long={LONG_BARS} bars",
        f"- forward horizons={HORIZONS} bars",
        "",
        "## Percentile window",
        f"- {PERCENTILE_WINDOW_BARS} bars (~60 CME session days)",
        f"- LOW <= {LOW_PERCENTILE}, HIGH >= {HIGH_PERCENTILE}",
        "",
        "## Shock de-duplication",
        "A shock event fires on first bar entering >=80th shock percentile.",
        "No additional shock events until shock percentile falls back below 80th.",
        "",
        "## Regime transitions",
        "Events fire only on primary ATR_24 state changes after >=6 bars in prior state (anti-flicker).",
        "Shock de-duplication: one event per shock episode until percentile falls below 80th.",
    ]
    (output / "event_definitions.md").write_text("\n".join(defs) + "\n")


def main() -> int:
    config = FrozenConfig()
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_static_docs(RESULTS, config)
    manifest = run_volatility_state_study(output=RESULTS, config=config)
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
