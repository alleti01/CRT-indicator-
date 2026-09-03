#!/usr/bin/env python3
"""Run Phase 22 auction / market-profile directional edge discovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase16.config import FrozenConfig
from phase22.analyze_auction_profile import load_unified_market_data, run_auction_profile_study
from phase22.config import CONTAMINATED_WINDOWS, DATA_PATHS, ERAS, HORIZONS, PROFILE_TICK, RESULTS, RTH_SESSION, VALUE_AREA_PCT


def write_static_docs(output: Path, config: FrozenConfig) -> None:
    market = load_unified_market_data(config)
    audit = [
        "# Phase 22 Data Audit",
        "",
        "Label: **DEVELOPMENT / DISCOVERY** — no slice treated as genuinely OOS.",
        "",
        "## Contaminated windows",
    ]
    for window in CONTAMINATED_WINDOWS:
        audit.append(f"- {window}")
    audit.extend(["", "## Sources"])
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

    profile_doc = [
        "# Profile Construction",
        "",
        f"Session: prior RTH only (`{RTH_SESSION}` America/Chicago).",
        f"Bin width: **{PROFILE_TICK} points** (NQ minimum tick).",
        f"Value area: **{int(VALUE_AREA_PCT * 100)}%** expanded from POC using adjacent-bin volume tie-break.",
        "",
        "## Approximation note",
        "Tick-level volume-at-price is unavailable in stored 5m OHLCV.",
        "Each bar's volume is distributed uniformly across tick bins touched by [low, high].",
        "POC/VAH/VAL are research approximations, not exchange-confirmed TPO profiles.",
        "",
        "Profiles lock after prior RTH completes and become available at the next RTH open.",
    ]
    (output / "profile_construction.md").write_text("\n".join(profile_doc) + "\n")

    event_doc = [
        "# Auction Event Definitions",
        "",
        f"Horizons: {HORIZONS} bars from event close.",
        "",
        "## Acceptance / rejection (one-bar rule)",
        "- ACCEPTANCE_ABOVE_VAH: prior bar close > VAH and current bar close > VAH",
        "- ACCEPTANCE_BELOW_VAL: prior bar close < VAL and current bar close < VAL",
        "- REJECTION_ABOVE_VAH: prior bar closed above VAH; current bar closes inside value",
        "- REJECTION_BELOW_VAL: prior bar closed below VAL; current bar closes inside value",
        "",
        "## De-duplication",
        f"One event per session/type/level until price exits interaction by > {0.5} ATR from level.",
    ]
    (output / "event_definitions.md").write_text("\n".join(event_doc) + "\n")


def main() -> int:
    config = FrozenConfig()
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_static_docs(RESULTS, config)
    manifest = run_auction_profile_study(output=RESULTS, config=config)
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
