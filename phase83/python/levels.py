"""Causal overnight / prior-RTH level construction. Frozen before 09:30 ET."""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from phase83.python.config import (
    MIN_OVERNIGHT_BARS,
    MIN_PRIOR_RTH_BARS,
    NY_TZ,
    ON_END_HOUR,
    ON_END_MINUTE,
    ON_START_HOUR,
    RESEARCH_END_HOUR,
    RESEARCH_END_MINUTE,
    RTH_CLOSE_HOUR,
    RTH_OPEN_HOUR,
    RTH_OPEN_MINUTE,
    TIME_BUCKETS,
)


@dataclass
class Session:
    date: str
    rth_open_i: int
    research_end_i: int
    on_start_i: int
    on_end_i: int
    on_high: float
    on_low: float
    on_mid: float
    prior_rth_high: float
    prior_rth_low: float
    prior_rth_close: float
    prior_rth_mid: float
    rth_open: float
    atr_open: float
    overnight_bars: int
    prior_rth_bars: int
    gap_atr: float
    on_range_atr: float
    open_vs_prior_high: str
    open_vs_prior_low: str
    open_vs_prior_close: str
    open_inside_prior_range: bool
    open_class: str


def _tod_minutes(ts) -> np.ndarray:
    return ts.hour * 60 + ts.minute


def time_bucket(hour: int, minute: int) -> str:
    hm = hour * 60 + minute
    for name, h0, m0, h1, m1 in TIME_BUCKETS:
        if h0 * 60 + m0 <= hm < h1 * 60 + m1:
            return name
    return "OUTSIDE"


def build_sessions(arr: dict) -> tuple[list[Session], dict]:
    ny = arr["ny"]
    hi, lo, cl, op, atr = arr["hi"], arr["lo"], arr["cl"], arr["op"], arr["atr"]
    n = arr["n"]
    dates = pd.DatetimeIndex(ny).normalize()
    unique_days = pd.Index(dates).unique().sort_values()

    # Map date -> indices
    day_groups: dict[pd.Timestamp, np.ndarray] = {}
    for d in unique_days:
        day_groups[d] = np.flatnonzero(dates == d)

    sessions: list[Session] = []
    skipped = {"no_rth_open": 0, "thin_overnight": 0, "no_prior_rth": 0, "bad_atr": 0}

    rth_open_min = RTH_OPEN_HOUR * 60 + RTH_OPEN_MINUTE
    rth_close_min = RTH_CLOSE_HOUR * 60
    research_end_min = RESEARCH_END_HOUR * 60 + RESEARCH_END_MINUTE
    on_end_min = ON_END_HOUR * 60 + ON_END_MINUTE

    rth_dates: list[pd.Timestamp] = []
    for d in unique_days:
        idx = day_groups[d]
        tod = _tod_minutes(ny[idx])
        if np.any(tod == rth_open_min):
            rth_dates.append(d)

    prior_rth = None
    for di, d in enumerate(rth_dates):
        idx = day_groups[d]
        tod = _tod_minutes(ny[idx])
        open_loc = np.flatnonzero(tod == rth_open_min)
        if len(open_loc) == 0:
            skipped["no_rth_open"] += 1
            continue
        rth_open_i = int(idx[open_loc[0]])
        end_loc = np.flatnonzero(tod <= research_end_min)
        research_end_i = int(idx[end_loc[-1]]) if len(end_loc) else rth_open_i

        # Overnight: previous RTH date 18:00 ET through today 09:29 ET
        if di == 0:
            skipped["no_prior_rth"] += 1
            continue
        prev = rth_dates[di - 1]
        start_ts = prev.tz_localize(None)
        # 18:00 previous trading day
        on_start = pd.Timestamp(prev.date()) + pd.Timedelta(hours=ON_START_HOUR)
        on_end = pd.Timestamp(d.date()) + pd.Timedelta(hours=ON_END_HOUR, minutes=ON_END_MINUTE)
        # ny is tz-aware; compare via midnight-normalized timestamps
        ny_naive = pd.DatetimeIndex(ny).tz_localize(None) if ny.tz is None else pd.DatetimeIndex(ny).tz_convert(NY_TZ).tz_localize(None)
        # ny is already NY tz
        ny_clock = pd.DatetimeIndex(ny).tz_convert(NY_TZ).tz_localize(None)
        on_mask = (ny_clock >= on_start) & (ny_clock <= on_end)
        on_idx = np.flatnonzero(on_mask)
        if len(on_idx) < MIN_OVERNIGHT_BARS:
            skipped["thin_overnight"] += 1
            continue

        # Prior RTH 09:30–16:00 previous session
        pidx = day_groups[prev]
        ptod = _tod_minutes(ny[pidx])
        prth = pidx[(ptod >= rth_open_min) & (ptod < rth_close_min)]
        if len(prth) < MIN_PRIOR_RTH_BARS:
            skipped["no_prior_rth"] += 1
            continue

        a = float(atr[rth_open_i])
        if not np.isfinite(a) or a <= 0:
            skipped["bad_atr"] += 1
            continue

        on_h = float(hi[on_idx].max())
        on_l = float(lo[on_idx].min())
        pr_h = float(hi[prth].max())
        pr_l = float(lo[prth].min())
        pr_c = float(cl[prth[-1]])
        o = float(op[rth_open_i])

        above_h = o > pr_h
        below_l = o < pr_l
        above_c = o > pr_c
        below_c = o < pr_c
        inside = pr_l <= o <= pr_h
        if above_h:
            oclass = "OPEN_ABOVE_PRIOR_HIGH"
        elif below_l:
            oclass = "OPEN_BELOW_PRIOR_LOW"
        elif inside:
            oclass = "OPEN_INSIDE_PRIOR_RANGE"
        else:
            oclass = "OPEN_OUTSIDE_GAP_NOT_EXTREME"

        sessions.append(
            Session(
                date=str(d.date()),
                rth_open_i=rth_open_i,
                research_end_i=research_end_i,
                on_start_i=int(on_idx[0]),
                on_end_i=int(on_idx[-1]),
                on_high=on_h,
                on_low=on_l,
                on_mid=0.5 * (on_h + on_l),
                prior_rth_high=pr_h,
                prior_rth_low=pr_l,
                prior_rth_close=pr_c,
                prior_rth_mid=0.5 * (pr_h + pr_l),
                rth_open=o,
                atr_open=a,
                overnight_bars=int(len(on_idx)),
                prior_rth_bars=int(len(prth)),
                gap_atr=float((o - pr_c) / a),
                on_range_atr=float((on_h - on_l) / a) if on_h > on_l else 0.0,
                open_vs_prior_high="ABOVE" if above_h else "BELOW_OR_EQUAL",
                open_vs_prior_low="BELOW" if below_l else "ABOVE_OR_EQUAL",
                open_vs_prior_close="ABOVE" if above_c else ("BELOW" if below_c else "EQUAL"),
                open_inside_prior_range=bool(inside),
                open_class=oclass,
            )
        )
        prior_rth = prth

    meta = {
        "n_sessions": len(sessions),
        "first_date": sessions[0].date if sessions else None,
        "last_date": sessions[-1].date if sessions else None,
        "skipped": skipped,
        "rth_dates": len(rth_dates),
        "mean_overnight_bars": float(np.mean([s.overnight_bars for s in sessions])) if sessions else 0,
        "mean_on_range_atr": float(np.mean([s.on_range_atr for s in sessions])) if sessions else 0,
    }
    return sessions, meta


def sessions_to_frame(sessions: list[Session]) -> pd.DataFrame:
    return pd.DataFrame([asdict(s) for s in sessions])
