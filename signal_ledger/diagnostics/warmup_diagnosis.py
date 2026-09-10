#!/usr/bin/env python3
"""Part B — warmup diagnosis for Layer D gate export semantics.

Simulates TradingView chart history truncation (prefix load) vs full history
at signal bars. Reports when mirror-derived gate inputs diverge and documents
implications for ``gldSnapArmTotal*`` / ``GLD_evidence_threshold_*`` export.

NOT TradingView bar replay — Python mirror proxy only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58j.research.lw_data import load_markets_lw
from phase72b.python.autonomous_mirror_engine import run_mirror
from phase72b.python.config import DEFAULT_CFG
from phase72b.python.event_log import events_to_dataframe
from phase72b.python.pine_features import precompute_features
from phase72b.python.series_builder import build_pine_series
from phase72b.tools.run_phase72b_parity import window_indices

OUT = ROOT / "signal_ledger" / "reports" / "PART_B_WARMUP_DIAGNOSIS.json"

WINDOWS = [
    ("aug28_session", "2026-08-28 08:30", "2026-08-28 16:00"),
    ("aug30_chi_evening", "2026-08-30 17:00", "2026-08-30 22:30"),
]

FEATURE_COLS = (
    "ctx_dir",
    "bull_sc",
    "bear_sc",
    "loc_long",
    "loc_short",
    "react_long",
    "react_short",
)


def _slice_markets(m1, m5, m15, start_i: int):
    m1s = m1.iloc[start_i:].copy()
    t0, t1 = m1s.index[0], m1s.index[-1]
    m5s = m5.loc[(m5.index >= t0.floor("5min")) & (m5.index <= t1)].copy()
    m15s = m15.loc[(m15.index >= t0.floor("15min")) & (m15.index <= t1)].copy()
    return m1s, m5s, m15s


def _arm_total(feat, k: int, direction: str) -> int:
    react = feat.react_long[k] if direction == "LONG" else feat.react_short[k]
    loc = feat.loc_long[k] if direction == "LONG" else feat.loc_short[k]
    ctx_sc = min(2, feat.bull_sc[k] if direction == "LONG" else feat.bear_sc[k])
    contra = 0
    ctx_dir = feat.ctx_dir[k]
    if direction == "LONG" and ctx_dir == "NEUTRAL" and feat.bear_sc[k] >= 2:
        contra -= 1
    if direction == "SHORT" and ctx_dir == "NEUTRAL" and feat.bull_sc[k] >= 2:
        contra -= 1
    return int(ctx_sc + loc + react + contra)


def _evidence_threshold(p58_state: int, total: int) -> bool:
    if p58_state == 1:
        return total >= DEFAULT_CFG.take_threshold
    if p58_state == -1:
        return total >= DEFAULT_CFG.take_threshold
    return False


def main() -> int:
    m1, m5, m15 = load_markets_lw()
    report = {
        "part": "B_warmup_diagnosis",
        "method": "prefix_vs_full at signal bars (Python mirror — NOT TV Pine export)",
        "take_threshold": DEFAULT_CFG.take_threshold,
        "windows": [],
        "findings": [],
    }

    for wid, start, end in WINDOWS:
        s_i, e_i = window_indices(m1, start, end)
        mid = s_i + (e_i - s_i) // 2
        prefix_start = mid

        _, ev_full, _, _ = run_mirror(m1, m5, m15, s_i, e_i)
        _, ev_prefix, _, _ = run_mirror(m1, m5, m15, prefix_start, e_i)
        df_full = events_to_dataframe(ev_full)
        df_prefix = events_to_dataframe(ev_prefix)

        m1w, m5w, m15w = _slice_markets(m1, m5, m15, s_i)
        m1p, m5p, m15p = _slice_markets(m1, m5, m15, prefix_start)
        full_series = build_pine_series(m1w, m5w, m15w)
        prefix_series = build_pine_series(m1p, m5p, m15p)
        full_feat = precompute_features(full_series, 0, len(m1w))
        prefix_feat = precompute_features(prefix_series, 0, len(m1p))

        sig_bars = df_full.loc[df_full["signal_long"] | df_full["signal_short"], "bar_index"].astype(int).tolist()

        signal_mismatches = []
        evidence_mismatches = []
        nan_feature_bars = []

        for bi in sig_bars:
            if bi < prefix_start:
                continue
            full_i = bi - s_i
            local_i = bi - prefix_start
            if full_i < 0 or local_i < 0 or full_i >= len(m1w) or local_i >= len(m1p):
                continue

            full_row = df_full.loc[df_full["bar_index"] == bi].iloc[0]
            pref_rows = df_prefix.loc[df_prefix["bar_index"] == bi]
            pref_row = pref_rows.iloc[0] if len(pref_rows) else None

            sig_diff = {}
            for col in ("signal_long", "signal_short", "enter_long", "enter_short"):
                fv = bool(full_row[col])
                pv = bool(pref_row[col]) if pref_row is not None else False
                if fv != pv:
                    sig_diff[col] = {"full": fv, "prefix": pv}
            if sig_diff:
                signal_mismatches.append(
                    {"bar_index": bi, "timestamp": str(m1.index[bi]), "diffs": sig_diff}
                )

            feat_nan = {}
            for col in FEATURE_COLS:
                if col == "ctx_dir":
                    continue
                fv = getattr(full_feat, col)[full_i]
                pv = getattr(prefix_feat, col)[local_i]
                if np.isfinite(fv) and not np.isfinite(pv):
                    feat_nan.append(col)
            if feat_nan:
                nan_feature_bars.append(
                    {"bar_index": bi, "timestamp": str(m1.index[bi]), "prefix_nan_features": feat_nan}
                )

            dir_str = "LONG" if full_row["signal_long"] else "SHORT" if full_row["signal_short"] else ""
            if dir_str:
                tot_full = _arm_total(full_feat, full_i, dir_str)
                tot_pref = _arm_total(prefix_feat, local_i, dir_str)
                ev_full = _evidence_threshold(int(full_row["p58_state"]), tot_full)
                ev_pref = _evidence_threshold(
                    int(pref_row["p58_state"]) if pref_row is not None else 0, tot_pref
                )
                if ev_full != ev_pref or tot_full != tot_pref:
                    evidence_mismatches.append(
                        {
                            "bar_index": bi,
                            "timestamp": str(m1.index[bi]),
                            "direction": dir_str,
                            "total_full": tot_full,
                            "total_prefix": tot_pref,
                            "evidence_threshold_full": ev_full,
                            "evidence_threshold_prefix": ev_pref,
                        }
                    )

        win = {
            "id": wid,
            "full_start_i": s_i,
            "prefix_start_i": prefix_start,
            "end_i": e_i,
            "prefix_warmup_bars": prefix_start - s_i,
            "signal_bars_in_overlap": len([b for b in sig_bars if b >= prefix_start]),
            "signal_output_mismatches": len(signal_mismatches),
            "evidence_threshold_mismatches": len(evidence_mismatches),
            "prefix_nan_feature_bars": len(nan_feature_bars),
            "signal_mismatch_samples": signal_mismatches[:10],
            "evidence_mismatch_samples": evidence_mismatches[:10],
            "nan_feature_samples": nan_feature_bars[:10],
        }
        report["windows"].append(win)

    # Pine snapshot semantics (static analysis — documents Part C input)
    report["pine_snapshot_semantics"] = {
        "gldSnapArmTotalLong_init": "var float 0.0 — NOT na; pre-first-assignment exports read 0",
        "gldSnapArmTotalShort_init": "var float 0.0 — NOT na; pre-first-assignment exports read 0",
        "update_scope": "Only inside ARMED path when total computed (L1181-1184)",
        "hold_behavior": "Persists last assigned value on WATCH/COOLDOWN/flat bars",
        "layer_d_evidence_threshold": "p58State==1/-1 AND snap>=takeThreshold — stale snap can read true/false incorrectly when state and snap disagree",
        "warmup_risk": "Insufficient chart history → HTF/pivot features NaN → Layer A signals may differ; snap totals may reflect prefix-warm feature inputs",
    }

    report["findings"] = [
        "Prefix chart load (mid-session start) can change signal_long/short/enter_* at overlap bars when HTF/pivot series are NaN under truncated history.",
        "gldSnapArmTotal* uses var float init 0.0 — export never emits na today; 'unknown' reads as 0 until first ARMED assignment.",
        "On non-ARMED bars, snap holds prior total — GLD_evidence_threshold_* can disagree with recomputed Layer B total even with full warmup.",
        "Part C must define explicit export encoding for unset/stale/warmup-invalid totals (na vs hold vs 0) once TV export sample confirms Pine plot behavior.",
        "Part D ledger must treat evidence_threshold export na/0/hold distinctly — do not coerce to False silently.",
    ]

    report["note"] = (
        "SUPPLEMENTARY ONLY — prefix-truncation proxy. "
        "Part B closure requires PART_B_WARMUP_VERDICT.md checks 1–3 (declarations, live reload, shadow logs)."
    )
    report["five_vs_one_source"] = "synthetic_prefix_truncation_not_shadow_log"
    report["hold_on_real_export"] = "ACTIVE until Part C + Part D complete"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    summary = {w["id"]: {"sig_mm": w["signal_output_mismatches"], "ev_mm": w["evidence_threshold_mismatches"]} for w in report["windows"]}
    print(json.dumps(summary, indent=2))
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
