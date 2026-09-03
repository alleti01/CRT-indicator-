"""Phase58D signal pipeline — online memory + decision variants."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58b.research.precompute import MTFArrays
from phase58d.research.evidence import compute_evidence, decide
from phase58d.research.opportunity_memory import OppState, OpportunityMemory


def run_variant(
    m: MTFArrays,
    raw_trades: pd.DataFrame,
    cfg: dict,
    variant: str,
    system: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Process Phase58 raw TAKE signals through online opportunity memory."""
    memory = OpportunityMemory(
        structural_gap=cfg.get("structural_gap_bars", 30),
        expire_bars=cfg.get("opportunity_expire_bars", 45),
    )
    df = raw_trades.sort_values("signal_i").reset_index(drop=True)

    memberships: list[tuple[int, str, float, str, bool]] = []
    for _, row in df.iterrows():
        i = int(row["signal_i"])
        direction = row["direction"]
        price = float(row.get("entry_price", m.m1_cl[i]))
        memory.expire_stale(i)
        opp, is_new = memory.match_or_create(i, price, direction)
        memberships.append((i, direction, price, opp.opportunity_id, is_new))

    first_bars = {i for i, _, _, _, is_new in memberships if is_new}
    ev_cache: dict[tuple[int, str], dict] = {}
    if variant in ("D", "E"):
        for i, direction, _, _, is_new in memberships:
            if is_new:
                ev_cache[(i, direction)] = compute_evidence(m, i, direction, cfg)

    decisions: list[dict] = []
    executions: list[dict] = []
    rejected: list[dict] = []
    wait_shadow: list[dict] = []
    pending_wait: dict[str, dict] = {}
    opp_by_id = {o.opportunity_id: o for o in memory.all_opps}

    for i, direction, price, oid, is_new in memberships:
        opp = opp_by_id[oid]
        if is_new:
            ev = ev_cache.get((i, direction), _blank_evidence(take=(variant == "C")))
            opp.location_score = ev["location_score"]
            opp.direction_score = ev["direction_score"]
            opp.reaction_score = ev["reaction_score"]
            opp.ctx15_state = ev["15m_state"]
            opp.ctx5_dir = ev["5m_state"]
            opp.max_evidence = max(opp.max_evidence, ev["total_evidence"])
        else:
            ev = _blank_evidence()

        state_before = opp.state.value
        if is_new:
            opp.state = OppState.DETECTED
            opp.armed_i = i

        decision = "UPDATE"
        entry_i = -1
        entry_price = np.nan

        if is_new:
            decision, d_reasons = decide(ev, variant, cfg, 0)
            if decision == "TAKE":
                opp.state = OppState.TAKE
                opp.take_i = i
                entry_i = min(i + 1, m.m1_n - 1)
                entry_price = float(m.m1_op[entry_i])
                memory.mark_traded(oid, i)
                executions.append(_exec_row(opp, i, entry_i, entry_price, ev, system, decision))
            elif decision == "PASS":
                opp.state = OppState.PASS
                opp.pass_i = i
                rejected.append(_shadow_row(opp, i, entry_i, entry_price, ev, decision, system))
            elif decision == "WAIT":
                opp.state = OppState.WAIT
                pending_wait[oid] = {"wait_bars": 1}
                wait_shadow.append(_wait_row(opp, i, ev, system))

            decisions.append(_decision_row(m, i, oid, state_before, opp, direction, ev, decision, True, entry_price, system))

    opps = _opportunities_df(memory)
    updates = pd.DataFrame(memory.updates) if memory.updates else pd.DataFrame()
    return opps, updates, pd.DataFrame(decisions), pd.DataFrame(executions), pd.DataFrame(rejected), pd.DataFrame(wait_shadow)


