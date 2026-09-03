"""Paths for Phase 49 forward data storage."""

from __future__ import annotations

from pathlib import Path

from phase49.config import ROOT

DATA_DIR = ROOT / "phase49" / "data"
HISTORICAL_DIR = DATA_DIR / "historical"
FORWARD_DIR = DATA_DIR / "forward"
INBOUND_DIR = DATA_DIR / "inbound"

FORWARD_1M_PROCESSED = FORWARD_DIR / "nq_continuous_1m_forward.csv"
FORWARD_5M_PROCESSED = FORWARD_DIR / "nq_continuous_5m_forward.csv"
FORWARD_15M_PROCESSED = FORWARD_DIR / "nq_continuous_15m_forward.csv"
FORWARD_MANIFEST = DATA_DIR / "forward_data_manifest.json"

# Bridge sources fill the 1m gap between stitched development data and the cutoff.
BRIDGE_1M_SOURCES = (
    ROOT / "phase16" / "data" / "raw" / "nq_continuous_1m_postwindow_to_20260629T0000CT.csv",
    ROOT / "phase16" / "data" / "raw" / "nq_continuous_1m_postwindow_to_20260629T0000CT.csv.parts",
)

INBOUND_1M_GLOB = "nq_continuous_1m_forward*.csv"
