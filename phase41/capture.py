"""Overlay existing frozen systems on major reversal opportunities."""

from __future__ import annotations

import pandas as pd

from .config import CAPTURE_AFTER_BARS, CAPTURE_BEFORE_BARS, P37_SIGNAL_MAP, P40_SIGNAL_MAP


def _load_signals(path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    s = pd.read_csv(path)
    ts_col = "marker_bar_timestamp" if "marker_bar_timestamp" in s.columns else "timestamp"
    s["marker_bar_timestamp"] = pd.to_datetime(s[ts_col], utc=True)
    return s


def classify_capture(opportunities: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    p37 = _load_signals(P37_SIGNAL_MAP)
    p40 = _load_signals(P40_SIGNAL_MAP)

    rev_p37 = p37.loc[p37["signal_type"].isin(["RL", "RS"])].copy() if not p37.empty else pd.DataFrame()
    rev_p40 = p40.loc[p40["signal_type"].isin(["RL", "RS"])].copy() if not p40.empty else pd.DataFrame()
    cont = p37.loc[p37["signal_type"].isin(["L", "S"])].copy() if not p37.empty else pd.DataFrame()

    rows = []
    for opp in opportunities.itertuples(index=False):
        ts = pd.Timestamp(opp.extreme_timestamp)
        want = "RL" if opp.direction == "Long" else "RS"
        want_cont = "L" if opp.direction == "Long" else "S"
        win_start = ts - pd.Timedelta(minutes=15 * CAPTURE_BEFORE_BARS)
        win_end = ts + pd.Timedelta(minutes=15 * CAPTURE_AFTER_BARS)

        def _near(df, stype):
            if df.empty:
                return pd.DataFrame()
            sub = df.loc[df["signal_type"] == stype]
            return sub.loc[(sub["marker_bar_timestamp"] >= win_start) & (sub["marker_bar_timestamp"] <= win_end)]

        hit37 = _near(rev_p37, want)
        hit40 = _near(rev_p40, want)
        hit_other = _near(cont, want_cont)
        if not hit37.empty:
            status = "CAPTURED_PHASE33"
            matched = hit37.iloc[0]
        elif not hit40.empty:
            status = "CAPTURED_PHASE40"
            matched = hit40.iloc[0]
        elif not hit_other.empty:
            status = "CAPTURED_OTHER_EXISTING"
            matched = hit_other.iloc[0]
        else:
            status = "MISSED"
            matched = None

        rows.append(
            {
                "event_id": opp.event_id,
                "extreme_timestamp": ts,
                "direction": opp.direction,
                "extreme_price": opp.extreme_price,
                "capture_status": status,
                "matched_signal_time": matched["marker_bar_timestamp"] if matched is not None else pd.NaT,
                "matched_signal_type": matched["signal_type"] if matched is not None else "",
                "MFE_R": opp.MFE_R,
                "MAE_R": opp.MAE_R,
            }
        )

    cap = pd.DataFrame(rows)
    missed = cap.loc[cap["capture_status"] == "MISSED"].merge(
        opportunities, on=["event_id", "extreme_timestamp", "direction", "extreme_price"], how="left"
    )
    return cap, missed


def capture_summary(cap: pd.DataFrame) -> dict:
    n = len(cap)
    if n == 0:
        return {}
    bull = cap.loc[cap["direction"] == "Long"]
    bear = cap.loc[cap["direction"] == "Short"]
    return {
        "total": n,
        "bullish": len(bull),
        "bearish": len(bear),
        "pct_phase33": float((cap["capture_status"] == "CAPTURED_PHASE33").mean()),
        "pct_phase40": float((cap["capture_status"].isin(["CAPTURED_PHASE33", "CAPTURED_PHASE40"])).mean()),
        "pct_missed": float((cap["capture_status"] == "MISSED").mean()),
        "bull_missed_pct": float((bull["capture_status"] == "MISSED").mean()) if len(bull) else 0.0,
        "bear_missed_pct": float((bear["capture_status"] == "MISSED").mean()) if len(bear) else 0.0,
    }
