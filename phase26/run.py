#!/usr/bin/env python3
"""Run Phase 26 high-expectancy entry discovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase26.analyze import run_phase26
from phase26.config import RESULTS


def main() -> int:
    manifest = run_phase26(output=RESULTS)
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