def _decision_row(m, i, oid, state_before, opp, direction, ev, decision, is_new, entry_price, system) -> dict:
    return {
        "timestamp": str(m.m1_idx[i]),
        "bar_i": i,
        "opportunity_id": oid,
        "state_before": state_before,
        "state_after": opp.state.value,
        "direction": direction,
        "location_score": ev["location_score"],
        "direction_score": ev["direction_score"],
        "reaction_score": ev["reaction_score"],
        "total_evidence": ev["total_evidence"],
        "15m_state": ev["15m_state"],
        "5m_state": ev["5m_state"],
        "reason_codes": "|".join(ev.get("reason_codes", [])),
        "decision": decision,
        "is_new_opportunity": is_new,
        "entry_price": entry_price,
        "system": system,
    }


def _exec_row(opp, signal_i, entry_i, entry_price, ev, system, decision) -> dict:
    return {
        "opportunity_id": opp.opportunity_id,
        "setup_id": opp.opportunity_id,
        "direction": opp.direction,
        "signal_i": signal_i,
        "signal_m1_i": signal_i,
        "entry_i": entry_i,
        "entry_price": entry_price,
        "variant": system,
        "tag": decision,
        "delay_bars_1m": entry_i - signal_i if entry_i >= 0 else 0,
        "15m_state": ev["15m_state"],
        "15m_strength": ev.get("15m_strength", 0),
        "location_score": ev["location_score"],
        "direction_score": ev["direction_score"],
        "reaction_score": ev["reaction_score"],
        "total_evidence": ev["total_evidence"],
    }


def _shadow_row(opp, signal_i, entry_i, entry_price, ev, decision, system) -> dict:
    ei = signal_i + 1 if entry_i < 0 else entry_i
    return {
        "opportunity_id": opp.opportunity_id,
        "direction": opp.direction,
        "signal_i": signal_i,
        "shadow_entry_i": ei,
        "decision": decision,
        "system": system,
        **{k: ev[k] for k in ("location_score", "direction_score", "reaction_score", "total_evidence", "15m_state")},
    }


def _wait_row(opp, signal_i, ev, system) -> dict:
    return {
        "opportunity_id": opp.opportunity_id,
        "direction": opp.direction,
        "wait_signal_i": signal_i,
        "immediate_entry_i": signal_i + 1,
        "system": system,
        **{k: ev[k] for k in ("location_score", "direction_score", "reaction_score", "total_evidence")},
    }


def _opportunities_df(memory: OpportunityMemory) -> pd.DataFrame:
    rows = []
    for o in memory.all_opps:
        rows.append({
            "opportunity_id": o.opportunity_id,
            "direction": o.direction,
            "created_i": o.created_i,
            "created_price": o.created_price,
            "state": o.state.value,
            "armed_i": o.armed_i,
            "take_i": o.take_i,
            "pass_i": o.pass_i,
            "signal_count": o.signal_count,
            "update_count": o.update_count,
            "location_score": o.location_score,
            "direction_score": o.direction_score,
            "reaction_score": o.reaction_score,
            "max_evidence": o.max_evidence,
            "15m_state_at_creation": o.ctx15_state,
            "5m_state_at_creation": o.ctx5_dir,
            "traded": o.traded,
        })
    return pd.DataFrame(rows)


def _blank_evidence(take: bool = False) -> dict:
    return {
        "location_score": 0,
        "direction_score": 0,
        "reaction_score": 0,
        "contradiction": 0,
        "total_evidence": 4 if take else 0,
        "15m_state": "NEUTRAL",
        "15m_strength": 0,
        "5m_state": "NEUTRAL",
        "5m_location_score": 0,
        "strong_contradiction": False,
        "reason_codes": [],
    }


def online_memory_at_signals(trades: pd.DataFrame, structural_gap: int = 30) -> pd.DataFrame:
    mem = OpportunityMemory(structural_gap=structural_gap)
    opp_ids = []
    for _, row in trades.sort_values("signal_i").iterrows():
        opp, _ = mem.match_or_create(int(row["signal_i"]), float(row["entry_price"]), row["direction"])
        opp_ids.append(opp.opportunity_id)
    out = trades.sort_values("signal_i").reset_index(drop=True).copy()
    out["opportunity_id"] = opp_ids
    return out
