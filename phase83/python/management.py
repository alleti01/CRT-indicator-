"""Frozen M0 walk + forward excursions. Independent of live engines."""
from __future__ import annotations

import numpy as np

from phase58.research.instrument import NQ
from phase83.python.config import M0, SLIP_TICKS, TICK_SIZE


def walk_m0(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    *,
    entry_i: int,
    direction: str,
    entry_price: float,
    atr: float,
    stop_r: float = M0["stop_r"],
    target_r: float = M0["target_r"],
    max_hold: int = M0["max_hold_minutes"],
    stop_price: float | None = None,
) -> dict:
    """STOP_FIRST, check from entry_i+1. Risk = stop_r * ATR unless structural stop given."""
    n = len(hi)
    d = 1.0 if direction == "LONG" else -1.0
    ep = float(entry_price)
    a = float(atr) if atr > 0 else 1.0
    if stop_price is None:
        risk = stop_r * a
        stop = ep - d * risk
    else:
        stop = float(stop_price)
        risk = abs(ep - stop)
        if risk <= 0:
            risk = max(0.25 * a, 1e-9)
    target = ep + d * target_r * risk
    end_i = min(entry_i + max_hold, n - 1)
    mfe = mae = 0.0
    if entry_i >= n - 2 or risk <= 0:
        return {
            "gross_r": float("nan"),
            "net_r": float("nan"),
            "exit_reason": "NO_ROOM",
            "exit_i": entry_i,
            "hold_minutes": 0,
            "mfe_r": 0.0,
            "mae_r": 0.0,
            "risk": risk,
            "stop": stop,
            "target": target,
        }

    for k in range(entry_i + 1, end_i + 1):
        h, l, c = float(hi[k]), float(lo[k]), float(cl[k])
        fav = (h - ep) * d / risk
        adv = (ep - l) * d / risk if d == 1 else (h - ep) / risk
        mfe = max(mfe, fav)
        mae = max(mae, adv)
        hit_stop = l <= stop if d == 1 else h >= stop
        hit_tgt = h >= target if d == 1 else l <= target
        if hit_stop and hit_tgt:
            return _pack(-1.0, "M0_STOP", k, entry_i, mfe, mae, ep, risk, stop, target)
        if hit_stop:
            return _pack(-1.0, "M0_STOP", k, entry_i, mfe, mae, ep, risk, stop, target)
        if hit_tgt:
            return _pack(target_r, "M0_TARGET", k, entry_i, mfe, mae, ep, risk, stop, target)
        if k == end_i:
            gr = (c - ep) * d / risk
            return _pack(gr, "TIME_EXIT", k, entry_i, mfe, mae, ep, risk, stop, target)

    c = float(cl[end_i])
    return _pack((c - ep) * d / risk, "TIME_EXIT", end_i, entry_i, mfe, mae, ep, risk, stop, target)


def _pack(gross, reason, exit_i, entry_i, mfe, mae, ep, risk, stop, target) -> dict:
    cost = NQ.cost_r(ep, stop)
    return {
        "gross_r": float(gross),
        "net_r": float(gross - cost),
        "cost_r": float(cost),
        "exit_reason": reason,
        "exit_i": int(exit_i),
        "hold_minutes": int(exit_i - entry_i),
        "mfe_r": float(mfe),
        "mae_r": float(mae),
        "risk": float(risk),
        "stop": float(stop),
        "target": float(target),
    }


def net_with_slip(gross_r: float, entry_price: float, risk: float, extra_ticks: int) -> float:
    if not np.isfinite(gross_r) or risk <= 0:
        return float("nan")
    base = NQ.cost_r(entry_price, entry_price - risk)
    extra = extra_ticks * TICK_SIZE / risk
    return float(gross_r - base - extra)


def forward_excursions(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    *,
    event_i: int,
    direction: str,
    atr: float,
    horizons: tuple[int, ...] = (5, 10, 15, 30, 60),
) -> dict:
    """MFE/MAE in ATR from event close, causal forward only."""
    n = len(hi)
    d = 1.0 if direction == "LONG" else -1.0
    px = float(cl[event_i])
    a = float(atr) if atr > 0 else 1.0
    out = {}
    for hzn in horizons:
        end = min(event_i + hzn, n - 1)
        if end <= event_i:
            out[f"mfe_{hzn}"] = float("nan")
            out[f"mae_{hzn}"] = float("nan")
            continue
        sl = slice(event_i + 1, end + 1)
        fav = (hi[sl].max() - px) * d / a if d == 1 else (px - lo[sl].min()) / a
        adv = (px - lo[sl].min()) / a if d == 1 else (hi[sl].max() - px) / a
        out[f"mfe_{hzn}"] = float(fav)
        out[f"mae_{hzn}"] = float(adv)
    return out


def first_passage(
    hi: np.ndarray,
    lo: np.ndarray,
    *,
    event_i: int,
    direction: str,
    atr: float,
    fav: float,
    adv: float,
    max_bars: int = 60,
) -> bool | None:
    """True if +fav ATR prints before -adv ATR. None if neither within window."""
    n = len(hi)
    d = 1.0 if direction == "LONG" else -1.0
    # use event close as origin — caller should pass event_i of confirmation
    return None  # filled by first_passage_from_price


def first_passage_from_price(
    hi: np.ndarray,
    lo: np.ndarray,
    *,
    event_i: int,
    origin: float,
    direction: str,
    up_pts: float,
    dn_pts: float,
    max_bars: int = 60,
) -> bool | None:
    n = len(hi)
    d = 1.0 if direction == "LONG" else -1.0
    up = origin + d * up_pts
    dn = origin - d * dn_pts
    end = min(event_i + max_bars, n - 1)
    for k in range(event_i + 1, end + 1):
        h, l = float(hi[k]), float(lo[k])
        hit_up = h >= up if d == 1 else l <= up
        hit_dn = l <= dn if d == 1 else h >= dn
        if hit_dn and hit_up:
            return False  # adverse first on collision (conservative)
        if hit_dn:
            return False
        if hit_up:
            return True
    return None
