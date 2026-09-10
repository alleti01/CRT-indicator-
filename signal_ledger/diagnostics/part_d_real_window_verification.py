#!/usr/bin/env python3
"""Part D final verification — insufficient_warmup counts on real analysis windows.

No TV GLD chart CSV exists in-repo for these windows. This tool:
  1. Runs the Phase72B mirror on the same NQ LW windows as Parts B/C.
  2. Synthesizes Part C export-shaped rows (Pine encoding from phase72a_signal_ledger.pine).
  3. Writes window CSVs and loads them through gate_export.load_tv_gate_export.
  4. Applies gate_tri_state evidence/arm interpretation on every bar.

NOT TradingView Pine — same caveat as Part C verification.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58j.research.lw_data import load_markets_lw
from phase72b.python.autonomous_mirror_engine import run_mirror
from phase72b.python.event_log import events_to_dataframe
from phase72b.tools.run_phase72b_parity import window_indices
from signal_ledger.config import GLD_HTF_WARMUP_MIN_BARS_DEFAULT, GATE_NAMES
from signal_ledger.gate_export import load_tv_gate_export
from signal_ledger.gate_tri_state import (
    arm_total_state,
    evidence_threshold_state,
    gate_state_detail_from_export_row,
)

OUT_JSON = ROOT / "signal_ledger" / "reports" / "PART_D_REAL_WINDOW_VERIFICATION.json"
OUT_DIR = ROOT / "signal_ledger" / "reports" / "diagnostics"

WINDOWS = [
    ("aug28_session", "2026-08-28 08:30", "2026-08-28 16:00"),
    ("jul_aug_2026", "2026-07-01 00:00", "2026-08-28 23:59"),
]

WARMUP_MIN = GLD_HTF_WARMUP_MIN_BARS_DEFAULT


def _tot(row: pd.Series, side: str) -> int:
    if side == "long":
        return int(row.ctx_score_long + row.loc_long + row.react_long + row.contra_long)
    return int(row.ctx_score_short + row.loc_short + row.react_short + row.contra_short)


def _encode_part_c_export(df: pd.DataFrame) -> pd.DataFrame:
    """Mirror rows → Part C GLD export columns (Pine semantics on full-history recalc)."""
    snap_long = math.nan
    snap_short = math.nan
    fresh_long = False
    fresh_short = False
    rows: list[dict] = []

    for _, r in df.iterrows():
        bi = int(r.bar_index)
        in_cold = bi < WARMUP_MIN
        ts_ms = int(pd.Timestamp(r.timestamp).tz_convert("UTC").timestamp() * 1000)

        if not in_cold:
            if int(r.p58_state) == 1:
                snap_long = float(_tot(r, "long"))
                fresh_long = True
            else:
                fresh_long = False
            if int(r.p58_state) == -1:
                snap_short = float(_tot(r, "short"))
                fresh_short = True
            else:
                fresh_short = False

        def _prov(fresh: bool, snap: float) -> int:
            if in_cold:
                return 0
            if fresh:
                return 1
            if not math.isnan(snap):
                return 2
            return 0

        prov_l = _prov(fresh_long, snap_long)
        prov_s = _prov(fresh_short, snap_short)

        def _ev(side: str) -> str:
            if in_cold:
                return ""
            return "1" if (bool(r.raw_long) if side == "long" else bool(r.raw_short)) else "0"

        rows.append(
            {
                "time": ts_ms,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "GLD_armed_long": 1 if int(r.p58_state) == 1 else 0,
                "GLD_armed_short": 1 if int(r.p58_state) == -1 else 0,
                "GLD_evidence_threshold_long": _ev("long"),
                "GLD_evidence_threshold_short": _ev("short"),
                "GLD_decide_e_long": 1 if bool(r.raw_long) and bool(r.gate_open) else 0,
                "GLD_decide_e_short": 1 if bool(r.raw_short) and bool(r.gate_open) else 0,
                "GLD_p4_keep_long": 1,
                "GLD_p4_keep_short": 1,
                "GLD_h1_keep_long": 1,
                "GLD_h1_keep_short": 1,
                "GLD_gate_open": 1 if bool(r.gate_open) else 0,
                "GLD_not_in_cooldown": 0 if bool(r.cooldown) else 1,
                "GLD_take_long": 1 if bool(r.signal_long) else 0,
                "GLD_take_short": 1 if bool(r.signal_short) else 0,
                "GLD_bar_time_utc_ms": ts_ms,
                "GLD_htf_warmup_ready": 0 if in_cold else 1,
                "GLD_arm_total_long": "" if prov_l == 0 else snap_long,
                "GLD_arm_total_short": "" if prov_s == 0 else snap_short,
                "GLD_arm_total_long_prov": prov_l,
                "GLD_arm_total_short_prov": prov_s,
                "GLD_pass_reason_code": 1 if in_cold else 0,
            }
        )

    return pd.DataFrame(rows)


def _count_insufficient(gates_df: pd.DataFrame) -> dict:
    ev_long = ev_short = arm_long = arm_short = any_flag = 0
    cold_pass_reason = cold_warmup_false = 0
    samples: list[dict] = []

    for _, row in gates_df.iterrows():
        el = evidence_threshold_state(row, "long")
        es = evidence_threshold_state(row, "short")
        al = arm_total_state(row, "long")
        ass = arm_total_state(row, "short")
        flagged = {el, es, al, ass} & {"insufficient_warmup"}
        pr = row.get("pass_reason_code", 0)
        if not pd.isna(pr) and int(pr) == 1:
            cold_pass_reason += 1
        hw = row.get("htf_warmup_ready")
        if not pd.isna(hw) and not bool(hw):
            cold_warmup_false += 1
        if el == "insufficient_warmup":
            ev_long += 1
        if es == "insufficient_warmup":
            ev_short += 1
        if al == "insufficient_warmup":
            arm_long += 1
        if ass == "insufficient_warmup":
            arm_short += 1
        if flagged:
            any_flag += 1
            if len(samples) < 5:
                detail = gate_state_detail_from_export_row(row)
                samples.append(
                    {
                        "bar_time_utc": row["bar_time_utc"].isoformat(),
                        "evidence_long": el,
                        "evidence_short": es,
                        "arm_long": al,
                        "arm_short": ass,
                        "pass_reason_code": detail.get("pass_reason_code"),
                        "htf_warmup_ready": detail.get("htf_warmup_ready"),
                    }
                )

    return {
        "bars_total": int(len(gates_df)),
        "bars_any_insufficient_warmup": any_flag,
        "bars_evidence_long_insufficient_warmup": ev_long,
        "bars_evidence_short_insufficient_warmup": ev_short,
        "bars_arm_total_long_insufficient_warmup": arm_long,
        "bars_arm_total_short_insufficient_warmup": arm_short,
        "bars_pass_reason_code_1": cold_pass_reason,
        "bars_htf_warmup_ready_false": cold_warmup_false,
        "samples": samples,
    }


def main() -> int:
    m1, m5, m15 = load_markets_lw()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "method": (
            "Mirror Part C export synthesis → gate_export.load_tv_gate_export → gate_tri_state "
            "(same NQ LW windows as Parts B/C; no TV GLD CSV in repo)"
        ),
        "warmup_min_bars": WARMUP_MIN,
        "m1_bars_in_dataset": len(m1),
        "windows": [],
        "negative_control_prefix_bars_0_199": {},
    }

    for wid, start, end in WINDOWS:
        s_i, e_i = window_indices(m1, start, end)
        _, ev, _, _ = run_mirror(m1, m5, m15, s_i, e_i)
        mirror_df = events_to_dataframe(ev)
        raw_csv = OUT_DIR / f"mirror_gld_export_{wid}.csv"
        encoded = _encode_part_c_export(mirror_df)
        encoded.to_csv(raw_csv, index=False)

        gates_df = load_tv_gate_export(raw_csv)
        counts = _count_insufficient(gates_df)
        bi_min = int(mirror_df["bar_index"].min())
        bi_max = int(mirror_df["bar_index"].max())

        report["windows"].append(
            {
                "window_id": wid,
                "start": start,
                "end": end,
                "mirror_bars": int(len(mirror_df)),
                "bar_index_min": bi_min,
                "bar_index_max": bi_max,
                "bars_below_warmup_min_in_window": int((mirror_df["bar_index"] < WARMUP_MIN).sum()),
                "export_csv": str(raw_csv.relative_to(ROOT)),
                **counts,
                "matches_item_1_expectation": (
                    counts["bars_pass_reason_code_1"] == 0
                    and counts["bars_htf_warmup_ready_false"] == 0
                    and counts["bars_any_insufficient_warmup"] == 0
                ),
            }
        )

    # Negative control: first 200 bars of dataset should show cold-start encoding works
    _, ev0, _, _ = run_mirror(m1, m5, m15, 0, min(199, len(m1) - 61))
    prefix_df = events_to_dataframe(ev0)
    prefix_csv = OUT_DIR / "mirror_gld_export_prefix_0_199.csv"
    _encode_part_c_export(prefix_df).to_csv(prefix_csv, index=False)
    prefix_gates = load_tv_gate_export(prefix_csv)
    prefix_counts = _count_insufficient(prefix_gates)
    report["negative_control_prefix_bars_0_199"] = {
        "bars_total": prefix_counts["bars_total"],
        "bars_any_insufficient_warmup": prefix_counts["bars_any_insufficient_warmup"],
        "expected_cold_bars": min(WARMUP_MIN, prefix_counts["bars_total"]),
        "export_csv": str(prefix_csv.relative_to(ROOT)),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
