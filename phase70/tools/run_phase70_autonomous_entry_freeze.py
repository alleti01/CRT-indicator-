#!/usr/bin/env python3
"""Phase70 Section 1 — freeze audit for Phase72A Autonomous Trader entry stream."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase69.python.entry_freeze import config_hash, executions, load_frozen_entries
from phase72a.tools.build_autonomous_pine import build  # noqa: F401 — documents pine builder

PINE_AUTONOMOUS = ROOT / "TV_REVIEW" / "phase72a_autonomous_trader.pine"
PINE_GHOSTS = ROOT / "TV_REVIEW" / "phase72a_python_review_ghosts.pine"
REPORTS = ROOT / "phase70" / "reports"
CHECK = ROOT / "phase70" / "checkpoints"


def pine_hash() -> str:
    if not PINE_AUTONOMOUS.exists():
        return "MISSING"
    return hashlib.sha256(PINE_AUTONOMOUS.read_bytes()).hexdigest()[:16]


def frozen_python_stream() -> pd.DataFrame:
    entries = load_frozen_entries()
    return executions(entries)


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    CHECK.mkdir(parents=True, exist_ok=True)

    py = frozen_python_stream()
    ph = pine_hash()
    sh = config_hash()

    # Phase72A autonomous is NOT exported from TV; no parquet of Pine TAKE events exists.
    autonomous_export_exists = False
    ghost_is_reference = True

    verdict = "ENTRY_STREAM_MISMATCH"
    reason = (
        "Phase72A Autonomous Trader (Pine) signal stream is not byte-identical to frozen Python "
        f"Phase60 H1 KEEP stream (hash {sh}, N={len(py):,}). "
        "Python Review Ghosts are diagnostic-only (frozen Python timestamps). "
        "No automated Pine→Python signal export exists. Phase70 on the ACTUAL TV autonomous "
        "stream cannot proceed until entry events are exported or signal parity is proven."
    )

    freeze = {
        "verdict": verdict,
        "autonomous_pine_file": str(PINE_AUTONOMOUS.relative_to(ROOT)),
        "autonomous_pine_hash": ph,
        "ghost_pine_file": str(PINE_GHOSTS.relative_to(ROOT)),
        "ghost_is_diagnostic_only": ghost_is_reference,
        "python_mirror_management": "phase72a/python/pine_mirror.py (management only, not signals)",
        "frozen_python_source": "phase60/diagnostics/cache/canon_full_phase60.parquet",
        "frozen_signal_hash": sh,
        "frozen_python_N": len(py),
        "frozen_python_long": int((py["direction"] == "LONG").sum()),
        "frozen_python_short": int((py["direction"] == "SHORT").sum()),
        "frozen_python_first": str(py["entry_ts"].min()),
        "frozen_python_last": str(py["entry_ts"].max()),
        "autonomous_export_exists": autonomous_export_exists,
        "phase72a_signal_parity_status": "PENDING_TV (see phase72a/checkpoints/10_signal_parity.json)",
        "reason": reason,
    }

    (CHECK / "00_autonomous_entry_stream.json").write_text(json.dumps(freeze, indent=2))

    md = "\n".join([
        "# Phase70 Entry Stream Freeze",
        "",
        "## Intended research object",
        "",
        "**Phase72A Autonomous Trader** (`TV_REVIEW/phase72a_autonomous_trader.pine`)",
        "",
        "Labels: `SIGNAL_LONG`, `SIGNAL_SHORT`, `ENTER_LONG`, `ENTER_SHORT`, `EXIT_*`",
        "",
        "**NOT** `phase72a_python_review_ghosts.pine` (Python reference markers only).",
        "",
        "## Autonomous Pine",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| File | `{PINE_AUTONOMOUS.relative_to(ROOT)}` |",
        f"| Pine hash | `{ph}` |",
        f"| Signal engine | Phase59 D→P4→H1 stack + Phase60 causal HTF |",
        f"| Management | Phase71 one-position + T5 |",
        "",
        "## Frozen Python stream (Phase60 causal)",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Signal hash | `{sh}` |",
        f"| N | {len(py):,} |",
        f"| LONG | {int((py['direction']=='LONG').sum()):,} |",
        f"| SHORT | {int((py['direction']=='SHORT').sum()):,} |",
        f"| First entry | {py['entry_ts'].min()} |",
        f"| Last entry | {py['entry_ts'].max()} |",
        "",
        "## Parity status",
        "",
        "| Comparison | Result |",
        "|------------|--------|",
        "| Autonomous Pine vs frozen Python | **NOT IDENTICAL** (signal count parity unproven) |",
        "| Ghost Pine vs frozen Python | Ghosts match Python timestamps by construction |",
        "| Autonomous Pine vs Ghosts | **Different purpose** — ghosts ≠ autonomous fires |",
        "",
        "## Verdict",
        "",
        f"## **{verdict}**",
        "",
        reason,
        "",
        "## Required before Phase70 on TV autonomous stream",
        "",
        "1. Export autonomous `SIGNAL_*` / `ENTER_*` events from TradingView (or Pine signal log), OR",
        "2. Prove Python replay of Phase72A signal path matches Pine event-for-event, OR",
        "3. Accept research on frozen Python stream only (already completed — see Phase70 discovery report).",
        "",
        "## Prior Phase70 completion (frozen Python stream)",
        "",
        "Historical Phase70 on hash `0da41f282174679f` already completed:",
        "",
        "- **KEEP:** T5 time/progress (15m, MFE < 1R → exit)",
        "- **REJECT:** late/chase filter, failure exit, reversal entry",
        "",
        "Phase71 frozen trader implements T5 only.",
        "",
        "**Do not re-run Phase70 optimization on Pine until entry stream is frozen.**",
    ])
    (REPORTS / "PHASE70_ENTRY_STREAM_FREEZE.md").write_text(md)
    print(json.dumps({"verdict": verdict, "frozen_N": len(py), "pine_hash": ph}, indent=2))


if __name__ == "__main__":
    main()
