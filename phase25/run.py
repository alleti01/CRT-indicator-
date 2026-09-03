#!/usr/bin/env python3
"""Run Phase 25 BOS trade architecture optimization."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase25.config import RESULTS
from phase25.run_bos_optimization import run_phase25


def main() -> int:
    manifest = run_phase25(output=RESULTS)
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
