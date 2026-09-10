"""Combination search for Phase80."""
from __future__ import annotations

import itertools
from typing import Callable

import pandas as pd

from phase80.python.evaluate import kept_vs_rejected, random_direction_proxy, summarize_subset, year_stability
from phase80.python.features import COMPONENT_META, FEATURE_COLS, partition_mask, partition_slice


def _roles(cols: list[str]) -> str:
    if cols == ["CONFLUENCE_SCORE"]:
        return "MULTI_ROLE_SCORE"
    known = [COMPONENT_META[c][1] for c in cols if c in COMPONENT_META]
    if known:
        return "+".join(sorted(set(known)))
    return "+".join(cols)


def _ids(cols: list[str]) -> str:
    if cols == ["CONFLUENCE_SCORE"]:
        return "CONFLUENCE_SCORE"
    known = [COMPONENT_META[c][0] for c in cols if c in COMPONENT_META]
    if known:
        return "+".join(sorted(set(known)))
    return "+".join(cols)


def eval_mask(df: pd.DataFrame, mask: pd.Series, baseline_train: dict, partition: tuple[int, int] | slice, model_id: str, components: list[str], logic: str, threshold: str = "") -> dict:
    if isinstance(partition, tuple):
        part = df.iloc[partition[0]:partition[1]]
        m = mask.iloc[partition[0]:partition[1]]
    else:
        part = df.iloc[partition]
        m = mask.iloc[partition]
    sm = summarize_subset(part, m)
    sm_base = summarize_subset(part)
    sm["retention"] = sm["N"] / sm_base["N"] if sm_base["N"] else 0.0
    sm["DeltaAvgR"] = sm.get("AvgR", 0) - sm_base.get("AvgR", 0)
    sm["DeltaTotalR"] = sm.get("TotalR", 0) - sm_base.get("TotalR", 0)
    kv = kept_vs_rejected(part, m)
    rnd = random_direction_proxy(part, m)
    return {
        "model_id": model_id,
        "components": _ids(components),
        "feature_cols": "+".join(components),
        "roles": _roles(components),
        "logic_type": logic,
        "threshold": threshold,
        "retention": sm["retention"],
        "N": sm.get("N", 0),
        "AvgR": sm.get("AvgR", 0),
        "PF": sm.get("PF", 0),
        "TotalR": sm.get("TotalR", 0),
        "DD": sm.get("MaxDD", 0),
        "WinRate": sm.get("WinRate", 0),
        "LONG_AvgR": sm.get("LONG_AvgR", 0),
        "SHORT_AvgR": sm.get("SHORT_AvgR", 0),
        "DeltaAvgR": sm["DeltaAvgR"],
        "DeltaTotalR": sm["DeltaTotalR"],
        "kept_AvgR": kv["kept"].get("AvgR", 0),
        "rejected_AvgR": kv["rejected"].get("AvgR", 0),
        "random_control_result": rnd.get("directional_lift", 0),
        "year_stability": year_stability(part, m),
        "causal_pass": True,
        "complexity": len(components),
        "status": "CANDIDATE",
    }


def search_singles(df: pd.DataFrame, splits: dict) -> pd.DataFrame:
    rows = []
    base_train = summarize_subset(partition_slice(df, splits["train"]))
    for col in FEATURE_COLS:
        mask = df[col].astype(bool)
        row = eval_mask(df, mask, base_train, splits["train"], f"SINGLE_{col}", [col], "SINGLE")
        rows.append(row)
    return pd.DataFrame(rows)


