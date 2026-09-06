"""Map Phase78 liquidity types to forensic taxonomy."""
from __future__ import annotations

EXTERNAL_TYPES = frozenset(
    {
        "PRIOR_SESSION_HIGH",
        "PRIOR_SESSION_LOW",
        "OVERNIGHT_HIGH",
        "OVERNIGHT_LOW",
        "SESSION_HIGH_PRE_WINDOW",
        "SESSION_LOW_PRE_WINDOW",
    }
)

INTERNAL_TYPES = frozenset(
    {
        "SWING_HIGH",
        "SWING_LOW",
        "EQUAL_HIGHS",
        "EQUAL_LOWS",
    }
)

# Spec alias labels for reporting
REPORT_LABELS = {
    "PRIOR_SESSION_HIGH": "PREVIOUS_SESSION_HIGH",
    "PRIOR_SESSION_LOW": "PREVIOUS_SESSION_LOW",
    "SESSION_HIGH_PRE_WINDOW": "CURRENT_SESSION_PREWINDOW_HIGH",
    "SESSION_LOW_PRE_WINDOW": "CURRENT_SESSION_PREWINDOW_LOW",
    "SWING_HIGH": "CAUSAL_SWING_HIGH",
    "SWING_LOW": "CAUSAL_SWING_LOW",
    "OVERNIGHT_HIGH": "OVERNIGHT_HIGH",
    "OVERNIGHT_LOW": "OVERNIGHT_LOW",
    "EQUAL_HIGHS": "EQUAL_HIGHS",
    "EQUAL_LOWS": "EQUAL_LOWS",
}


def classify_level(level_type: str) -> str:
    if level_type in EXTERNAL_TYPES:
        return "EXTERNAL_MAJOR"
    if level_type in INTERNAL_TYPES:
        return "INTERNAL_SHORT_TERM"
    return "OTHER"


def report_label(level_type: str) -> str:
    return REPORT_LABELS.get(level_type, level_type)


def bucket_first_sweep(level_type: str) -> str:
    lt = report_label(level_type)
    if lt.startswith("PREVIOUS_SESSION") or lt.startswith("CURRENT_SESSION"):
        return "SESSION_PREWINDOW_H/L" if "PREWINDOW" in lt else "PREVIOUS_SESSION_H/L"
    if lt.startswith("OVERNIGHT"):
        return "OVERNIGHT_H/L"
    if lt.startswith("CAUSAL_SWING") or lt.startswith("EQUAL"):
        return "ROLLING_SHORT_TERM"
    return "OTHER"
