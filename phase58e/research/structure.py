"""Structural progression and countertrend strength — causal at bar i."""
from __future__ import annotations

import numpy as np

from phase58b.research.precompute import MTFArrays
from phase58d.research.context_maps import ctx5_at_1m, m1_market_view


def structural_features(m: MTFArrays, i: int, cfg: dict) -> dict:
    """Causal structure features for both directions."""
    j = int(m.m1_to_m5[i]) if i < m.m1_n else 0
    ctx5 = ctx5_at_1m(m, i, cfg)
    m1 = m1_market_view(m, cfg.get("swing_period", 5))

    hh = np.isfinite(m1.sh1[i]) and np.isfinite(m1.sh2[i]) and m1.sh1[i] > m1.sh2[i]
    hl = np.isfinite(m1.sl1[i]) and np.isfinite(m1.sl2[i]) and m1.sl1[i] > m1.sl2[i]
    lh = np.isfinite(m1.sh1[i]) and np.isfinite(m1.sh2[i]) and m1.sh1[i] < m1.sh2[i]
    ll = np.isfinite(m1.sl1[i]) and np.isfinite(m1.sl2[i]) and m1.sl1[i] < m1.sl2[i]

    bull_struct = hh or hl
    bear_struct = lh or ll

    # Failed extension (causal)
    a = m1.atr[i] if np.isfinite(m1.atr[i]) and m1.atr[i] > 0 else 1.0
    fail_up = i >= 2 and m1.hi[i] > m1.hi[i - 1] and (m1.hi[i] - m1.hi[i - 1]) / a < 0.15 and m1.cl[i] < m1.cl[i - 1]
    fail_dn = i >= 2 and m1.lo[i] < m1.lo[i - 1] and (m1.lo[i - 1] - m1.lo[i]) / a < 0.15 and m1.cl[i] > m1.cl[i - 1]

    return {
        "bull_structure": bull_struct,
        "bear_structure": bear_struct,
        "5m_bull": ctx5.get("bull", 0),
        "5m_bear": ctx5.get("bear", 0),
        "failed_up_extension": fail_up,
        "failed_down_extension": fail_dn,
    }


def countertrend_strength(m: MTFArrays, i: int, active: dict, cfg: dict) -> dict:
    """Countertrend impulse relative to active move impulse."""
    lb = cfg.get("progress_lookback_1m", 8)
    imp_lb = cfg.get("impulse_lookback_1m", 12)
    if i < imp_lb:
        return {"countertrend_ratio": 0.0, "active_impulse_atr": 0.0, "counter_impulse_atr": 0.0}

    a = m.m1_atr[i] if np.isfinite(m.m1_atr[i]) and m.m1_atr[i] > 0 else 1.0
    dom = active["dominant_active"]

    start = max(0, i - imp_lb)
    if dom in ("STRONG_UP", "UP"):
        active_start = m.m1_lo[start : i + 1].min()
        active_imp = (m.m1_hi[i] - active_start) / a
        ct_start = m.m1_hi[i]
        ct_end = m.m1_lo[max(0, i - lb) : i + 1].min()
        counter_imp = max(0.0, (ct_start - ct_end) / a)
    elif dom in ("STRONG_DOWN", "DOWN"):
        active_start = m.m1_hi[start : i + 1].max()
        active_imp = (active_start - m.m1_lo[i]) / a
        ct_end = m.m1_hi[max(0, i - lb) : i + 1].max()
        counter_imp = max(0.0, (ct_end - m.m1_lo[i]) / a)
    else:
        active_imp = active.get("impulse_1m_atr", 0.5)
        counter_imp = abs(active.get("progress_1m_atr", 0.0))

    ratio = counter_imp / active_imp if active_imp > 0.05 else 0.0
    return {
        "countertrend_ratio": float(ratio),
        "active_impulse_atr": float(active_imp),
        "counter_impulse_atr": float(counter_imp),
        "pullback_threshold": cfg.get("countertrend_ratio_pullback", 0.5),
        "reversal_threshold": cfg.get("countertrend_ratio_reversal", 0.85),
    }


def structure_context(struct: dict, active: dict, direction: str) -> dict:
    """Direction-specific structure interpretation."""
    dom = active["dominant_active"]
    if direction == "LONG":
        intact = struct["bull_structure"] or dom in ("STRONG_UP", "UP", "NEUTRAL")
        weakening = struct["failed_up_extension"] or dom in ("STRONG_DOWN", "DOWN")
        opp_str = struct["bear_structure"] or struct["failed_up_extension"]
    else:
        intact = struct["bear_structure"] or dom in ("STRONG_DOWN", "DOWN", "NEUTRAL")
        weakening = struct["failed_down_extension"] or dom in ("STRONG_UP", "UP")
        opp_str = struct["bull_structure"] or struct["failed_down_extension"]
    return {
        "structure_intact": bool(intact),
        "prior_weakening": bool(weakening),
        "opposite_strengthening": bool(opp_str),
    }
