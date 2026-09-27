"""Print the latest shadow vision row. No order controls."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    path = Path("cdx_vision/logs/vision_levels.jsonl")
    if not path.exists() or path.stat().st_size == 0:
        print("no vision rows")
        return 0
    last = path.read_text(encoding="utf-8").splitlines()[-1]
    row = json.loads(last)
    print("signal_id", row.get("signal_id"))
    print("direction", row.get("webhook_direction"))
    print("status", row.get("validation_status"))
    print("entry", row.get("entry"), row.get("entry_source"))
    print("stop", row.get("stop"))
    print("tp1", row.get("tp1"))
    print("tp2", row.get("tp2"))
    print("reasons", ",".join(row.get("reason_codes") or []))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
