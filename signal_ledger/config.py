"""Signal quality ledger configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = ROOT / "output"

# Default missed-reversal threshold (R). Sweep via CLI.
DEFAULT_MISSED_REVERSAL_THRESHOLD_R = 1.5

# M0 frozen — must match production research spec (not modified here).
M0_STOP_R = 1.0
M0_TARGET_R = 2.5
M0_MAX_HOLD_MINUTES = 60

# Phase72A entry convention: signal on bar T close → fill at T+1 open.
ENTRY_OFFSET_BARS = 1

# Named TAKE-chain gates (stable keys for aggregation).
# Part C — arm-total provenance codes (GLD_arm_total_*_prov)
ARM_TOTAL_PROV_COLD_START = 0
ARM_TOTAL_PROV_FRESH = 1
ARM_TOTAL_PROV_STALE_HOLD = 2

# Part C — pass reason codes (GLD_pass_reason_code)
PASS_REASON_NONE = 0
PASS_REASON_INSUFFICIENT_WARMUP = 1

# Bounded cold-start window: 12 × 15M bars + swingPeriod (default 185 at swingPeriod=5)
GLD_HTF_LOOKBACK_15M_BARS = 12
GLD_HTF_WARMUP_MIN_BARS_DEFAULT = GLD_HTF_LOOKBACK_15M_BARS * 15 + 5

# Optional Layer D export columns (Part C — not in TAKE-chain GATE_NAMES)
GLD_OPTIONAL_COLS: tuple[str, ...] = (
    "htf_warmup_ready",
    "arm_total_long",
    "arm_total_short",
    "arm_total_long_prov",
    "arm_total_short_prov",
    "pass_reason_code",
    "script_init_utc_ms",
)

# Gates whose TV export may be na (Part C/D — do not coerce to False)
NULLABLE_GATE_NAMES: tuple[str, ...] = (
    "evidence_threshold_long",
    "evidence_threshold_short",
)

GATE_NAMES: tuple[str, ...] = (
    "armed_long",
    "armed_short",
    "evidence_threshold_long",
    "evidence_threshold_short",
    "decide_e_long",
    "decide_e_short",
    "p4_keep_long",
    "p4_keep_short",
    "h1_keep_long",
    "h1_keep_short",
    "gate_open",
    "not_in_cooldown",
    "take_long",
    "take_short",
)


@dataclass
class LedgerConfig:
    start: str
    end: str
    signal_log_paths: list[Path] = field(default_factory=list)
    output_path: Path = DEFAULT_OUTPUT_DIR / "signal_quality_ledger.parquet"
    missed_reversal_threshold_r: float = DEFAULT_MISSED_REVERSAL_THRESHOLD_R
    warmup_bars: int = 3000
