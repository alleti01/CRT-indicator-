"""Load canonical Phase58D + P4 + H1 trade population."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from phase58g.research.forensics import enrich
from phase58h.research.filters import apply_h_model

ROOT = Path(__file__).resolve().parents[2]


def load_full_audit() -> pd.DataFrame:
    audit = pd.read_parquet(ROOT / "phase58f" / "results" / "confidence_audit.parquet")
    trades = pd.read_parquet(ROOT / "phase58d" / "results" / "trades.parquet")
    trade_cols = [
        "trade_id", "net_R", "gross_R", "cost_R", "direction", "setup_id",
        "signal_m1_i", "entry_i", "entry_price", "exit_i", "exit_price",
        "exit_reason", "stop", "target", "atr", "MFE_R", "MAE_R", "duration_min",
    ]
    trade_cols = [c for c in trade_cols if c in trades.columns]
    audit_cols = [c for c in audit.columns if c not in trade_cols or c == "trade_id"]
    df = audit[audit_cols].merge(trades[trade_cols], on="trade_id", how="inner")
    return enrich(df)


def canonical_trades(population: str = "H1") -> pd.DataFrame:
    """Return trades passing P4 + H1 (default canonical retained population)."""
    full = load_full_audit()
    dec = apply_h_model(full, population)
    return full.loc[dec == "KEEP"].copy()


def rejected_trades(which: str = "H1") -> pd.DataFrame:
    full = load_full_audit()
    p4 = apply_h_model(full, "H0")
    if which == "P4":
        return full.loc[p4 == "ABSTAIN"].copy()
    h1 = apply_h_model(full, "H1")
    return full.loc[(h1 == "ABSTAIN") & (p4 == "KEEP")].copy()
