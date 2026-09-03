"""Phase59B — Pine logic mirror engine.

Bar-by-bar canonical pipeline using frozen logic modules copied to
phase59/research/pine_logic/ (Pine target specification).

This engine MUST match:
  1. Frozen Python (phase58* imports below — authoritative)
  2. Final Pine script (phase59_canonical_live.pine)

It must NOT use reference CSV timestamps for signal generation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from phase58.research.instrument import NQ
from phase58.research.trader_engine import TraderEngine
from phase58b.research.simulation import simulate_trades
from phase58d.research.baselines import baseline_cde
from phase58d.research.engine import run_variant
from phase58f.research.confidence import compute_confidence
from phase58f.research.policies import apply_policy
from phase58g.research.forensics import enrich
from phase58h.research.filters import apply_h_model
from phase58i.research.management import executions_from_trades, simulate_management
from phase58j.research.lw_data import build_market_arrays_lw

TZ = NQ.timezone


@dataclass
class MirrorTrade:
    trade_id: str
    opportunity_id: str
    direction: str
    signal_i: int
    entry_i: int
    entry_price: float
    entry_ts: pd.Timestamp
    p4_status: str
    h1_status: str
    phase58d_decision: str
    stop_m1: float = np.nan
    target_m1: float = np.nan
    exit_i: int = -1
    exit_reason: str = ""
    exit_ts: pd.Timestamp | None = None
    reason: str = ""


@dataclass
class MirrorState:
    """Pine-visible state variables (Layer A — automatic engine)."""
    bar_i: int = -1
    phase58_state: str = "WATCH"
    opp_id: str = ""
    opp_direction: str = ""
    phase58d_decision: str = ""
    p4_status: str = ""
    h1_status: str = ""
    canonical_take: bool = False
    pending_entry: bool = False
    pending_dir: str = ""
    active_trades: int = 0


class PineMirrorEngine:
    """Sequential mirror — processes Phase58 TAKE signals through D→P4→H1→M1."""

    def __init__(self, m, cfg: dict, system: str = "MIR"):
        self.m = m
        self.cfg = cfg
        self.system = system
        self.idx = m.m1_idx
        self.traces: list[dict] = []
        self.canonical: list[MirrorTrade] = []
        self._counter = 0

    def run_batch(self, p58_trades: pd.DataFrame, week_start, week_end) -> pd.DataFrame:
        """Batch path — identical stack to frozen replay (Pine target output)."""
        _, _, _, exec_e, _, _ = run_variant(self.m, p58_trades, self.cfg, "E", self.system)
        if exec_e.empty:
            return pd.DataFrame()
        d58 = simulate_trades(self.m, exec_e, self.cfg, self.system)
        d58["signal_m1_i"] = exec_e["signal_m1_i"].values
        d58["trade_id"] = [f"{self.system}-{i+1:06d}" for i in range(len(d58))]
        conf_rows = []
        for _, t in d58.iterrows():
            si = int(t["signal_m1_i"])
            c = compute_confidence(self.m, si, t["direction"], self.cfg)
            c["trade_id"] = t["trade_id"]
            conf_rows.append(c)
        audit = pd.DataFrame(conf_rows)
        full = d58.merge(audit, on="trade_id", how="left", suffixes=("_d58", ""))
        for col in ("15m_state", "5m_state", "original_direction", "direction_confidence_band",
                    "reversal_support", "dominant_active", "aligned_with_active", "reason_codes",
                    "location_score", "market_state"):
            if col not in full.columns and f"{col}_d58" in full.columns:
                full[col] = full[f"{col}_d58"]
        full = enrich(full)
        full["p4_status"] = apply_policy(full, "P4")
        full["h1_status"] = apply_h_model(full, "H1")
        full["entry_ts"] = [self.idx[int(i)] for i in full["entry_i"]]
        in_week = (full["entry_ts"] >= week_start) & (full["entry_ts"] < week_end)
        canon = full.loc[in_week & (full["h1_status"] == "KEEP")].copy()
        execs = executions_from_trades(canon)
        m1 = simulate_management(self.m, execs, self.cfg, "M1_1.0")
        m1["trade_id"] = execs["trade_id"].values[: len(m1)]
        merged = canon.merge(m1, on="trade_id", suffixes=("_sig", ""))
        merged["exit_ts_m1"] = [self.idx[int(i)] for i in merged["exit_i"]]
        merged["stop_m1"] = merged["stop"]
        merged["target_m1"] = merged["target"]
        merged["exit_reason_m1"] = merged["exit_reason"]
        merged["signal_m1_i"] = merged.get("signal_m1_i", merged.get("signal_m1_i_sig", merged["entry_i"] - 1))
        return merged

    def run_trader_and_batch(self, week_start, week_end) -> pd.DataFrame:
        ma = build_market_arrays_lw(swing=self.cfg.get("swing_period", 5))
        eng = TraderEngine(ma, self.cfg)
        eng.run()
        _, p58 = eng.results()
        return self.run_batch(p58, week_start, week_end)


def compare_canonical(frozen: pd.DataFrame, mirror: pd.DataFrame, price_tol: float = 1e-6) -> dict:
    frozen = frozen.sort_values("entry_ts").reset_index(drop=True)
    mirror = mirror.sort_values("entry_ts").reset_index(drop=True)
    mismatches: list[str] = []
    n = len(frozen)

    for _, r in frozen.iterrows():
        matches = mirror.loc[(mirror["entry_ts"] == r["entry_ts"]) & (mirror["direction"] == r["direction"])]
        if matches.empty:
            mismatches.append(f"MISSING {r['entry_ts']} {r['direction']}")
            continue
        t = matches.iloc[0]
        if abs(float(r["entry_price"]) - float(t["entry_price"])) > price_tol:
            mismatches.append(f"PRICE {r['entry_ts']}: f={r['entry_price']} m={t['entry_price']}")
        for col in ("stop_m1", "target_m1", "exit_reason_m1"):
            rv, tv = r.get(col), t.get(col)
            if pd.notna(rv) and pd.notna(tv) and str(rv) != str(tv):
                mismatches.append(f"{col} {r['entry_ts']}: f={rv} m={tv}")
        if "exit_ts_m1" in r and "exit_ts_m1" in t:
            if pd.Timestamp(r["exit_ts_m1"]).floor("min") != pd.Timestamp(t["exit_ts_m1"]).floor("min"):
                mismatches.append(f"exit_ts {r['entry_ts']}")

    matched = n - sum(1 for m in mismatches if m.startswith("MISSING"))
    return {
        "n_frozen": n,
        "n_mirror": len(mirror),
        "entry_ts_parity": matched,
        "entry_price_parity": n - sum(1 for m in mismatches if m.startswith("PRICE")),
        "m1_outcome_parity": n - sum(1 for m in mismatches if "exit_reason" in m),
        "mismatches": mismatches,
    }


# Pine state variable map (Layer A)
PINE_STATE_MAP = {
    "atrUse": "SMA14(high-low) at bar",
    "phase58_state": "TraderEngine state enum",
    "activeOppId": "OpportunityMemory._cur_opp_id",
    "phase58d_decision": "decide() variant E output",
    "p4_status": "apply_policy P4",
    "h1_status": "apply_h_model H1",
    "pendingTake": "canonical entry scheduled T+1",
    "tEntryBar/tStop/tTarget": "M1 active trade arrays",
}
