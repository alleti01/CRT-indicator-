#!/usr/bin/env python3
"""Generate Phase51 frozen model manifest and embed hash in Pine."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase51.frozen import embed_hash_in_pine, write_frozen_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Phase51 frozen model manifest")
    parser.add_argument(
        "--forward-start-ct",
        default="2026-08-26 11:30:00",
        help="Forward start timestamp CT (must match Pine input)",
    )
    args = parser.parse_args()
    manifest, model_hash = write_frozen_snapshot(forward_start_ct=args.forward_start_ct)
    embed_hash_in_pine(model_hash)
    print(f"MODEL HASH: {model_hash}")
    print(f"FORWARD START CT: {args.forward_start_ct}")
    print(f"Manifest: phase51/frozen_model/model_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
