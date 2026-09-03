#!/usr/bin/env python3
"""Run Phase 24 entry signal precision optimization."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase24.analyze_entry_precision import run_entry_precision_study
from phase24.config import RESULTS


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    manifest = run_entry_precision_study(output=RESULTS)
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
