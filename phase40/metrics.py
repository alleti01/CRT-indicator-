"""Performance reporting for Phase 40."""

from __future__ import annotations

import pandas as pd

from phase31.metrics import apply_costs, performance

from phase29.config import WALK_FORWARD_FOLDS


def enrich_net(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["net_R"] = apply_costs(
        out.assign(entry_price=out["entry_price"], stop_price=out["stop"], result_R=out["realized_R"])
    )
    return out


def segment_results(df: pd.DataFrame, *, col: str = "net_R") -> pd.DataFrame:
    rows = []
    for st in ("L", "S", "RL", "RS"):
        sub = df.loc[df["signal_type"] == st]
        if not sub.empty:
            rows.append({"segment": st, **performance(sub, col=col)})
    for seg, mask in (
        ("continuation", df["signal_type"].isin(["L", "S"])),
        ("reversal", df["signal_type"].isin(["RL", "RS"])),
        ("ALL", pd.Series(True, index=df.index)),
    ):
        sub = df.loc[mask]
        if not sub.empty:
            rows.append({"segment": seg, **performance(sub, col=col)})
    return pd.DataFrame(rows)


def yearly_results(df: pd.DataFrame, *, col: str = "net_R") -> pd.DataFrame:
    d = df.copy()
    d["year"] = pd.to_datetime(d["marker_bar_timestamp"], utc=True).dt.year
    return d.groupby("year").apply(lambda g: pd.Series(performance(g, col=col)), include_groups=False).reset_index()


def cost_stress(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for mult in (1.0, 1.5, 2.0):
        d = df.copy()
        d["net_R"] = apply_costs(
            d.assign(entry_price=d["entry_price"], stop_price=d["stop"], result_R=d["realized_R"]),
            multiplier=mult,
        )
        rows.append({"cost_multiplier": mult, **performance(d, col="net_R")})
    return pd.DataFrame(rows)


def walk_forward_stitched(df: pd.DataFrame, *, col: str = "net_R") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stitched OOS test folds only."""
    test_parts = []
    for _tr_s, _tr_e, te_s, te_e in WALK_FORWARD_FOLDS:
        tz = df["marker_bar_timestamp"].dt.tz
        part = df.loc[
            (df["marker_bar_timestamp"] >= pd.Timestamp(te_s, tz=tz))
            & (df["marker_bar_timestamp"] <= pd.Timestamp(te_e, tz=tz))
        ]
        if not part.empty:
            test_parts.append(part)
    oos = pd.concat(test_parts, ignore_index=True) if test_parts else pd.DataFrame()
    return oos, segment_results(oos, col=col)
