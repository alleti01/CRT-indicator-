"""Phase 27 configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase27" / "results" / "order_flow_entry_edge"
DATA_RAW = ROOT / "phase27" / "data" / "raw"

# Pilot approved under $20 gate (trades schema)
PILOT_START = "2024-01-01"
PILOT_END = "2024-02-01"
PILOT_SYMBOL = "NQ.v.0"
PILOT_SCHEMA = "trades"
PILOT_DATASET = "GLBX.MDP3"
PILOT_ESTIMATED_COST_USD = 10.43

NQ_5M_PATHS = (
    ROOT / "phase16/data/processed/nq_5m_oos_20171001_20201201.csv",
    ROOT / "phase18/data/processed/nq_5m.csv",
    ROOT / "phase16/data/processed/nq_5m.csv",
)

PRIMARY_PROFIT_ATR = 1.0
PRIMARY_LOSS_ATR = 0.5
PRIMARY_HORIZON_BARS = 24

ROUND_TURN_COST_USD = 14.50
NQ_DOLLARS_PER_POINT = 20.0
RISK_ATR_FOR_COST = 0.5

FLOW_WINDOWS_SECONDS = (30, 60, 120, 300, 600)

WALK_FORWARD_FOLDS = (
    ("2024-01-01", "2024-01-15", "2024-01-16", "2024-02-01"),
)

PRECISION_FRACTIONS = (1.0, 0.50, 0.30, 0.20, 0.10, 0.05, 0.02, 0.01, 0.005)
