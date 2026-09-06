"""Per-window liquidity and sweep forensics — uses frozen Phase78 engines."""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from phase78.python.liquidity import LiquidityLevel, LiquidityMap, freeze_liquidity_map
from phase78.python.sequence import _detect_sweep

from .taxonomy import classify_level, report_label


@dataclass
class SweepEvent:
    liquidity_type: str
    liquidity_price: float
    side: str
    sweep_time: pd.Timestamp
    sweep_extreme: float
    penetration_points: float
    penetration_atr: float
    bar_idx: int
    classification: str = ""
    report_type: str = ""


@dataclass
class WindowForensic:
    calendar_date: object
    window_id: str
    window_start: pd.Timestamp
    window_open: float
    window_atr: float
    n_levels_total: int = 0
    n_external: int = 0
    n_internal: int = 0
    nearest_external_pts: float = np.nan
    nearest_external_atr: float = np.nan
    nearest_internal_pts: float = np.nan
    nearest_internal_atr: float = np.nan
    nearest_any_pts: float = np.nan
    nearest_any_atr: float = np.nan
    density_025: int = 0
    density_050: int = 0
    density_100: int = 0
    density_200: int = 0
    density_ext_050: int = 0
    density_int_050: int = 0
    first_sweep: SweepEvent | None = None
    all_sweeps: list[SweepEvent] = field(default_factory=list)
    has_external_sweep: bool = False
    has_internal_sweep: bool = False
    only_external: bool = False
    only_internal: bool = False
    cluster_count_005: int = 0
    cluster_count_010: int = 0
    levels_before_cluster_010: int = 0


def _level_distance(open_px: float, liq: LiquidityLevel) -> float:
    if liq.side == "BUY_SIDE":
        return max(0.0, liq.level_price - open_px)
    return max(0.0, open_px - liq.level_price)


def _cluster_levels(levels: list[LiquidityLevel], atr: float, tol_atr: float) -> list[list[LiquidityLevel]]:
    if not levels or not np.isfinite(atr) or atr <= 0:
        return []
    tol = max(tol_atr * atr, 1.0)
    sorted_lv = sorted(levels, key=lambda x: x.level_price)
    clusters: list[list[LiquidityLevel]] = []
    for lv in sorted_lv:
        placed = False
        for cl in clusters:
            if abs(cl[0].level_price - lv.level_price) <= tol:
                cl.append(lv)
                placed = True
                break
        if not placed:
            clusters.append([lv])
    return clusters


def _sweep_followthrough(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    bar_idx: int,
    side: str,
    level_price: float,
    horizon: int = 5,
) -> str:
    end = min(len(highs), bar_idx + horizon + 1)
    sub_h = highs[bar_idx:end]
    sub_l = lows[bar_idx:end]
    sub_c = closes[bar_idx:end]
    if len(sub_h) == 0:
        return "UNKNOWN"
    if side == "BUY_SIDE":
        reclaimed = bool(np.any(sub_c < level_price))
        continued = bool(np.max(sub_h) > highs[bar_idx])
        closed_beyond = bool(sub_c[-1] > level_price)
    else:
        reclaimed = bool(np.any(sub_c > level_price))
        continued = bool(np.min(sub_l) < lows[bar_idx])
        closed_beyond = bool(sub_c[-1] < level_price)
    if reclaimed and not closed_beyond:
        return "RECLAIMED"
    if continued and closed_beyond:
        return "CONTINUED_BEYOND"
    if closed_beyond:
        return "CLOSED_BEYOND"
    return "RETURNED_INSIDE"


