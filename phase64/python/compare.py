"""Phase64 — statistical comparison helpers."""
from __future__ import annotations

import numpy as np


def lift(p58: float, ctl: float) -> float:
    return (p58 - ctl) / ctl if ctl != 0 else 0.0


def ci_proportion(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    p = min(max(p, 0.0), 1.0)
    se = np.sqrt(max(p * (1 - p) / n, 0))
    return float(p - z * se), float(p + z * se)


def practical_label(abs_diff: float, baseline: float) -> str:
    rel = abs(abs_diff / baseline) if baseline else abs(abs_diff)
    if rel < 0.03:
        return "NEGLIGIBLE"
    if rel < 0.08:
        return "SMALL"
    if rel < 0.15:
        return "MODERATE"
    return "LARGE"


def compare_metric(p58_val: float, ctl_val: float, n58: int, nctl: int) -> dict:
    abs_diff = p58_val - ctl_val
    return {
        "phase58": p58_val,
        "control": ctl_val,
        "abs_diff": abs_diff,
        "lift": lift(p58_val, ctl_val),
        "ci58": ci_proportion(p58_val, n58),
        "practical": practical_label(abs_diff, ctl_val),
    }


def archetype_comparison(p58_summary: dict, ctl_summary: dict) -> dict:
    arches = [
        "CLEAN_UP_EXPANSION", "CLEAN_DOWN_EXPANSION",
        "UP_BREAK_CONTINUATION", "DOWN_BREAK_CONTINUATION",
        "UP_BREAK_FAILURE_TO_DOWN", "DOWN_BREAK_FAILURE_TO_UP",
        "TWO_SIDED_SWEEP_THEN_UP", "TWO_SIDED_SWEEP_THEN_DOWN",
        "TWO_SIDED_CHOP", "COMPRESSION_NO_EXPANSION",
        "LATE_EXPANSION", "EXPLOSIVE_IMMEDIATE_MOVE",
    ]
    out = {}
    for a in arches:
        key = f"arch_{a}"
        p = p58_summary.get(key, 0)
        c = ctl_summary.get(key, 0)
        out[a] = compare_metric(p, c, p58_summary.get("n", 1), ctl_summary.get("n", 1))
    return out
