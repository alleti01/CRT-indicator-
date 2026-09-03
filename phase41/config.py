"""Phase 41 configuration — preregistered before discovery."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase41" / "results" / "major_reversal_discovery"

P37_SIGNAL_MAP = ROOT / "phase37" / "results" / "concurrent_reversal_parity" / "pine_reference_map.csv"
P40_SIGNAL_MAP = ROOT / "phase40" / "results" / "impulse_filtered_pine" / "pine_reference_map.csv"

RTH_SESSION = "0930-1600"
REPLAY_START = "2018-01-01"

# Post-hoc opportunity labeling (ground truth only — NOT used for signals)
PIVOT_LEFT = 4
PIVOT_RIGHT = 4
CLUSTER_BARS = 6
OPPORTUNITY_SENSITIVITY = (
    {"mfe_r": 1.5, "mae_r": 0.5, "hold_bars": 4, "label": "1.5R_before_0.5R_60m"},
    {"mfe_r": 2.0, "mae_r": 0.75, "hold_bars": 6, "label": "2R_before_0.75R_90m"},
    {"mfe_r": 2.0, "mae_r": 1.0, "hold_bars": 6, "label": "2R_before_1R_90m"},
    {"mfe_r": 2.0, "mae_r": 1.0, "hold_bars": 8, "label": "2R_before_1R_120m"},
    {"mfe_r": 2.5, "mae_r": 1.0, "hold_bars": 8, "label": "2.5R_before_1R_120m"},
    {"mfe_r": 3.0, "mae_r": 1.0, "hold_bars": 8, "label": "3R_before_1R_120m"},
)

# Primary label (selected before signal discovery)
PRIMARY_OPPORTUNITY = {"mfe_r": 2.0, "mae_r": 1.0, "hold_bars": 6, "label": "2R_before_1R_90m"}
LABEL_RISK_ATR = 0.75

# Capture windows (causal proximity to existing signals vs post-hoc extreme)
CAPTURE_BEFORE_BARS = 2
CAPTURE_AFTER_BARS = 8

# False-reversal control sampling
FALSE_CONTROL_PER_TRUE = 3

# Execution grid (small, preregistered)
STOP_ATRS = (0.5, 0.75, 1.0, 1.25)
TARGET_RS = (1.5, 2.0, 2.5, 3.0)
HOLD_BARS = (3, 4, 6, 8)  # 45m, 60m, 90m, 120m
ENTRY_VARIANTS = ("CURRENT", "NEXT_OPEN")

# Economic gates
MIN_OOS_N = 300
MIN_OOS_AVGR = 0.15
MIN_OOS_PF = 1.35

from phase29.config import WALK_FORWARD_FOLDS  # noqa: E402
