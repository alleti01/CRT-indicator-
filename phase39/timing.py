"""Entry timing, signal age, time-to-move, and wrong-direction diagnostics."""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from .paths import max_hold_bars, target_r


def _dir_code(direction: str) -> int:
    return 1 if str(direction).lower() == "long" else -1


def entry_timing_comparison(signals: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    pos = {ts: i for i, ts in enumerate(market.index)}
    rows = []
    for sig in signals.itertuples(index=False):
        ts = pd.Timestamp(sig.marker_bar_timestamp)
        if ts not in pos:
            continue
        i = pos[ts]
        d = _dir_code(sig.direction)
        entry = float(sig.entry_price)
        stop = float(sig.stop)
        risk = abs(entry - stop) or 1e-9
        st = str(sig.signal_type)
        mh = max_hold_bars(st)
        tgt = target_r(st)

        alts = {
            "CURRENT": (i, entry, True),
            "NEXT_OPEN": (i + 1, float(market.iloc[i + 1].open) if i + 1 < len(market) else np.nan, i + 1 < len(market)),
            "NEXT_CLOSE": (i + 1, float(market.iloc[i + 1].close) if i + 1 < len(market) else np.nan, i + 1 < len(market)),
        }
        # Earlier bar only if same bar is not first bar after displacement — conservative: NOT AVAILABLE unless i>0 and prior bar had retest touch
        alts["ONE_BAR_EARLIER"] = (i - 1, float(market.iloc[i - 1].close) if i > 0 else np.nan, False)

        for label, (ei, px, causal) in alts.items():
            if not causal or ei < 0 or ei >= len(market) or not np.isfinite(px):
                mfe = mae = realized = np.nan
                causal_ok = False
            else:
                causal_ok = True
                mfe = mae = 0.0
                realized = 0.0
                for elapsed, j in enumerate(range(ei + 1, min(len(market), ei + mh + 1)), start=1):
                    bar = market.iloc[j]
                    hi, lo, cl = float(bar.high), float(bar.low), float(bar.close)
                    if d == 1:
                        bar_mfe = (hi - px) / risk
                        bar_mae = (px - lo) / risk
                        hit_stop = lo <= stop
                        hit_tgt = hi >= px + tgt * risk
                    else:
                        bar_mfe = (px - lo) / risk
                        bar_mae = (hi - px) / risk
                        hit_stop = hi >= stop
                        hit_tgt = lo <= px - tgt * risk
                    mfe = max(mfe, bar_mfe)
                    mae = max(mae, bar_mae)
                    if hit_stop:
                        realized = -1.0
                        break
                    if hit_tgt:
                        realized = tgt
                        break
                    if elapsed >= mh:
                        realized = (cl - px) / risk * d
                        break
            rows.append(
                {
                    "signal_id": sig.signal_id,
                    "timestamp_ct": ts,
                    "signal_type": st,
                    "timing_variant": label,
                    "causally_available": causal_ok,
                    "entry_price": px,
                    "MFE_R": mfe,
                    "MAE_R": mae,
                    "realized_R": realized,
                }
            )
    return pd.DataFrame(rows)


def timing_error_labels(paths: pd.DataFrame) -> pd.DataFrame:
    """Post-hoc optimal timing vs actual (diagnostic)."""
    out = paths.copy()
    b50 = out["bars_to_plus_0.50r"].fillna(999)
    out["timing_error"] = np.select(
        [b50 <= 0, b50 == 1, b50 == 2, b50 == 3, b50 >= 4],
        ["OPTIMAL", "OPTIMAL", "1_BAR_LATE", "2_BARS_LATE", "3+_BARS_LATE"],
        default="OPTIMAL",
    )
    out["entered_after_impulse"] = out["pre_entry_move_3_atr"] > 1.0 if "pre_entry_move_3_atr" in out.columns else False
    return out


def signal_age_analysis(signals: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    pos = {ts: i for i, ts in enumerate(market.index)}
    rows = []
    for sig in signals.itertuples(index=False):
        ts = pd.Timestamp(sig.marker_bar_timestamp)
        if ts not in pos:
            continue
        i = pos[ts]
        d = _dir_code(sig.direction)
        atr = float(market.iloc[i].atr)
        entry = float(sig.entry_price)
        move_disp = np.nan
        if hasattr(sig, "source_displacement_time") and pd.notna(sig.source_displacement_time):
            dts = pd.Timestamp(sig.source_displacement_time)
            if dts in pos:
                disp_i = pos[dts]
                move_disp = (entry - float(market.iloc[disp_i].close)) * d / atr if atr > 0 else np.nan
        move_bos = np.nan
        if hasattr(sig, "bos_or_reclaim_time") and pd.notna(sig.bos_or_reclaim_time):
            bts = pd.Timestamp(sig.bos_or_reclaim_time)
            if bts in pos:
                bos_i = pos[bts]
                lvl = float(getattr(sig, "bos_level", getattr(sig, "reclaim_level", entry)))
                move_bos = (entry - lvl) * d / atr if atr > 0 else np.nan
        rows.append(
            {
                "signal_id": sig.signal_id,
                "signal_type": sig.signal_type,
                "timestamp_ct": ts,
                "move_since_displacement_atr": move_disp,
                "move_since_bos_reclaim_atr": move_bos,
                "pre_entry_move_5_atr": (float(market.iloc[i].close) - float(market.iloc[max(0, i - 5)].close)) * d / atr if atr > 0 else np.nan,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    bins = [0, 0.5, 1.0, 1.5, 2.0, np.inf]
    labels = ["0-0.5", "0.5-1.0", "1.0-1.5", "1.5-2.0", "2+"]
    df["exhaustion_bucket"] = pd.cut(df["move_since_displacement_atr"].fillna(0), bins=bins, labels=labels)
    return df


def time_to_move_stats(paths: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for st, grp in paths.groupby("signal_type"):
        n = len(grp)
        rows.append(
            {
                "signal_type": st,
                "N": n,
                "P_plus_0.25R_1bar": float((grp["bars_to_plus_0.25r"] <= 1).mean()),
                "P_plus_0.50R_1bar": float((grp["bars_to_plus_0.50r"] <= 1).mean()),
                "P_plus_0.50R_2bars": float((grp["bars_to_plus_0.50r"] <= 2).mean()),
                "P_plus_1R_2bars": float((grp["bars_to_plus_1.00r"] <= 2).mean()),
                "P_plus_0.50R_3bars": float((grp["bars_to_plus_0.50r"] <= 3).mean()),
                "P_plus_1R_3bars": float((grp["bars_to_plus_1.00r"] <= 3).mean()),
                "median_bars_to_0.5R": float(grp["bars_to_plus_0.50r"].median(skipna=True)),
                "median_bars_to_1R": float(grp["bars_to_plus_1.00r"].median(skipna=True)),
            }
        )
    return pd.DataFrame(rows)