def analyze_window(
    df_slice: pd.DataFrame,
    liq_map: LiquidityMap,
    calendar_date: object,
    window_id: str,
    window_end: pd.Timestamp,
) -> WindowForensic:
    index = df_slice.index
    open_px = float(df_slice["open"].iloc[0])
    atr = float(df_slice["atr"].dropna().iloc[0]) if df_slice["atr"].notna().any() else np.nan
    wf = WindowForensic(calendar_date, window_id, index[0], open_px, atr)
    levels = liq_map.levels
    wf.n_levels_total = len(levels)
    wf.n_external = sum(1 for l in levels if classify_level(l.level_type) == "EXTERNAL_MAJOR")
    wf.n_internal = sum(1 for l in levels if classify_level(l.level_type) == "INTERNAL_SHORT_TERM")

    ext_dists, int_dists, all_dists = [], [], []
    for lv in levels:
        d = _level_distance(open_px, lv)
        all_dists.append(d)
        cls = classify_level(lv.level_type)
        if cls == "EXTERNAL_MAJOR":
            ext_dists.append(d)
        elif cls == "INTERNAL_SHORT_TERM":
            int_dists.append(d)
        for thr, attr in ((0.25, "density_025"), (0.50, "density_050"), (1.0, "density_100"), (2.0, "density_200")):
            if np.isfinite(atr) and d <= thr * atr:
                setattr(wf, attr, getattr(wf, attr) + 1)
        if np.isfinite(atr) and d <= 0.5 * atr:
            if cls == "EXTERNAL_MAJOR":
                wf.density_ext_050 += 1
            elif cls == "INTERNAL_SHORT_TERM":
                wf.density_int_050 += 1

    if ext_dists:
        wf.nearest_external_pts = float(min(ext_dists))
        wf.nearest_external_atr = wf.nearest_external_pts / atr if np.isfinite(atr) and atr > 0 else np.nan
    if int_dists:
        wf.nearest_internal_pts = float(min(int_dists))
        wf.nearest_internal_atr = wf.nearest_internal_pts / atr if np.isfinite(atr) and atr > 0 else np.nan
    if all_dists:
        wf.nearest_any_pts = float(min(all_dists))
        wf.nearest_any_atr = wf.nearest_any_pts / atr if np.isfinite(atr) and atr > 0 else np.nan

    for tol in (0.05, 0.10):
        clusters = _cluster_levels(levels, atr, tol)
        if tol == 0.05:
            wf.cluster_count_005 = len(clusters)
        else:
            wf.cluster_count_010 = len(clusters)
            wf.levels_before_cluster_010 = len(levels)

    highs = df_slice["high"].values
    lows = df_slice["low"].values
    closes = df_slice["close"].values
    swept_keys: set[tuple[str, float]] = set()

    for local_i in range(len(df_slice)):
        ts = index[local_i]
        if ts > window_end:
            break
        h, l = highs[local_i], lows[local_i]
        for liq in liq_map.levels:
            key = (liq.level_type, liq.level_price)
            if key in swept_keys:
                continue
            swept, extreme, dist = _detect_sweep(h, l, liq)
            if not swept:
                continue
            swept_keys.add(key)
            pen_atr = dist / atr if np.isfinite(atr) and atr > 0 else np.nan
            ev = SweepEvent(
                liquidity_type=liq.level_type,
                liquidity_price=liq.level_price,
                side=liq.side,
                sweep_time=ts,
                sweep_extreme=extreme,
                penetration_points=dist,
                penetration_atr=pen_atr,
                bar_idx=local_i,
                classification=classify_level(liq.level_type),
                report_type=report_label(liq.level_type),
            )
            wf.all_sweeps.append(ev)
            if wf.first_sweep is None:
                wf.first_sweep = ev
            # Phase78 stops at first sweep for setup — forensic continues logging all sweeps

    wf.has_external_sweep = any(s.classification == "EXTERNAL_MAJOR" for s in wf.all_sweeps)
    wf.has_internal_sweep = any(s.classification == "INTERNAL_SHORT_TERM" for s in wf.all_sweeps)
    wf.only_external = wf.has_external_sweep and not wf.has_internal_sweep
    wf.only_internal = wf.has_internal_sweep and not wf.has_external_sweep
    return wf


def window_forensic_row(wf: WindowForensic) -> dict:
    fs = wf.first_sweep
    mins_to_sweep = np.nan
    if fs is not None:
        mins_to_sweep = (fs.sweep_time - wf.window_start).total_seconds() / 60.0
    return {
        "calendar_date": str(wf.calendar_date),
        "window_id": wf.window_id,
        "window_start": wf.window_start,
        "window_open": wf.window_open,
        "window_atr": wf.window_atr,
        "n_levels_total": wf.n_levels_total,
        "n_external": wf.n_external,
        "n_internal": wf.n_internal,
        "nearest_external_pts": wf.nearest_external_pts,
        "nearest_external_atr": wf.nearest_external_atr,
        "nearest_internal_pts": wf.nearest_internal_pts,
        "nearest_internal_atr": wf.nearest_internal_atr,
        "nearest_any_pts": wf.nearest_any_pts,
        "nearest_any_atr": wf.nearest_any_atr,
        "density_025": wf.density_025,
        "density_050": wf.density_050,
        "density_100": wf.density_100,
        "density_200": wf.density_200,
        "density_ext_050": wf.density_ext_050,
        "density_int_050": wf.density_int_050,
        "cluster_count_005": wf.cluster_count_005,
        "cluster_count_010": wf.cluster_count_010,
        "levels_raw": wf.levels_before_cluster_010,
        "has_sweep": fs is not None,
        "first_sweep_type": fs.liquidity_type if fs else None,
        "first_sweep_report_type": fs.report_type if fs else None,
        "first_sweep_class": fs.classification if fs else None,
        "first_sweep_time": fs.sweep_time if fs else None,
        "minutes_to_first_sweep": mins_to_sweep,
        "first_penetration_pts": fs.penetration_points if fs else np.nan,
        "first_penetration_atr": fs.penetration_atr if fs else np.nan,
        "n_sweeps_total": len(wf.all_sweeps),
        "has_external_sweep": wf.has_external_sweep,
        "has_internal_sweep": wf.has_internal_sweep,
        "only_external": wf.only_external,
        "only_internal": wf.only_internal,
        "both_ext_int": wf.has_external_sweep and wf.has_internal_sweep,
    }
