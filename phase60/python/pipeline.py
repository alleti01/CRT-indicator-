"""Phase60 frozen pipeline — patches HTF context only."""
from __future__ import annotations

import contextlib
from typing import Iterator

import pandas as pd

import phase58d.research.context_maps as _cm
import phase58d.research.engine as _eng
import phase58d.research.evidence as _ev
from phase60.python import context_maps as p60_cm
from phase60.python import evidence as p60_ev


@contextlib.contextmanager
def phase60_htf_context() -> Iterator[None]:
    """Temporarily route Phase58D HTF context through Phase60 causal maps."""
    saved = {
        "ctx15_at_1m": _cm.ctx15_at_1m,
        "ctx5_at_1m": _cm.ctx5_at_1m,
        "loc5_at_1m": _cm.loc5_at_1m,
        "location_score": _cm.location_score,
        "m1_market_view": _cm.m1_market_view,
        "direction_score": _cm.direction_score,
        "compute_evidence_ev": _ev.compute_evidence,
        "compute_evidence_eng": _eng.compute_evidence,
    }
    _cm.ctx15_at_1m = p60_cm.ctx15_at_1m
    _cm.ctx5_at_1m = p60_cm.ctx5_at_1m
    _cm.loc5_at_1m = p60_cm.loc5_at_1m
    _cm.location_score = p60_cm.location_score
    _cm.m1_market_view = p60_cm.m1_market_view
    _cm.direction_score = p60_cm.direction_score
    _ev.compute_evidence = p60_ev.compute_evidence
    _eng.compute_evidence = p60_ev.compute_evidence
    try:
        yield
    finally:
        _cm.ctx15_at_1m = saved["ctx15_at_1m"]
        _cm.ctx5_at_1m = saved["ctx5_at_1m"]
        _cm.loc5_at_1m = saved["loc5_at_1m"]
        _cm.location_score = saved["location_score"]
        _cm.m1_market_view = saved["m1_market_view"]
        _cm.direction_score = saved["direction_score"]
        _ev.compute_evidence = saved["compute_evidence_ev"]
        _eng.compute_evidence = saved["compute_evidence_eng"]


def run_full_canonical(m, p58: pd.DataFrame, cfg: dict, tag: str = "P60") -> pd.DataFrame:
    """Full canonical path: Phase58D → confidence → P4 → H1 → M1."""
    from phase58b.research.simulation import simulate_trades
    from phase58d.research.baselines import baseline_cde
    from phase58f.research.confidence import compute_confidence
    from phase58f.research.policies import apply_policy
    from phase58g.research.forensics import enrich
    from phase58h.research.filters import apply_h_model
    from phase58i.research.management import executions_from_trades, simulate_management
    from phase58.research.instrument import NQ

    with phase60_htf_context():
        _, _, _, exec_e, _, _ = baseline_cde(m, p58, cfg, "E", tag)
        d58 = simulate_trades(m, exec_e, cfg, tag)
        if not exec_e.empty:
            merge_cols = [
                c
                for c in [
                    "setup_id",
                    "location_score",
                    "direction_score",
                    "reaction_score",
                    "total_evidence",
                    "15m_state",
                ]
                if c in exec_e.columns
            ]
            d58 = d58.merge(exec_e[merge_cols], on="setup_id", how="left")
        d58["signal_m1_i"] = d58.get("signal_m1_i", d58.get("signal_i", d58["entry_i"] - 1))

        conf_rows = []
        for i, t in d58.iterrows():
            si = int(t.get("signal_m1_i", t["entry_i"] - 1))
            c = compute_confidence(m, si, t["direction"], cfg)
            c["trade_id"] = t.get("trade_id", f"{tag}-{i}")
            conf_rows.append(c)
        audit = pd.DataFrame(conf_rows)
        d58["trade_id"] = d58.get("trade_id", [f"{tag}-{i+1:06d}" for i in range(len(d58))])
        full = d58.merge(audit, on="trade_id", how="left", suffixes=("", "_c"))
        full = enrich(full)
        full["p4_status"] = apply_policy(full, "P4")
        full["h1_status"] = apply_h_model(full, "H1")
        full["entry_ts"] = [m.m1_idx[int(i)] for i in full["entry_i"]]
        canon = full.loc[full["h1_status"] == "KEEP"].copy()
        execs = executions_from_trades(canon)
        m1 = simulate_management(m, execs, cfg, "M1_1.0")
        m1["trade_id"] = execs["trade_id"].values[: len(m1)]
        merged = canon.merge(m1, on="trade_id", suffixes=("_d58", "_m1"))
        merged["net_R_m1"] = merged["net_R_m1"].astype(float)
        merged["m1_outcome"] = merged["exit_reason_m1"]
        merged["entry_ts"] = pd.to_datetime(merged["entry_ts"]).dt.tz_convert(NQ.timezone)
    return merged
