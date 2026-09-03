#!/usr/bin/env python3
"""Run Phase 20 session liquidity edge discovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase16.config import FrozenConfig
from phase20.analyze_session_liquidity import load_unified_market_data, run_session_liquidity_study
from phase20.config import (
    APPROACH_ATR,
    CONTAMINATED_WINDOWS,
    DATA_PATHS,
    ERAS,
    EVENT_TYPES,
    LEVELS,
    RESET_ATR,
    RESULTS,
    TIME_BUCKETS,
)


def write_static_docs(output: Path, config: FrozenConfig) -> None:
    market = load_unified_market_data(config)
    audit = [
        "# Phase 20 Data Audit",
        "",
        "## Discovery label",
        "All analysis is **DEVELOPMENT / DISCOVERY**. No historical slice is treated as OOS.",
        "",
        "## Previously observed windows",
    ]
    for window in CONTAMINATED_WINDOWS:
        audit.append(f"- {window}")
    audit.extend(
        [
            "",
            "## Local 5m datasets merged",
        ]
    )
    for path in DATA_PATHS:
        audit.append(f"- `{path}`")
    audit.extend(
        [
            "",
            f"## Unified range used",
            f"- Start: `{market.index.min()}`",
            f"- End: `{market.index.max()}`",
            f"- 5m bars: **{len(market):,}**",
            "",
            "## Era boundaries",
        ]
    )
    for era, bounds in ERAS.items():
        audit.append(f"- **{era}:** {bounds[0]} → {bounds[1]}")
    (output / "data_audit.md").write_text("\n".join(audit) + "\n")

    definitions = [
        "# Session Liquidity Event Definitions",
        "",
        "## Timezone",
        f"All timestamps use `{config.exchange_timezone}` (CME/CBOT equity index convention).",
        "",
        "## Levels (causal)",
        "- **PDH/PDL:** prior completed CME session high/low",
        "- **ONH/ONL:** overnight window high/low from session start through 09:30, then locked",
        "- **ORH/ORL:** RTH opening range 09:30–10:00 high/low, then locked",
        "- **PRIOR_RTH_CLOSE:** prior session last RTH close (09:30–16:00)",
        "- **SESSION_OPEN:** current session first RTH bar open (known after 09:30 bar)",
        "",
        "## Interaction events",
        "- **APPROACH:** distance to level ≤ "
        f"{APPROACH_ATR} ATR after being farther on prior bar",
        "- **TOUCH:** first bar where range spans the level",
        "- **SWEEP:** pierce through level and close back on originating side",
        "- **BREAK:** close crosses level vs prior close",
        "- **BREAK_HOLD:** bar after break remains on breakout side",
        "- **BREAK_FAILURE:** bar after break closes back through level",
        "",
        "## De-duplication",
        f"After an event fires for `(session_date, level, event_type)`, suppress repeats until price moves "
        f"**>{RESET_ATR} ATR** away from the level or a new session resets the level.",
        "",
        "## Forward returns",
        "Measured from event bar close over horizons 1/3/6/12/24 five-minute bars.",
        "",
        "## Time buckets",
    ]
    for name, bounds in TIME_BUCKETS.items():
        definitions.append(f"- **{name}:** minutes {bounds[0]}–{bounds[1]} (Chicago local)")
    (output / "event_definitions.md").write_text("\n".join(definitions) + "\n")


def main() -> int:
    config = FrozenConfig()
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_static_docs(RESULTS, config)
    manifest = run_session_liquidity_study(output=RESULTS, config=config)
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
