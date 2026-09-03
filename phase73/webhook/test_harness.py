#!/usr/bin/env python3
"""Send fake Pine webhook alerts to local receiver."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase73.webhook.schemas import make_test_signal


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8787/webhook")
    ap.add_argument("--event", default="SIGNAL_LONG", choices=["SIGNAL_LONG", "SIGNAL_SHORT"])
    args = ap.parse_args()
    sig = make_test_signal(args.event)
    payload = sig.to_dict()
    req = urllib.request.Request(
        args.url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print(resp.read().decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
