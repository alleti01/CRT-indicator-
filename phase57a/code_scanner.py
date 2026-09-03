"""Code-level future-leak scanner for Phase57 research modules."""

from __future__ import annotations

import re
from pathlib import Path

SUSPICIOUS_PATTERNS = [
    (r"shift\s*\(\s*-", "Negative shift — potential future data access"),
    (r"\.bfill\(", "Backward fill — potential future data"),
    (r"center\s*=\s*True", "Centered rolling window — uses future bars"),
    (r"iloc\s*\[\s*i\s*\+", "Forward iloc indexing — potential lookahead"),
    (r"values\s*\[\s*i\s*\+\s*\d", "Forward array indexing in loop"),
    (r"\.shift\s*\(\s*-\d", "Explicit negative shift"),
    (r"searchsorted.*side\s*=\s*['\"]left['\"]", "Left-side searchsorted (may include current)"),
    (r"argmax|argmin", "argmax/argmin — may select future extremum"),
    (r"\.max\(\)|\.min\(\)", "Global max/min on full array (check scope)"),
    (r"qcut.*score", "Global qcut — check if fitted on train only"),
]


def scan_file(path: Path) -> list[dict]:
    findings = []
    text = path.read_text()
    for line_no, line in enumerate(text.splitlines(), 1):
        for pattern, desc in SUSPICIOUS_PATTERNS:
            if re.search(pattern, line):
                findings.append({
                    "file": str(path.relative_to(path.parents[1])),
                    "line": line_no,
                    "pattern": pattern,
                    "description": desc,
                    "code": line.strip()[:120],
                })
    return findings


def scan_phase57(phase57_root: Path) -> list[dict]:
    all_findings = []
    for py in sorted(phase57_root.rglob("*.py")):
        all_findings.extend(scan_file(py))
    return all_findings
