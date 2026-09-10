"""
OFFLINE DIAGNOSTIC ONLY — forward-looking M0 hypothetical labels.

These functions use future bar data to compute hyp_long_R / hyp_short_R.
They must NEVER be imported by live execution, webhook handlers, or TraderEngine code paths.

Entry convention (matches Phase72A / phase73 replay):
  - Signal evaluated at bar T (signal_bar_i = T)
  - Hypothetical entry at bar T+1 OPEN (entry_i = T+1, entry_price = open[T+1])
  - M0 walk uses phase73.trader.management (build_management + evaluate_exit)
    from bar T+2 onward (entry bar ei is not checked for stop/target).

M0 rules (via phase73/config/default.json): 1.0 ATR stop, 2.5R target,
60-minute max hold, STOP_FIRST same-bar collision, T5 disabled.

Net R subtracts NQ round-trip cost via phase58.research.instrument.NQ.cost_r
(same basis as phase69.walk_trade).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from phase58.research.instrument import NQ
from phase73.config.loader import load_config
from phase73.market_data.bar import Bar
from phase73.trader.management import build_management, evaluate_exit
from signal_ledger.config import ENTRY_OFFSET_BARS

__all__ = ["hyp_m0_long_r", "hyp_m0_short_r", "hyp_m0_both", "walk_m0_phase73", "apply_m0_cost"]

_M0_CFG = load_config()


def _entry_index(signal_bar_i: int) -> int:
    return signal_bar_i + ENTRY_OFFSET_BARS


def _gross_r(side: str, entry_price: float, exit_price: float, risk: float) -> float:
    if risk <= 0:
        return float("nan")
    d = 1.0 if side == "LONG" else -1.0
    return (exit_price - entry_price) * d / risk


def apply_m0_cost(gross_r: float, entry_price: float, risk: float) -> float:
    """Subtract NQ round-trip cost in R-units (matches phase69 walk_trade)."""
    if not np.isfinite(gross_r) or risk <= 0:
        return float("nan")
    stop = entry_price - risk  # sign unused by cost_r (uses abs distance)
    cost = NQ.cost_r(entry_price, stop)
    return float(gross_r - cost)


def walk_m0_phase73(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    op: np.ndarray,
    atr: np.ndarray,
    entry_i: int,
    side: str,
    entry_price: float | None = None,
    signal_atr: float | None = None,
) -> float:
    """
    Array-based M0 walk using the same functions as phase73 TraderEngine.on_bar().

    Mirrors engine._execute_entry → build_management, then bar loop → evaluate_exit.
    Returns net R after NQ.cost_r adjustment.
    """
    n = len(hi)
    if entry_i >= n - 2:
        return float("nan")

    ep = float(entry_price if entry_price is not None else op[entry_i])
    a = float(signal_atr if signal_atr is not None else atr[entry_i - ENTRY_OFFSET_BARS])
    if a <= 0:
        a = float(atr[entry_i]) if atr[entry_i] > 0 else max(abs(ep) * 1e-6, 1.0)

    base_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
    entry_time = base_ts + timedelta(minutes=int(entry_i))
    mgmt = build_management(side, ep, a, _M0_CFG, entry_time)

    for k in range(entry_i + 1, min(entry_i + _M0_CFG.max_hold_minutes + 1, n)):
        bar = Bar(
            timestamp=base_ts + timedelta(minutes=k),
            open=float(op[k]),
            high=float(hi[k]),
            low=float(lo[k]),
            close=float(cl[k]),
        )
        now = bar.timestamp
        exit_dec = evaluate_exit(mgmt, bar, _M0_CFG, now)
        if exit_dec is None:
            continue
        px = exit_dec.exit_price if exit_dec.exit_price is not None else float(cl[k])
        gross = _gross_r(side, ep, px, mgmt.risk)
        return apply_m0_cost(gross, ep, mgmt.risk)

    last_k = min(entry_i + _M0_CFG.max_hold_minutes, n - 1)
    gross = _gross_r(side, ep, float(cl[last_k]), mgmt.risk)
    return apply_m0_cost(gross, ep, mgmt.risk)


def hyp_m0_long_r(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    op: np.ndarray,
    atr: np.ndarray,
    signal_bar_i: int,
) -> float:
    """Simulated net R for a hypothetical LONG entered at next-bar open after signal_bar_i."""
    ei = _entry_index(signal_bar_i)
    if ei >= len(hi) - 2:
        return float("nan")
    ep = float(op[ei])
    a = float(atr[signal_bar_i]) if atr[signal_bar_i] > 0 else float(atr[ei])
    return walk_m0_phase73(hi, lo, cl, op, atr, ei, "LONG", ep, a)


def hyp_m0_short_r(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    op: np.ndarray,
    atr: np.ndarray,
    signal_bar_i: int,
) -> float:
    """Simulated net R for a hypothetical SHORT entered at next-bar open after signal_bar_i."""
    ei = _entry_index(signal_bar_i)
    if ei >= len(hi) - 2:
        return float("nan")
    ep = float(op[ei])
    a = float(atr[signal_bar_i]) if atr[signal_bar_i] > 0 else float(atr[ei])
    return walk_m0_phase73(hi, lo, cl, op, atr, ei, "SHORT", ep, a)


def hyp_m0_both(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    op: np.ndarray,
    atr: np.ndarray,
    signal_bar_i: int,
) -> tuple[float, float]:
    return (
        hyp_m0_long_r(hi, lo, cl, op, atr, signal_bar_i),
        hyp_m0_short_r(hi, lo, cl, op, atr, signal_bar_i),
    )
