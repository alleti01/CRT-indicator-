"""ATM-A causal bar walk — management only."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from phase58.research.instrument import NQ


@dataclass
class ATMParams:
    stop_r: float = 1.0
    target_r: float = 2.5
    be_trigger_r: float = 1.0
    be_offset_r: float = 0.05
    max_hold: int = 60


def _risk_stop(ep: float, direction: str, atr: float, stop_r: float) -> tuple[float, float]:
    risk = stop_r * atr
    if risk <= 0:
        risk = max(0.25 * atr, 1e-9)
    if direction == "LONG":
        return ep - risk, risk
    return ep + risk, risk


def walk_atm_a(
    hi,
    lo,
    cl,
    op,
    *,
    entry_i: int,
    direction: str,
    entry_price: float,
    atr: float,
    params: ATMParams | None = None,
    n: int | None = None,
) -> dict:
    """
    Causal ATM-A management from entry bar+1.
    Collision: STOP_FIRST (same as Phase73 M0 baseline).
    BE trigger + BE stop same bar: activate BE if high/low reaches trigger without
    initial stop hit first; then if BE stop also touched on same bar → BREAKEVEN_STOP.
    """
    params = params or ATMParams()
    d = 1 if direction == "LONG" else -1
    ep = float(entry_price)
    initial_stop, risk = _risk_stop(ep, direction, atr, params.stop_r)
    target = ep + d * params.target_r * risk
    be_trigger_px = ep + d * params.be_trigger_r * risk
    be_stop_px = ep + d * params.be_offset_r * risk

    be_active = False
    cur_stop = initial_stop
    mfe = mae = 0.0
    peak_r = 0.0
    be_activation_bar: Optional[int] = None
    be_activation_minute: Optional[int] = None

    end_i = min(entry_i + params.max_hold, (n or len(hi)) - 1)

    for k in range(entry_i + 1, end_i + 1):
        h, l, c = float(hi[k]), float(lo[k]), float(cl[k])
        bar_fav = (h - ep) * d / risk
        bar_adv = (ep - l) * d / risk if d == 1 else (h - ep) / risk
        mfe = max(mfe, bar_fav)
        mae = max(mae, bar_adv)
        peak_r = max(peak_r, mfe)
        minutes = k - entry_i

        if not be_active:
            hit_initial = l <= initial_stop if d == 1 else h >= initial_stop
            hit_target = h >= target if d == 1 else l <= target
            hit_be_trigger = h >= be_trigger_px if d == 1 else l <= be_trigger_px

            if hit_initial and hit_target:
                return _pack(
                    k, -1.0, "INITIAL_STOP", initial_stop, mfe, mae, ep, risk, d, minutes,
                    be_active=False, be_activation_bar=None, be_activation_minute=None,
                )
            if hit_initial:
                return _pack(
                    k, -1.0, "INITIAL_STOP", initial_stop, mfe, mae, ep, risk, d, minutes,
                    be_active=False, be_activation_bar=None, be_activation_minute=None,
                )
            if hit_target:
                return _pack(
                    k, params.target_r, "TARGET", target, mfe, mae, ep, risk, d, minutes,
                    be_active=False, be_activation_bar=None, be_activation_minute=None,
                )
            if hit_be_trigger:
                be_active = True
                cur_stop = be_stop_px
                be_activation_bar = k
                be_activation_minute = minutes
                hit_be_stop = l <= cur_stop if d == 1 else h >= cur_stop
                hit_tgt_after = h >= target if d == 1 else l <= target
                if hit_be_stop and hit_tgt_after:
                    exit_r = params.be_offset_r
                    return _pack(
                        k, exit_r, "BREAKEVEN_STOP", cur_stop, mfe, mae, ep, risk, d, minutes,
                        be_active=True, be_activation_bar=be_activation_bar, be_activation_minute=be_activation_minute,
                    )
                if hit_be_stop:
                    exit_r = params.be_offset_r
                    return _pack(
                        k, exit_r, "BREAKEVEN_STOP", cur_stop, mfe, mae, ep, risk, d, minutes,
                        be_active=True, be_activation_bar=be_activation_bar, be_activation_minute=be_activation_minute,
                    )
        else:
            hit_be_stop = l <= cur_stop if d == 1 else h >= cur_stop
            hit_target = h >= target if d == 1 else l <= target
            if hit_be_stop and hit_target:
                exit_r = params.be_offset_r
                return _pack(
                    k, exit_r, "BREAKEVEN_STOP", cur_stop, mfe, mae, ep, risk, d, minutes,
                    be_active=True, be_activation_bar=be_activation_bar, be_activation_minute=be_activation_minute,
                )
            if hit_be_stop:
                exit_r = params.be_offset_r
                return _pack(
                    k, exit_r, "BREAKEVEN_STOP", cur_stop, mfe, mae, ep, risk, d, minutes,
                    be_active=True, be_activation_bar=be_activation_bar, be_activation_minute=be_activation_minute,
                )
            if hit_target:
                return _pack(
                    k, params.target_r, "TARGET", target, mfe, mae, ep, risk, d, minutes,
                    be_active=True, be_activation_bar=be_activation_bar, be_activation_minute=be_activation_minute,
                )

        if k == end_i:
            exit_r = (c - ep) * d / risk
            return _pack(
                k, exit_r, "TIME_EXIT", c, mfe, mae, ep, risk, d, minutes,
                be_active=be_active, be_activation_bar=be_activation_bar, be_activation_minute=be_activation_minute,
            )

    c = float(cl[end_i])
    exit_r = (c - ep) * d / risk
    return _pack(
        end_i, exit_r, "TIME_EXIT", c, mfe, mae, ep, risk, d, end_i - entry_i,
        be_active=be_active, be_activation_bar=be_activation_bar, be_activation_minute=be_activation_minute,
    )


def counterfactual_killed_winner_path(
    hi, lo, cl, op, *, entry_i: int, direction: str, entry_price: float, atr: float, params: ATMParams | None = None, n: int | None = None,
) -> bool:
    """
    For a baseline TARGET trade: did price reach +be_trigger_r, retrace to BE stop,
    before reaching target_r? (path-only, no baseline exit at target).
    """
    params = params or ATMParams()
    d = 1 if direction == "LONG" else -1
    ep = float(entry_price)
    _, risk = _risk_stop(ep, direction, atr, params.stop_r)
    target = ep + d * params.target_r * risk
    be_trigger_px = ep + d * params.be_trigger_r * risk
    be_stop_px = ep + d * params.be_offset_r * risk
    end_i = min(entry_i + params.max_hold, (n or len(hi)) - 1)
    be_armed = False
    for k in range(entry_i + 1, end_i + 1):
        h, l = float(hi[k]), float(lo[k])
        if d == 1:
            if l <= ep - risk:
                return False
            if h >= target:
                return False
            if not be_armed and h >= be_trigger_px:
                be_armed = True
            if be_armed and l <= be_stop_px:
                return True
        else:
            if h >= ep + risk:
                return False
            if l <= target:
                return False
            if not be_armed and l <= be_trigger_px:
                be_armed = True
            if be_armed and h >= be_stop_px:
                return True
    return False


def _pack(
    exit_i, gross_r, reason, exit_px, mfe, mae, ep, risk, d, hold_minutes,
    *, be_active, be_activation_bar, be_activation_minute,
):
    cost = NQ.cost_r(ep, ep - risk if d == 1 else ep + risk)
    return {
        "exit_i": exit_i,
        "exit_price": exit_px,
        "exit_reason": reason,
        "gross_r": gross_r,
        "cost_r": cost,
        "net_r": gross_r - cost,
        "mfe_r": mfe,
        "mae_r": mae,
        "hold_minutes": hold_minutes,
        "be_activated": be_active or be_activation_bar is not None,
        "be_activation_bar": be_activation_bar,
        "be_activation_minute": be_activation_minute,
        "minutes_be_to_exit": (hold_minutes - be_activation_minute) if be_activation_minute is not None else None,
    }
