"""Phase72A — Python mirror of Pine Phase71 management semantics (not TV parity)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from phase72.python.independent_simulator import simulate_trade


@dataclass
class PineMirrorState:
    pos_state: str = "FLAT"
    entry_px: float = 0.0
    init_atr: float = 0.0
    stop_px: float = 0.0
    tgt_px: float = 0.0
    entry_bar: int = -1
    signal_bar: int = -1
    pos_dir: int = 0
    run_mfe_r: float = 0.0
    t5_checked: bool = False
    skipped_signals: int = 0


def mirror_trade(direction: str, signal_i: int, entry_i: int, entry_price: float, atr: float,
                 hi, lo, cl, op, n: int, enable_t5: bool = True) -> dict:
    """Mirror Pine pending→entry→manage flow for one trade."""
    return simulate_trade(direction, entry_i, entry_price, atr, hi, lo, cl, op, n, enable_t5)


def mirror_one_position(execs, m, enable_t5: bool = True):
    """Run one-position semantics matching Pine posState machine."""
    from phase72.python.independent_simulator import run_one_position_independent
    return run_one_position_independent(execs, m, enable_t5)
