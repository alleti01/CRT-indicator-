"""Post-entry behavior classification (diagnostic labels only)."""

from __future__ import annotations

import pandas as pd

from .config import (
    CLASS_CLEAN_WIN_MAE_R,
    CLASS_CLEAN_WIN_MFE_R,
    CLASS_DELAYED_MFE_R,
    CLASS_DELAYED_MIN_BARS,
    CLASS_IMMEDIATE_BARS,
    CLASS_IMMEDIATE_MFE_R,
    CLASS_STATIC_EFFICIENCY,
    CLASS_STATIC_MAE_R,
    CLASS_STATIC_MFE_R,
    CLASS_WRONG_MAE_R,
    CLASS_WRONG_MFE_R,
    PRIMARY_MOVEMENT_MFE_R,
)


def classify_behavior(row: pd.Series) -> str:
    mfe = float(row.get("MFE_R", 0))
    mae = float(row.get("MAE_R", 0))
    eff = float(row.get("directional_efficiency", 0))
    move_eff = float(row.get("movement_efficiency", 0))
    b50 = row.get("bars_to_plus_0.50r", float("nan"))
    b50 = float(b50) if pd.notna(b50) else 999.0

    if mfe >= CLASS_CLEAN_WIN_MFE_R and mae <= CLASS_CLEAN_WIN_MAE_R:
        return "CLEAN_WINNER"
    if mfe >= CLASS_IMMEDIATE_MFE_R and b50 <= CLASS_IMMEDIATE_BARS:
        return "IMMEDIATE_EXPANSION"
    if mae >= CLASS_WRONG_MAE_R and mfe <= CLASS_WRONG_MFE_R:
        return "WRONG_DIRECTION"
    if mfe >= CLASS_DELAYED_MFE_R and b50 >= CLASS_DELAYED_MIN_BARS:
        return "DELAYED_EXPANSION"
    if mfe >= 0.75 and mae >= 0.75 and move_eff < 0.45:
        return "WHIPSAW"
    if mfe < CLASS_STATIC_MFE_R and mae < CLASS_STATIC_MAE_R and eff < CLASS_STATIC_EFFICIENCY:
        return "STATIC_CHOP"
    if mfe < CLASS_STATIC_MFE_R and mae < CLASS_STATIC_MAE_R:
        return "STATIC_CHOP"
    if mfe >= PRIMARY_MOVEMENT_MFE_R:
        return "DELAYED_EXPANSION"
    if mae > mfe:
        return "WRONG_DIRECTION"
    return "STATIC_CHOP"


def classify_dataframe(paths: pd.DataFrame) -> pd.DataFrame:
    out = paths.copy()
    out["behavior_class"] = out.apply(classify_behavior, axis=1)
    out["meaningful_expansion"] = out["MFE_R"] >= PRIMARY_MOVEMENT_MFE_R
    return out


def sensitivity_table(paths: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for static_mfe in (0.35, 0.50, 0.65):
        for static_mae in (0.50, 0.75, 1.00):
            static = (
                (paths["MFE_R"] < static_mfe)
                & (paths["MAE_R"] < static_mae)
            ).mean()
            expansion = (paths["MFE_R"] >= 1.0).mean()
            rows.append({"static_mfe_max": static_mfe, "static_mae_max": static_mae, "static_rate": static, "expansion_1r_rate": expansion})
    return pd.DataFrame(rows)
