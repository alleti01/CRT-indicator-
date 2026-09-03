"""Phase 24 configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase24" / "results" / "entry_signal_precision"

BASELINE_TRADE_SOURCES = (
    ("phase18/results/base_run/trades.csv", "2018-2023"),
    ("phase17/results/baseline_run/trades.csv", "2024-2026"),
)

NQ_DATA_PATHS = (
    ROOT / "phase16/data/processed/nq_5m_oos_20171001_20201201.csv",
    ROOT / "phase18/data/processed/nq_5m.csv",
    ROOT / "phase16/data/processed/nq_5m.csv",
)

WALK_FORWARD_FOLDS = (
    ("2021-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("2021-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    ("2021-01-01", "2024-12-31", "2025-01-01", "2026-06-26"),
)

RETENTION_FRACTIONS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1)

FEATURE_FAMILIES = {
    "structure": [
        "score",
        "stop_distance_atr",
        "body_to_atr",
        "time_since_setup_bars",
        "time_since_bos_bars",
        "time_since_retest_bars",
        "distance_from_crt_atr",
        "bos_present",
        "retest_present",
        "confirmation_present",
    ],
    "price_quality": [
        "range_atr",
        "body_range_ratio",
        "close_location",
        "upper_wick_ratio",
        "lower_wick_ratio",
        "momentum_3_atr",
        "accel_3",
    ],
    "volatility": [
        "normalized_atr",
        "atr_ratio_6_72",
        "volatility_regime_code",
        "body_atr_pct",
    ],
    "session": [
        "session_bucket",
        "minutes_from_rth_open",
        "day_of_week",
    ],
    "liquidity": [
        "dist_pdh_atr",
        "dist_pdl_atr",
        "dist_onh_atr",
        "dist_onl_atr",
    ],
    "trend": [
        "htf_regime",
        "trend_aligned",
    ],
}
