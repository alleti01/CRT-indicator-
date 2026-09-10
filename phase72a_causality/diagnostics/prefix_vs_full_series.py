#!/usr/bin/env python3
"""Compare prefix-walk vs full-load feature values at signal bars (replay proxy).

NOT TradingView bar replay — simulates live-by-truncating history start and
checking whether suspect series values at bar_index i differ from full history.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase52.research.swings import precompute_swing_highs, precompute_swing_lows
from phase58j.research.lw_data import load_markets_lw
from phase72b.python.autonomous_mirror_engine import run_mirror
from phase72b.python.event_log import events_to_dataframe
from phase72b.python.pine_features import precompute_features
from phase72b.python.series_builder import build_pine_series
from phase72b.tools.run_phase72b_parity import window_indices

OUT = ROOT / "phase72a_causality" / "reports" / "PREFIX_VS_FULL_SERIES.json"

CANDIDATES = [
    "last_sh",
    "last_sl",
    "sh_at_i",
    "sh_at_i10",
    "sl_at_i",
    "sl_at_i10",
    "m5_last_sh",
    "m5_last_sl",
    "m15_h4",
    "m15_l4",
    "m15_c12",
    "m5_h",
    "m15_h",
]

FEATURE_COLS = [
    "ctx_dir",
    "bull_sc",
    "bear_sc",
    "loc_long",
    "loc_short",
    "react_long",
    "react_short",
    "ev_total_long",
    "ev_total_short",
]


def _slice_markets(m1, m5, m15, start_i: int):
    m1s = m1.iloc[start_i:].copy()
    # Reindex 5m/15m to cover sliced 1m range
    t0, t1 = m1s.index[0], m1s.index[-1]
    m5s = m5.loc[(m5.index >= t0.floor("5min")) & (m5.index <= t1)].copy()
    m15s = m15.loc[(m15.index >= t0.floor("15min")) & (m15.index <= t1)].copy()
    return m1s, m5s, m15s


def _series_dict(s, i: int) -> dict:
    return {
        "last_sh": float(s.sh_at_i[i]) if hasattr(s, "sh_at_i") else np.nan,
        "last_sl": float(s.sl_at_i[i]) if hasattr(s, "sl_at_i") else np.nan,
        "sh_at_i": float(s.sh_at_i[i]),
        "sh_at_i10": float(s.sh_at_i10[i]),
        "sl_at_i": float(s.sl_at_i[i]),
        "sl_at_i10": float(s.sl_at_i10[i]),
        "m5_last_sh": float(s.m5_last_sh[i]),
        "m5_last_sl": float(s.m5_last_sl[i]),
        "m15_h4": float(s.m15_h4[i]),
        "m15_l4": float(s.m15_l4[i]),
        "m15_c12": float(s.m15_c12[i]),
        "m5_h": float(s.m5_h[i]),
        "m15_h": float(s.m15_h[i]),
    }


def _pivot_confirm_audit(hi: np.ndarray, swing: int = 5) -> list[dict]:
    """For each pivot confirmation, record first-appear bar vs swing-center bar."""
    out = []
    last = np.nan
    for i in range(len(hi)):
        j = i - swing
        if j >= swing:
            window = hi[j - swing : j + swing + 1]
            if hi[j] == np.max(window) and (not np.isfinite(last) or hi[j] != last):
                out.append(
                    {
                        "confirm_bar_index": i,
                        "swing_center_bar_index": j,
                        "lag_bars": swing,
                        "price": float(hi[j]),
                        "would_backdate_by_bars": swing,
                    }
                )
                last = hi[j]
        if len(out) >= 12:
            break
    return out


def main() -> int:
    m1, m5, m15 = load_markets_lw()
    windows = [
        ("aug28_session", "2026-08-28 08:30", "2026-08-28 16:00"),
        ("aug30_chi_evening", "2026-08-30 17:00", "2026-08-30 22:30"),
    ]

    report = {
        "method": "prefix_vs_full_series (Python mirror — NOT TradingView bar replay UI)",
        "tv_bar_replay_run": False,
        "windows": [],
        "pivot_confirm_samples": _pivot_confirm_audit(m1["high"].values.astype(float)),
    }

    for wid, start, end in windows:
        s_i, e_i = window_indices(m1, start, end)
        mid = s_i + (e_i - s_i) // 2
        prefix_start = mid

        _, ev_full, _, _ = run_mirror(m1, m5, m15, s_i, e_i)
        df_full = events_to_dataframe(ev_full)
        sig_bars = df_full.loc[df_full["signal_long"] | df_full["signal_short"], "bar_index"].astype(int).tolist()

        m1w, m5w, m15w = _slice_markets(m1, m5, m15, s_i)
        m1p, m5p, m15p = _slice_markets(m1, m5, m15, prefix_start)
        full_series = build_pine_series(m1w, m5w, m15w)
        prefix_series = build_pine_series(m1p, m5p, m15p)
        full_feat = precompute_features(full_series, 0, len(m1w))
        prefix_feat = precompute_features(prefix_series, 0, len(m1p))

        comparisons = []
        for bi in sig_bars:
            if bi < prefix_start:
                continue
            local_i = bi - prefix_start
            full_i = bi - s_i
            if local_i < 0 or local_i >= len(m1p) or full_i < 0 or full_i >= len(m1w):
                continue
            full_vals = _series_dict(full_series, full_i)
            pref_vals = _series_dict(prefix_series, local_i)
            diffs = {}
            for k in CANDIDATES:
                fv, pv = full_vals[k], pref_vals[k]
                if not (np.isfinite(fv) and np.isfinite(pv)):
                    diffs[k] = {"full": fv, "prefix": pv, "match": (not np.isfinite(fv) and not np.isfinite(pv))}
                else:
                    diffs[k] = {"full": fv, "prefix": pv, "match": abs(fv - pv) < 1e-9}
            feat_diffs = {}
            for col in FEATURE_COLS:
                arr = getattr(full_feat, col)
                arr_p = getattr(prefix_feat, col)
                if col == "ctx_dir":
                    feat_diffs[col] = {"full": str(arr[full_i]), "prefix": str(arr_p[local_i]), "match": arr[full_i] == arr_p[local_i]}
                else:
                    feat_diffs[col] = {
                        "full": int(arr[full_i]),
                        "prefix": int(arr_p[local_i]),
                        "match": int(arr[full_i]) == int(arr_p[local_i]),
                    }
            comparisons.append(
                {
                    "bar_index": bi,
                    "timestamp": str(m1.index[bi]),
                    "series_match_all": all(d["match"] for d in diffs.values()),
                    "feature_match_all": all(d["match"] for d in feat_diffs.values()),
                    "series_diffs": {k: v for k, v in diffs.items() if not v["match"]},
                    "feature_diffs": {k: v for k, v in feat_diffs.items() if not v["match"]},
                }
            )

        report["windows"].append(
            {
                "id": wid,
                "full_start_i": s_i,
                "prefix_start_i": prefix_start,
                "end_i": e_i,
                "signal_bars_checked": len(comparisons),
                "series_mismatch_bars": sum(1 for c in comparisons if not c["series_match_all"]),
                "feature_mismatch_bars": sum(1 for c in comparisons if not c["feature_match_all"]),
                "comparisons": comparisons,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({w["id"]: {"checked": w["signal_bars_checked"], "series_mm": w["series_mismatch_bars"], "feat_mm": w["feature_mismatch_bars"]} for w in report["windows"]}, indent=2))
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
