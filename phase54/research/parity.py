"""Phase53 score parity and frozen score assignment."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase53.research.features import feature_columns
from phase53.research.metrics import pf, summarize_r
from phase53.research.models import walk_forward_models
from phase54.config import P53_REF, PARITY_TOL_AVGR, PARITY_TOL_D10_N, PARITY_TOL_EVENTS, PHASE53_SCORE_DECILES


def load_events() -> pd.DataFrame:
    from phase54.config import PHASE53_PARQUET

    return pd.read_parquet(PHASE53_PARQUET)


def assign_scores(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Frozen Phase53 walk-forward logistic scoring."""
    feats = feature_columns(df)
    stitched, sel_df, _ = walk_forward_models(df, feats, target="opp_O2", max_features=8)
    return stitched, sel_df


def add_population_flags(scored: pd.DataFrame) -> pd.DataFrame:
    out = scored.copy()
    out["decile"] = pd.qcut(out["score"], 10, labels=False, duplicates="drop") + 1
    out["top10"] = out["decile"] == 10
    out["top20"] = out["score"] >= scored["score"].quantile(0.8)
    return out


def parity_report(all_events: pd.DataFrame, scored: pd.DataFrame) -> dict:
    d10 = scored.loc[scored["decile"] == 10] if "decile" in scored.columns else pd.DataFrame()
    if "decile" not in scored.columns and not scored.empty:
        scored = add_population_flags(scored)
        d10 = scored.loc[scored["decile"] == 10]
    checks = {}
    checks["total_events"] = {
        "actual": len(all_events),
        "expected": P53_REF["total_events"],
        "pass": abs(len(all_events) - P53_REF["total_events"]) / P53_REF["total_events"] <= PARITY_TOL_EVENTS,
    }
    checks["scored_oos_n"] = {
        "actual": len(scored),
        "expected": P53_REF["scored_oos_n"],
        "pass": abs(len(scored) - P53_REF["scored_oos_n"]) / P53_REF["scored_oos_n"] <= PARITY_TOL_D10_N,
    }
    if not d10.empty:
        avgr = float(d10["net_R"].mean())
        unauth = d10.loc[d10["core_authorized"] == 0]
        checks["d10_avgr"] = {
            "actual": avgr,
            "expected": P53_REF["d10_avgr"],
            "pass": abs(avgr - P53_REF["d10_avgr"]) <= PARITY_TOL_AVGR,
        }
        checks["d10_n"] = {
            "actual": len(d10),
            "expected": P53_REF["d10_n"],
            "pass": abs(len(d10) - P53_REF["d10_n"]) / P53_REF["d10_n"] <= PARITY_TOL_D10_N,
        }
        checks["d10_unauth_avgr"] = {
            "actual": float(unauth["net_R"].mean()) if len(unauth) else np.nan,
            "expected": P53_REF["d10_unauth_avgr"],
            "pass": abs(float(unauth["net_R"].mean()) - P53_REF["d10_unauth_avgr"]) <= PARITY_TOL_AVGR if len(unauth) else False,
        }
    all_pass = all(v["pass"] for v in checks.values())
    return {"checks": checks, "all_pass": all_pass}
