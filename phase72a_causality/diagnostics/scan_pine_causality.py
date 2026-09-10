#!/usr/bin/env python3
"""Phase72A causality scan — catalog repaint-prone constructs in frozen Pine."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINE = ROOT / "TV_REVIEW" / "phase72a_autonomous_trader.pine"
EXPECTED_SHA = "d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f"
OUT = ROOT / "phase72a_causality" / "reports" / "PINE_CAUSALITY_SCAN.json"

PATTERNS: list[tuple[str, str]] = [
    ("pivothigh", r"ta\.pivothigh\s*\("),
    ("pivotlow", r"ta\.pivotlow\s*\("),
    ("valuewhen", r"ta\.valuewhen\s*\("),
    ("barssince", r"ta\.barssince\s*\("),
    ("request_security", r"request\.security\s*\("),
    ("lookahead_on", r"lookahead\s*=\s*barmerge\.lookahead_on"),
    ("lookahead_off", r"lookahead\s*=\s*barmerge\.lookahead_off"),
    ("series_negative_offset", r"\[[ ]*-[0-9]+\]"),
    ("bar_index_minus", r"bar_index\s*-\s*[0-9]+"),
    ("bar_index_plus", r"bar_index\s*\+\s*[0-9]+"),
    ("barstate_confirmed", r"barstate\.isconfirmed"),
]


def main() -> int:
    text = PINE.read_text(encoding="utf-8")
    sha = hashlib.sha256(text.encode()).hexdigest()
    lines = text.splitlines()
    hits: dict[str, list[dict]] = {k: [] for k, _ in PATTERNS}

    for name, pat in PATTERNS:
        rx = re.compile(pat)
        for i, line in enumerate(lines, start=1):
            if rx.search(line):
                hits[name].append({"line": i, "text": line.strip()})

    security_calls = []
    for h in hits["request_security"]:
        block = lines[h["line"] - 1 : min(len(lines), h["line"] + 2)]
        joined = " ".join(s.strip() for s in block)
        explicit_off = "lookahead=barmerge.lookahead_off" in joined
        explicit_on = "lookahead=barmerge.lookahead_on" in joined
        security_calls.append(
            {
                "line": h["line"],
                "lookahead_off": explicit_off,
                "lookahead_on": explicit_on,
                "text": joined[:240],
            }
        )

    report = {
        "pine_path": str(PINE),
        "sha256": sha,
        "freeze_ok": sha == EXPECTED_SHA,
        "line_count": len(lines),
        "hits": hits,
        "request_security_audit": security_calls,
        "summary": {
            "pivothigh_count": len(hits["pivothigh"]),
            "pivotlow_count": len(hits["pivotlow"]),
            "valuewhen_count": len(hits["valuewhen"]),
            "barssince_count": len(hits["barssince"]),
            "request_security_count": len(hits["request_security"]),
            "lookahead_on_count": len(hits["lookahead_on"]),
            "lookahead_off_count": len(hits["lookahead_off"]),
            "series_negative_offset_count": len(hits["series_negative_offset"]),
            "security_missing_lookahead": sum(
                1 for s in security_calls if not s["lookahead_off"] and not s["lookahead_on"]
            ),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"FREEZE_OK={report['freeze_ok']}")
    print(f"Wrote {OUT}")
    return 0 if report["freeze_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
