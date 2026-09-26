"""CDX V3 Pro discovery run: labels, match, features, causality. No P&L fit."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from cdx_research.python.causality import run_causality
from cdx_research.python.features import add_causal_features
from cdx_research.python.match import context_windows, load_labels, match_labels
from cdx_research.python.rules import apply_candidate_v1
from phase58j.research.lw_data import load_market_1m_lw

ROOT = Path(__file__).resolve().parents[1]


def main() -> dict:
    labels = load_labels()
    labels.to_csv(ROOT / "labels" / "signal_labels.csv", index=False)
    m1 = load_market_1m_lw()
    matched = match_labels(labels, m1)
    matched.to_csv(ROOT / "cdx_signal_bars.csv", index=False)
    ctx = context_windows(matched, m1)
    if not ctx.empty:
        ctx.to_csv(ROOT / "labels" / "signal_context_windows.csv", index=False)

    # Feature library smoke on last available 5 calendar days — NOT CDX-labeled.
    end = m1.index.max()
    start = end - pd.Timedelta(days=5)
    window = m1.loc[start:end]
    feat = add_causal_features(window)
    feat["cdx_target"] = 0
    feat["candidate_v1"] = apply_candidate_v1(feat)
    feat_path = ROOT / "features" / "all_bar_features.parquet"
    try:
        feat.to_parquet(feat_path)
    except Exception:
        feat.to_csv(ROOT / "features" / "all_bar_features.csv")

    causality = run_causality(window, sample_n=500)
    (ROOT / "reports" / "causality_raw.json").write_text(json.dumps(causality, default=str, indent=2))

    n = len(labels)
    high = int((labels["timestamp_confidence"] == "HIGH").sum())
    med = int((labels["timestamp_confidence"] == "MEDIUM").sum())
    low = int((labels["timestamp_confidence"] == "LOW").sum())
    longs = int((labels["direction"] == "LONG").sum())
    shorts = int((labels["direction"] == "SHORT").sum())
    matched_n = int((matched["match_status"] == "MATCHED").sum())
    oos = int((matched["match_status"] == "OUT_OF_RANGE").sum())

    summary = {
        "verdict": "CDX_RE_INSUFFICIENT_INFORMATION" if matched_n == 0 else "CDX_RE_DISCOVERY_READY",
        "screenshots": 12,
        "labels": n,
        "high": high,
        "medium": med,
        "low": low,
        "longs": longs,
        "shorts": shorts,
        "ohlcv_min": str(m1.index.min()),
        "ohlcv_max": str(m1.index.max()),
        "matched_bars": matched_n,
        "out_of_range": oos,
        "feature_rows": int(len(feat)),
        "candidate_v1_fires_in_smoke_window": int((feat["candidate_v1"] != 0).sum()),
        "causality": causality["status"],
        "htf_table_used": False,
    }
    (ROOT / "reports" / "run_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