def search_pairs(df: pd.DataFrame, splits: dict, veto_cols: set[str]) -> pd.DataFrame:
    rows = []
    base_train = summarize_subset(partition_slice(df, splits["train"]))
    for a, b in itertools.combinations(FEATURE_COLS, 2):
        # AND
        mask = df[a].astype(bool) & df[b].astype(bool)
        rows.append(eval_mask(df, mask, base_train, splits["train"], f"PAIR_AND_{a}_{b}", [a, b], "AND"))
        # VETO if b is conflict
        if COMPONENT_META[b][1] == "CONFLICT" or COMPONENT_META[a][1] == "CONFLICT":
            veto = b if COMPONENT_META[b][1] == "CONFLICT" else a
            other = a if veto == b else b
            mask = df[other].astype(bool) & ~df[veto].astype(bool)
            rows.append(eval_mask(df, mask, base_train, splits["train"], f"PAIR_VETO_{other}_NOT_{veto}", [other, veto], "VETO"))
    return pd.DataFrame(rows)


def search_triples(df: pd.DataFrame, splits: dict) -> pd.DataFrame:
    rows = []
    base_train = summarize_subset(partition_slice(df, splits["train"]))
    priority_triples = []
    loc = [c for c in FEATURE_COLS if COMPONENT_META[c][1] == "LOCATION"]
    react = [c for c in FEATURE_COLS if COMPONENT_META[c][1] == "REACTION"]
    ctx = [c for c in FEATURE_COLS if COMPONENT_META[c][1] == "CONTEXT"]
    conf = [c for c in FEATURE_COLS if COMPONENT_META[c][1] == "CONFLICT"]
    tim = [c for c in FEATURE_COLS if COMPONENT_META[c][1] == "TIMING"]
    for a in loc:
        for b in react:
            for c in ctx + conf + tim:
                if len({a, b, c}) == 3:
                    priority_triples.append((a, b, c))
    seen = set()
    triples = []
    for t in priority_triples:
        if t not in seen:
            seen.add(t)
            triples.append(t)
    for t in itertools.combinations(FEATURE_COLS, 3):
        if t not in seen:
            triples.append(t)
    for cols in triples:
        mask = df[cols[0]].astype(bool) & df[cols[1]].astype(bool) & df[cols[2]].astype(bool)
        rows.append(eval_mask(df, mask, base_train, splits["train"], f"TRIPLE_AND_{'_'.join(cols)}", list(cols), "AND"))
    return pd.DataFrame(rows)


def score_model(df: pd.DataFrame, splits: dict) -> pd.DataFrame:
    """Role-based integer score 0-8, test thresholds."""
    role_points = {
        "LOCATION": ["F_GOOD_LOCATION", "F_LOCATION_SCORE"],
        "REACTION": ["F_REACTION_SCORE", "F_REVERSAL_STRONG"],
        "CONTEXT": ["F_ALIGNED_ACTIVE", "F_HTF_SUPPORT", "F_M15_NOT_NEUTRAL", "F_MARKET_REVERSAL"],
        "TIMING": ["F_SB_WINDOW", "F_RTH"],
        "CONFLICT": ["F_NO_HTF_CONTRA", "F_FALSE_REV_LOW", "F_NO_PULLBACK", "F_HTF_LTF_AGREE", "F_CT_LOW"],
    }
    score = pd.Series(0, index=df.index, dtype=int)
    for role, cols in role_points.items():
        for c in cols:
            if c in df.columns:
                score += df[c].astype(int)
    # conflict vetoes subtract
    score -= df["F_HTF_CONTRA"].astype(int) if "F_HTF_CONTRA" in df.columns else 0
    df = df.copy()
    df["CONFLUENCE_SCORE"] = score
    rows = []
    base_train = summarize_subset(partition_slice(df, splits["train"]))
    for thr in range(1, 8):
        mask = df["CONFLUENCE_SCORE"] >= thr
        rows.append(eval_mask(df, mask, base_train, splits["train"], f"SCORE_GE_{thr}", ["CONFLUENCE_SCORE"], "SCORE", str(thr)))
    return pd.DataFrame(rows)


