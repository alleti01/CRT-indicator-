"""Walk-forward selection for S52 — TRAIN-only configuration."""

from __future__ import annotations

import pandas as pd

from phase52.config import CONTEXTS, MIN_TEST_TRADES, MIN_TRAIN_TRADES, WALK_FORWARD_FOLDS
from phase52.research.metrics import summarize_trades


def _slice_ts(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    ts = pd.to_datetime(df["entry_timestamp"])
    tz = ts.dt.tz
    lo = pd.Timestamp(start, tz=tz)
    hi = pd.Timestamp(end, tz=tz)
    return df.loc[(ts >= lo) & (ts <= hi)].copy()


def pick_best_config(train: pd.DataFrame) -> tuple[str, str, bool]:
    best = ("A1", "C0", False)
    best_avgr = -999.0
    for family in train["family"].unique():
        for ctx in train["context"].unique() if "context" in train.columns else ["C0"]:
            for rth in (False, True):
                sub = train.loc[
                    (train["family"] == family)
                    & (train.get("context", "C0") == ctx)
                    & (train.get("rth_only", False) == rth)
                ]
                if len(sub) < MIN_TRAIN_TRADES:
                    continue
                avgr = float(sub["net_R"].mean())
                if avgr > best_avgr:
                    best_avgr = avgr
                    best = (family, ctx, rth)
    return best


def walk_forward_s52(all_trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """all_trades must include family, context, rth_only, net_R, entry_timestamp."""
    oos_parts: list[pd.DataFrame] = []
    selections: list[dict] = []
    for fold_i, (tr_s, tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, 1):
        train = _slice_ts(all_trades, tr_s, tr_e)
        test = _slice_ts(all_trades, te_s, te_e)
        if train.empty or test.empty:
            continue
        fam, ctx, rth = pick_best_config(train)
        te = test.loc[
            (test["family"] == fam)
            & (test.get("context", "C0") == ctx)
            & (test.get("rth_only", False) == rth)
        ].copy()
        if len(te) < MIN_TEST_TRADES and not te.empty:
            pass  # still include sparse folds
        te["fold"] = fold_i
        te["selected_family"] = fam
        te["selected_context"] = ctx
        te["selected_rth"] = rth
        oos_parts.append(te)
        selections.append(
            {
                "fold": fold_i,
                "train_start": tr_s,
                "train_end": tr_e,
                "test_start": te_s,
                "test_end": te_e,
                "family": fam,
                "context": ctx,
                "rth_only": rth,
                "train_N": len(
                    train.loc[
                        (train["family"] == fam)
                        & (train.get("context", "C0") == ctx)
                        & (train.get("rth_only", False) == rth)
                    ]
                ),
                "train_AvgR": float(
                    train.loc[
                        (train["family"] == fam)
                        & (train.get("context", "C0") == ctx)
                        & (train.get("rth_only", False) == rth),
                        "net_R",
                    ].mean()
                ),
            }
        )
    stitched = pd.concat(oos_parts, ignore_index=True) if oos_parts else pd.DataFrame()
    sel_df = pd.DataFrame(selections)
    return stitched, sel_df
