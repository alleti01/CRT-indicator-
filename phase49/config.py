"""Phase 49 configuration — frozen forward validation."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase49" / "results" / "forward_validation"
FROZEN_MODEL_DIR = ROOT / "phase49" / "frozen_model"

# Frozen forward boundary — DO NOT CHANGE after Phase49 begins
TIMEZONE = "America/Chicago"
INSTRUMENT = "NQ"
DATA_SOURCE = "phase36 15m replay + phase45 stitched 1m"

# Last development 15m bar end; forward signals strictly after this
DEVELOPMENT_CUTOFF = "2026-06-28 23:45:00"
FORWARD_START_TIMESTAMP = "2026-06-29 00:00:00"

# Frozen production candidate (Phase44 → B1 → M0)
FROZEN_B1_RULE = "B1"
FROZEN_B1_WINDOW_MIN = 10  # fold 7 train-selected window (folds 3–7)

MODEL_VERSION = "phase49_frozen_v1"
PHASE44_VERSION = "phase44_quality_filtered_pine"
PHASE45_VERSION = "phase45_b1_wf_stitched"
M0_VERSION = "phase45_simulate_1m"

P44_REF = ROOT / "phase44" / "results" / "quality_filtered_pine" / "quality_reference_all_signals.csv"
P45_WF = ROOT / "phase45" / "results" / "15m_context_1m_execution" / "walk_forward_results.csv"
P48_CONTROL = ROOT / "phase48" / "results" / "trade_management" / "control_management_results.csv"

HISTORICAL = {
    "phase44": {"N": 2275, "AvgR": 0.5683200798575244, "PF": 2.430042753194928, "TotalR": 1292.928181675868, "MaxDD": 15.563767849085934},
    "b1": {
        "N": 1135, "AvgR": 1.6483731365801972, "PF": 17.77573512839063, "MaxDD": 8.38599731970504,
        "fill_rate": 0.6452529846503695, "wrong_direction": 0.06696035242290749, "median_delay": 1.0,
    },
    "m0": {"TotalR": 1870.9035100185238, "WinRate": 0.866079295154185, "N": 1135},
}

CHECKPOINTS = (20, 50, 100, 200)
BOOTSTRAP_SAMPLE_SIZES = (20, 50, 100, 200)
BOOTSTRAP_SEED = 49

DATASET_TAG_HISTORICAL = "HISTORICAL"
DATASET_TAG_FORWARD = "FORWARD"
