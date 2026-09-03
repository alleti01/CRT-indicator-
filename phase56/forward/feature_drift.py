"""Feature / score distribution drift vs historical pre-holdout reference."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase56.config import LOGS, P54_SCORED_CACHE, RESULTS


def _psi(ref: pd.Series, cur: pd.Series, bins: int = 10) -> float:
    ref = ref.dropna().astype(float)
    cur = cur.dropna().astype(float)
    if len(ref) < 100 or len(cur) < 20:
        return np.nan
    edges = np.quantile(ref, np.linspace(0, 1, bins + 1))
    edges = np.unique(edges)
    if len(edges) < 3:
        return np.nan
    r = np.histogram(ref, bins=edges)[0] / len(ref)
    c = np.histogram(cur, bins=edges)[0] / len(cur)
    r = np.clip(r, 1e-6, 1)
    c = np.clip(c, 1e-6, 1)
    return float(np.sum((c - r) * np.log(c / r)))


def compute_feature_drift() -> pd.DataFrame:
    from phase54.research.parity import add_population_flags

    ref = pd.read_parquet(P54_SCORED_CACHE)
    ref = add_population_flags(ref)
    ref_d10 = ref.loc[ref["top10"]].copy()
    ev = pd.read_csv(LOGS / "s54_forward_events.csv")
    fwd_d10 = ev.loc[ev["D10_pass"].astype(str).str.lower().eq("true")] if not ev.empty else ev
    rows = []
    # Score distribution (primary forward observable)
    ref_score = ref_d10["score"].astype(float)
    fwd_score = fwd_d10["quality_score"].astype(float) if not fwd_d10.empty else pd.Series(dtype=float)
    rows.append(
        {
            "field": "quality_score",
            "ref_mean": float(ref_score.mean()),
            "ref_std": float(ref_score.std()),
            "ref_median": float(ref_score.median()),
            "forward_n": len(fwd_score),
            "forward_mean": float(fwd_score.mean()) if len(fwd_score) else np.nan,
            "forward_std": float(fwd_score.std()) if len(fwd_score) else np.nan,
            "forward_median": float(fwd_score.median()) if len(fwd_score) else np.nan,
            "PSI": _psi(ref_score, fwd_score),
            "flag": "OK",
        }
    )
    # Frozen model input features — reference only (forward events log score, not full feature vector)
    for f in [
        "m15_body_atr", "countertrend_15m", "mtf_1m_5m_align", "mtf_1m_15m_align",
        "atr", "atr_ratio", "m5_range_pos_8", "m5_range_pos_4", "m15_range_pos_4",
        "m15_range_pos_8", "m5_mom", "m15_mom_4",
    ]:
        if f not in ref_d10.columns:
            continue
        ref_s = ref_d10[f].astype(float)
        rows.append(
            {
                "field": f,
                "ref_mean": float(ref_s.mean()),
                "ref_std": float(ref_s.std()),
                "ref_median": float(ref_s.median()),
                "forward_n": 0,
                "forward_mean": np.nan,
                "forward_std": np.nan,
                "forward_median": np.nan,
                "PSI": np.nan,
                "flag": "REFERENCE_ONLY",
            }
        )
    out = pd.DataFrame(rows)
    RESULTS.mkdir(parents=True, exist_ok=True)
    out.to_csv(RESULTS / "feature_drift.csv", index=False)
    return out
