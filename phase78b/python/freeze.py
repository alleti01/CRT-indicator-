"""Verify frozen Phase78 implementation via hashes and metric reproduction."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CHECKPOINTS, FREEZE_FILES, PHASE78_ROOT, REPORTS


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def build_freeze_manifest() -> dict:
    files = {}
    for rel in FREEZE_FILES:
        p = PHASE78_ROOT / rel
        if p.exists():
            files[rel] = file_sha256(p)
    return {"phase78_root": str(PHASE78_ROOT), "files": files}


def verify_cached_entries(entries_path: Path) -> dict:
    e = pd.read_parquet(entries_path)
    valid_risk = e.apply(
        lambda r: (r["entry_price"] - r["stop"] if r["direction"] == "LONG" else r["stop"] - r["entry_price"]),
        axis=1,
    )
    return {
        "n_entries": len(e),
        "long_n": int((e["direction"] == "LONG").sum()),
        "short_n": int((e["direction"] == "SHORT").sum()),
        "gross_avg_r": float(e["outcome_r"].mean()),
        "real_plus1": float(e["plus_1.0R_before_minus_1R"].mean()),
        "invalid_risk_n": int((valid_risk <= 0).sum()),
    }


def verify_reproduction(manifest: dict, metrics: dict, window_metrics: dict) -> tuple[bool, dict]:
    targets = {
        "n_entries": (6601, 0),
        "long_n": (1345, 0),
        "short_n": (5256, 0),
        "gross_avg_r": (-0.075, 0.01),
        "real_plus1": (0.474, 0.01),
        "windows": (6826, 0),
        "windows_with_sweep": (6826, 0),
    }
    checks = {}
    ok = True
    for k, (exp, tol) in targets.items():
        got = window_metrics.get(k, metrics.get(k))
        if got is None:
            checks[k] = {"expected": exp, "got": None, "pass": False}
            ok = False
            continue
        if isinstance(exp, int):
            passed = int(got) == exp
        else:
            passed = abs(float(got) - exp) <= tol
        checks[k] = {"expected": exp, "got": got, "pass": passed}
        if not passed:
            ok = False
    return ok, checks


def write_freeze(manifest: dict, metrics: dict, window_metrics: dict, checks: dict, passed: bool) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = {"manifest": manifest, "entry_metrics": metrics, "window_metrics": window_metrics, "checks": checks, "pass": passed}
    (CHECKPOINTS / "00_PHASE78_FREEZE.json").write_text(json.dumps(out, indent=2, default=str))
    lines = [
        "# Phase78B Freeze Verification",
        "",
        f"**PASS:** {passed}",
        "",
        "## File hashes",
    ]
    for k, v in manifest["files"].items():
        lines.append(f"- `{k}`: `{v[:16]}…`")
    lines.extend(["", "## Metric checks", ""])
    for k, c in checks.items():
        lines.append(f"- {k}: expected {c['expected']}, got {c['got']}, pass={c['pass']}")
    (REPORTS / "PHASE78B_FREEZE.md").write_text("\n".join(lines))
