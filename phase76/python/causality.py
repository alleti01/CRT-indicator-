"""Prefix invariance audit — mandatory before signal research."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .auction_engine import build_auction_features
from .config import CAUSALITY_ATOL, CAUSALITY_RTOL, CHECKPOINTS, PREFIX_CUTOFFS, REPORTS


AUDIT_COLS = [
    "prior_vah",
    "prior_val",
    "prior_poc",
    "prior_vwap",
    "dev_vah",
    "dev_val",
    "dev_poc",
    "dev_vwap",
    "dev_high",
    "dev_low",
    "or_high",
    "or_low",
    "overnight_high",
    "overnight_low",
    "roll_high_5",
    "roll_low_30",
    "in_hvn",
    "in_lvn",
]


def compare_prefix(full: pd.DataFrame, prefix: pd.DataFrame, cutoff: pd.Timestamp) -> dict[str, Any]:
    """Compare feature columns at timestamps <= cutoff (present in both frames)."""
    common_idx = full.index[full.index <= cutoff].intersection(prefix.index)
    if len(common_idx) == 0:
        return {"ok": True, "compared": 0, "mismatches": []}
    mismatches: list[dict] = []
    for col in AUDIT_COLS:
        if col not in full.columns or col not in prefix.columns:
            continue
        a = full.loc[common_idx, col]
        b = prefix.loc[common_idx, col]
        # boolean columns
        if a.dtype == bool or b.dtype == bool:
            ne = (a.fillna(False).astype(bool) != b.fillna(False).astype(bool)).sum()
            if ne:
                mismatches.append({"column": col, "count": int(ne), "type": "bool"})
            continue
        both_nan = a.isna() & b.isna()
        ne = ~both_nan & ~np.isclose(a, b, rtol=CAUSALITY_RTOL, atol=CAUSALITY_ATOL, equal_nan=True)
        if ne.any():
            idx = a.index[ne][0]
            mismatches.append(
                {
                    "column": col,
                    "count": int(ne.sum()),
                    "first_ts": str(idx),
                    "full": float(a.loc[idx]) if pd.notna(a.loc[idx]) else None,
                    "prefix": float(b.loc[idx]) if pd.notna(b.loc[idx]) else None,
                }
            )
    return {"ok": len(mismatches) == 0, "compared": len(common_idx), "mismatches": mismatches}


def run_causality_audit(df: pd.DataFrame) -> dict[str, Any]:
    full = build_auction_features(df)
    results: list[dict] = []
    all_ok = True
    for frac in PREFIX_CUTOFFS:
        cutoff_idx = int(len(df) * frac)
        if cutoff_idx < 1000:
            continue
        cutoff = df.index[cutoff_idx - 1]
        prefix_df = df.iloc[:cutoff_idx]
        prefix_feat = build_auction_features(prefix_df)
        cmp = compare_prefix(full, prefix_feat, cutoff)
        cmp["cutoff_frac"] = frac
        cmp["cutoff_ts"] = str(cutoff)
        results.append(cmp)
        all_ok = all_ok and cmp["ok"]

    report = {
        "verdict": "CAUSALITY_PASS" if all_ok else "CAUSALITY_FAIL",
        "prefix_tests": results,
        "audit_columns": AUDIT_COLS,
        "profile_type": full["profile_type"].iloc[-1] if len(full) else None,
    }
    return report


def write_causality_report(report: dict, path: Path | None = None) -> Path:
    path = path or REPORTS / "PHASE76_CAUSALITY_AUDIT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase76 — Causality / Prefix Audit",
        "",
        f"**Verdict:** `{report['verdict']}`",
        "",
        f"Profile type: **{report.get('profile_type')}**",
        "",
        "## Prefix invariance tests",
        "",
        "| Cutoff | Compared bars | Pass | Mismatches |",
        "|--------|---------------|------|------------|",
    ]
    for t in report["prefix_tests"]:
        mm = len(t["mismatches"])
        lines.append(
            f"| {t['cutoff_frac']:.0%} ({t['cutoff_ts'][:10]}) | {t['compared']:,} | {'PASS' if t['ok'] else 'FAIL'} | {mm} |"
        )
    if report["verdict"] == "CAUSALITY_FAIL":
        lines.extend(["", "## First mismatches", ""])
        for t in report["prefix_tests"]:
            if not t["ok"]:
                for m in t["mismatches"][:5]:
                    lines.append(f"- {t['cutoff_frac']:.0%} `{m['column']}`: {m}")
    else:
        lines.extend(
            [
                "",
                "## Audited fields",
                "",
                ", ".join(f"`{c}`" for c in report["audit_columns"]),
                "",
                "No signal research until CAUSALITY_PASS.",
            ]
        )
    path.write_text("\n".join(lines) + "\n")
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / "02_causality_audit.json").write_text(json.dumps(report, indent=2))
    return path
