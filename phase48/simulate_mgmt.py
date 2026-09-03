"""Management-aware 1m trade simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from phase39.classify import classify_behavior

from phase45.execution.data_1m import cost_r
from phase45.execution.simulate import simulate_1m

from .config import MAX_HOLD_CONT, MAX_HOLD_REV, TARGET_R_CONT, TARGET_R_REV
from .structure import causal_swing_levels, opposite_bos, trail_swing_stop


@dataclass
class MgmtSpec:
    """Management specification for one simulation."""

    name: str = "M0"
    stop_mode: str = "frozen"  # frozen | computed
    stop_price: float | None = None
    target_mode: str = "frozen"  # frozen | fixed_r | structure
    target_price: float | None = None
    target_r: float | None = None
    structure_target_cap: tuple[float, float] | None = None
    be_trigger_r: float | None = None
    be_dest: str = "BE0"
    partials: list[tuple[float, float]] = field(default_factory=list)
    partial_be_runner: bool = False
    trail_activate_r: float | None = None
    trail_method: str | None = None
    trail_param: float | None = None
    opposite_bos: bool = False
    opposite_bos_min_r: float = 0.0
    time_exit_bars: int | None = None
    stagnation: str | None = None
    stagnation_minutes: int = 5
    profit_lock_trigger: float | None = None
    profit_lock_r: float | None = None
    invalidation_15m: bool = False
    phase44_entry: float | None = None
    max_hold_bars: int | None = None


def _wrong_direction(mfe: float, mae: float, t05: float) -> int:
    row = pd.Series({"MFE_R": mfe, "MAE_R": mae, "directional_efficiency": 0.5, "movement_efficiency": 0.5, "bars_to_plus_0.50r": t05})
    return int(classify_behavior(row) == "WRONG_DIRECTION")


def _be_stop(entry: float, risk: float, d: int, dest: str, cost_mult: float) -> float:
    if dest == "BE1":
        cr = cost_r(entry, entry - risk * d, cost_mult) * risk  # approximate lock
        return entry + d * cr
    if dest == "BE2":
        return entry + d * 0.1 * risk
    return entry


def _fixed_target_r(signal_type: str) -> float:
    return TARGET_R_CONT if signal_type in ("L", "S") else TARGET_R_REV


def simulate_managed(
    market: pd.DataFrame,
    entry_i: int,
    entry_price: float,
    stop: float,
    target: float,
    direction: str,
    signal_type: str,
    spec: MgmtSpec,
    *,
    cost_mult: float = 1.0,
) -> dict[str, Any]:
    """Simulate trade with optional management. Stop-first intrabar ordering."""
    if spec.name == "M0" and spec.stop_mode == "frozen" and spec.target_mode == "frozen" and not any(
        [spec.be_trigger_r, spec.partials, spec.trail_activate_r, spec.opposite_bos, spec.time_exit_bars, spec.stagnation, spec.profit_lock_trigger, spec.invalidation_15m]
    ):
        return simulate_1m(market, entry_i, entry_price, stop, target, direction, signal_type, cost_mult=cost_mult)

    d = 1 if str(direction).lower() == "long" else -1
    cur_stop = float(spec.stop_price if spec.stop_price is not None else stop)
    risk = abs(entry_price - cur_stop) or 1e-9

    if spec.target_mode == "fixed_r" and spec.target_r is not None:
        tgt_px = entry_price + d * spec.target_r * risk
    elif spec.target_mode == "structure" and spec.target_price is not None:
        tgt_px = float(spec.target_price)
        if spec.structure_target_cap:
            mn, mx = spec.structure_target_cap
            r_dist = abs(tgt_px - entry_price) / risk
            r_dist = min(max(r_dist, mn), mx)
            tgt_px = entry_price + d * r_dist * risk
    else:
        tgt_px = float(spec.target_price if spec.target_price is not None else target)

    max_bars = spec.max_hold_bars or (MAX_HOLD_CONT if signal_type in ("L", "S") else MAX_HOLD_REV)
    hi_a = market["high"].astype(float).values
    lo_a = market["low"].astype(float).values
    cl_a = market["close"].astype(float).values
    atr_a = market["atr"].astype(float).values if "atr" in market.columns else np.full(len(market), risk)

    mfe = mae = 0.0
    t05 = t1 = t15 = t2 = np.nan
    exit_type = "DATA_END"
    exit_i = entry_i
    exit_px = entry_price
    realized_parts: list[tuple[float, float]] = []
    remaining = 1.0
    be_active = False
    trail_active = False
    peak_mfe = 0.0
    lock_stop = cur_stop
    entry_ts = market.index[entry_i]
    partial_done: set[tuple[float, float]] = set()

    for elapsed, j in enumerate(range(entry_i + 1, min(len(market), entry_i + 1 + max_bars)), start=1):
        hi, lo, cl = hi_a[j], lo_a[j], cl_a[j]
        if d == 1:
            bar_mfe = (hi - entry_price) / risk
            bar_mae = (entry_price - lo) / risk
            hit_stop = lo <= lock_stop
            hit_tgt = hi >= tgt_px
        else:
            bar_mfe = (entry_price - lo) / risk
            bar_mae = (hi - entry_price) / risk
            hit_stop = hi >= lock_stop
            hit_tgt = lo <= tgt_px

        if bar_mfe > mfe:
            mfe = bar_mfe
        if bar_mae > mae:
            mae = bar_mae
        if np.isnan(t05) and mfe >= 0.5:
            t05 = elapsed
        if np.isnan(t1) and mfe >= 1.0:
            t1 = elapsed
        if np.isnan(t15) and mfe >= 1.5:
            t15 = elapsed
        if np.isnan(t2) and mfe >= 2.0:
            t2 = elapsed
        peak_mfe = max(peak_mfe, mfe)

        # Conservative: stop before target on same bar
        if hit_stop and remaining > 0:
            r_exit = (lock_stop - entry_price) / risk * d
            realized_parts.append((remaining, r_exit))
            remaining = 0.0
            exit_type = "STOP"
            exit_i, exit_px = j, lock_stop
            break

        if hit_tgt and remaining > 0:
            r_exit = spec.target_r if spec.target_mode == "fixed_r" and spec.target_r else _fixed_target_r(signal_type)
            realized_parts.append((remaining, r_exit))
            remaining = 0.0
            exit_type = "TARGET"
            exit_i, exit_px = j, tgt_px
            break

        # Opposite BOS exit (after min R)
        if spec.opposite_bos and mfe >= spec.opposite_bos_min_r and opposite_bos(hi_a, lo_a, cl_a, j, direction):
            r_exit = (cl - entry_price) / risk * d
            realized_parts.append((remaining, r_exit))
            remaining = 0.0
            exit_type = "OPP_BOS"
            exit_i, exit_px = j, cl
            break

        # Time exit
        if spec.time_exit_bars and elapsed >= spec.time_exit_bars:
            r_exit = (cl - entry_price) / risk * d
            realized_parts.append((remaining, r_exit))
            remaining = 0.0
            exit_type = "TIME"
            exit_i, exit_px = j, cl
            break

        # Stagnation exits (causal: checked at bar close)
        if spec.stagnation == "ST1" and elapsed >= 5 and mfe < 0.25:
            realized_parts.append((remaining, (cl - entry_price) / risk * d))
            remaining = 0.0
            exit_type = "STAGNATION"
            exit_i, exit_px = j, cl
            break
        if spec.stagnation == "ST2" and elapsed >= 10 and mfe < 0.5:
            realized_parts.append((remaining, (cl - entry_price) / risk * d))
            remaining = 0.0
            exit_type = "STAGNATION"
            exit_i, exit_px = j, cl
            break
        if spec.stagnation == "ST3" and elapsed >= 15 and mfe < 0.5:
            realized_parts.append((remaining, (cl - entry_price) / risk * d))
            remaining = 0.0
            exit_type = "STAGNATION"
            exit_i, exit_px = j, cl
            break
        if spec.stagnation == "ST4" and elapsed >= spec.stagnation_minutes and abs((cl - entry_price) / risk) <= 0.25:
            realized_parts.append((remaining, (cl - entry_price) / risk * d))
            remaining = 0.0
            exit_type = "STAGNATION"
            exit_i, exit_px = j, cl
            break

        # Partial exits at bar close when level touched intrabar
        for level_r, frac in spec.partials:
            if remaining <= 0:
                break
            key = (level_r, frac)
            if mfe >= level_r and key not in partial_done:
                take = min(frac, remaining)
                realized_parts.append((take, level_r))
                remaining -= take
                partial_done.add(key)

        # End-of-bar management updates (active next bar)
        if spec.be_trigger_r and not be_active and mfe >= spec.be_trigger_r:
            lock_stop = _be_stop(entry_price, risk, d, spec.be_dest, cost_mult)
            be_active = True
        if spec.profit_lock_trigger and peak_mfe >= spec.profit_lock_trigger and spec.profit_lock_r is not None:
            new_lock = entry_price + d * spec.profit_lock_r * risk
            if d == 1:
                lock_stop = max(lock_stop, new_lock)
            else:
                lock_stop = min(lock_stop, new_lock)
        if spec.trail_activate_r and mfe >= spec.trail_activate_r:
            trail_active = True
        if trail_active and spec.trail_method:
            if spec.trail_method == "TR1" and j > 0:
                trail = lo_a[j - 1] if d == 1 else hi_a[j - 1]
                lock_stop = max(lock_stop, trail) if d == 1 else min(lock_stop, trail)
            elif spec.trail_method == "TR2":
                ts = trail_swing_stop(hi_a, lo_a, j, direction)
                if np.isfinite(ts):
                    if d == 1:
                        lock_stop = max(lock_stop, min(ts, hi))  # never above bar high
                    else:
                        lock_stop = min(lock_stop, max(ts, lo))
            elif spec.trail_method == "TR3" and spec.trail_param:
                atr = atr_a[j]
                trail = cl - spec.trail_param * atr if d == 1 else cl + spec.trail_param * atr
                lock_stop = max(lock_stop, trail) if d == 1 else min(lock_stop, trail)
            elif spec.trail_method == "TR4" and spec.trail_param:
                trail_r = peak_mfe - spec.trail_param
                trail_px = entry_price + d * trail_r * risk
                lock_stop = max(lock_stop, trail_px) if d == 1 else min(lock_stop, trail_px)

        # 15m invalidation: completed 15m bar closes against phase44 entry
        if spec.invalidation_15m and spec.phase44_entry is not None:
            bar_ts = market.index[j]
            if bar_ts.minute % 15 == 14 or (bar_ts - entry_ts).total_seconds() >= 900:
                p44 = float(spec.phase44_entry)
                if (d == 1 and cl < p44) or (d == -1 and cl > p44):
                    r_exit = (cl - entry_price) / risk * d
                    realized_parts.append((remaining, r_exit))
                    remaining = 0.0
                    exit_type = "INV_15M"
                    exit_i, exit_px = j, cl
                    break

        if elapsed >= max_bars and remaining > 0:
            r_exit = (cl - entry_price) / risk * d
            realized_parts.append((remaining, r_exit))
            remaining = 0.0
            exit_type = "TIME"
            exit_i, exit_px = j, cl
            break

    if remaining > 0 and not realized_parts:
        realized_parts.append((1.0, 0.0))

    gross = sum(w * r for w, r in realized_parts)
    cr = cost_r(entry_price, cur_stop, cost_mult)
    # Extra cost for partial legs
    n_exits = max(1, len([p for p in spec.partials if hasattr(spec, "_partial_done")]))
    if len(realized_parts) > 1:
        cr *= len(realized_parts)
    net = gross - cr
    mfe_capture = min(gross / mfe, 1.0) if mfe > 0 else 0.0

    return {
        "gross_R": gross,
        "net_R": net,
        "cost_R": cr,
        "MFE_R": mfe,
        "MAE_R": mae,
        "bars_to_plus_0.5r": t05,
        "bars_to_plus_1r": t1,
        "bars_to_plus_1.5r": t15,
        "bars_to_plus_2r": t2,
        "exit_type": exit_type,
        "exit_timestamp": market.index[exit_i] if exit_i < len(market) else market.index[-1],
        "exit_i": exit_i,
        "exit_price": exit_px,
        "wrong_direction": _wrong_direction(mfe, mae, t05 if np.isfinite(t05) else np.nan),
        "hold_bars": exit_i - entry_i,
        "mfe_capture": mfe_capture,
        "realized_parts": len(realized_parts),
        "initial_risk_points": risk,
        "initial_stop": cur_stop,
        "initial_target": tgt_px,
    }