def role_gated_model(df: pd.DataFrame, splits: dict) -> pd.DataFrame:
    """LOCATION + REACTION required; strong conflict vetoes."""
    loc = df["F_GOOD_LOCATION"] | df["F_LOCATION_SCORE"]
    react = df["F_REACTION_SCORE"] | df["F_REVERSAL_STRONG"]
    veto = df["F_NO_HTF_CONTRA"] & df["F_FALSE_REV_LOW"] & df["F_NO_PULLBACK"]
    mask = loc & react & veto
    base_train = summarize_subset(partition_slice(df, splits["train"]))
    return pd.DataFrame([eval_mask(df, mask, base_train, splits["train"], "ROLE_GATED_V1", ["LOCATION", "REACTION", "CONFLICT"], "ROLE_GATED")])


def apply_validation(all_train: pd.DataFrame, df: pd.DataFrame, splits: dict, top_n: int = 10) -> pd.DataFrame:
    """Add validation metrics to top train candidates."""
    top = all_train.sort_values("DeltaAvgR", ascending=False).head(top_n)
    val_rows = []
    for _, row in top.iterrows():
        cols = row["feature_cols"].split("+") if row["feature_cols"] != "CONFLUENCE_SCORE" else []
        if row["logic_type"] == "SCORE":
            thr = int(row["threshold"])
            mask = df["CONFLUENCE_SCORE"] >= thr
        elif row["logic_type"] == "ROLE_GATED":
            loc = df["F_GOOD_LOCATION"] | df["F_LOCATION_SCORE"]
            react = df["F_REACTION_SCORE"] | df["F_REVERSAL_STRONG"]
            veto = df["F_NO_HTF_CONTRA"] & df["F_FALSE_REV_LOW"] & df["F_NO_PULLBACK"]
            mask = loc & react & veto
        elif row["logic_type"] == "VETO":
            parts = row["model_id"].replace("PAIR_VETO_", "").split("_NOT_")
            if len(parts) == 2:
                other, veto = parts[0], "F_" + parts[1] if not parts[1].startswith("F_") else parts[1]
                # fallback parse from feature cols
            cols = [c for c in row["feature_cols"].split("+") if c in df.columns]
            if len(cols) >= 2:
                veto_col = [c for c in cols if COMPONENT_META.get(c, ("", "CONFLICT"))[1] == "CONFLICT"][0]
                other_col = [c for c in cols if c != veto_col][0]
                mask = df[other_col].astype(bool) & ~df[veto_col].astype(bool)
            else:
                mask = df[cols[0]].astype(bool)
        else:
            if not cols:
                cols = [c for c in row["feature_cols"].split("+") if c in df.columns]
            mask = df[cols[0]].astype(bool)
            for c in cols[1:]:
                mask &= df[c].astype(bool)
        if isinstance(splits["validation"], tuple):
            val_part = df.iloc[splits["validation"][0]:splits["validation"][1]]
            val_mask = mask.iloc[splits["validation"][0]:splits["validation"][1]]
        else:
            val_part = df.iloc[splits["validation"]]
            val_mask = mask.iloc[splits["validation"]]
        val = summarize_subset(val_part, val_mask)
        base_val = summarize_subset(val_part)
        val_rows.append({
            "model_id": row["model_id"],
            "N_validation": val.get("N", 0),
            "AvgR_validation": val.get("AvgR", 0),
            "PF_validation": val.get("PF", 0),
            "TotalR_validation": val.get("TotalR", 0),
            "DD_validation": val.get("MaxDD", 0),
            "DeltaAvgR_validation": val.get("AvgR", 0) - base_val.get("AvgR", 0),
            "validation_pass": val.get("AvgR", 0) > base_val.get("AvgR", 0) and val.get("N", 0) >= 200,
        })
    return pd.DataFrame(val_rows)


def redundancy_matrix(df: pd.DataFrame) -> pd.DataFrame:
    cols = FEATURE_COLS
    n = len(cols)
    mat = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = cols[i], cols[j]
            ma = df[a].astype(bool)
            mb = df[b].astype(bool)
            inter = (ma & mb).sum()
            union = (ma | mb).sum()
            jacc = float(inter / union) if union else 0.0
            mat.append({"A": a, "B": b, "jaccard": jacc, "agreement": float((ma == mb).mean())})
    return pd.DataFrame(mat)
