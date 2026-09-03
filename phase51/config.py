"""Phase51 live forward paper validation configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE51_ROOT = ROOT / "phase51"
FROZEN_MODEL_DIR = PHASE51_ROOT / "frozen_model"
PINE_PATH = PHASE51_ROOT / "pine" / "phase51_nq_live_indicator.pine"
FORWARD_DIR = PHASE51_ROOT / "forward"
RESULTS_DIR = PHASE51_ROOT / "results"

TIMEZONE = "America/Chicago"
SYMBOL = "NQ1!"
CHART_TIMEFRAME = "1"
NQ_TICK = 0.25
PRICE_TOLERANCE = NQ_TICK

MODEL_VERSION = "phase51_frozen_v1"
PHASE44_VERSION = "phase44_quality_filtered_pine"
PHASE45_VERSION = "phase45_b1_wf_stitched"
M0_VERSION = "phase45_simulate_1m"
FROZEN_B1_RULE = "B1"
FROZEN_B1_WINDOW_MIN = 10

# Historical B1 benchmark (Phase45) — not optimization targets
BENCHMARK_N = 1135
BENCHMARK_AVG_R = 1.648
BENCHMARK_PF = 17.78
BENCHMARK_MAX_DD = 8.39
BENCHMARK_FILL_RATE = 0.645
BENCHMARK_MEDIAN_DELAY_MIN = 1.0

CHECKPOINTS = (25, 50, 100, 200)
