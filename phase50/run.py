"""Phase 50 orchestrator — export reference data and parity artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from .config import P44_PINE, PINE_DIR, RESULTS
from .export_reference import write_reference_exports


def run_phase50(*, output: Path = RESULTS) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    PINE_DIR.mkdir(parents=True, exist_ok=True)

    export_meta = write_reference_exports(output)
    manifest = {
        "phase": 50,
        "pine_indicator": str(PINE_DIR / "phase50_nq_indicator.pine"),
        "phase44_pine_source": str(P44_PINE),
        "export": export_meta,
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    run_phase50()
