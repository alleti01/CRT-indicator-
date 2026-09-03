"""Pine-equivalent feature computation at bar index i."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from phase72b.python.config import PineConfig, DEFAULT_CFG
from phase72b.python.series_builder import PineSeries


@dataclass
class FeatureSlice:
    """Precomputed per-bar features for autonomous mirror."""

    ctx_dir: np.ndarray
    bull_sc: np.ndarray
    bear_sc: np.ndarray
    ctx15_state: np.ndarray
    ctx15_strength: np.ndarray
    ctx15_score: np.ndarray
    ctx5_dir: np.ndarray
    ctx5_bull: np.ndarray
    ctx5_bear: np.ndarray
    loc_long: np.ndarray
    loc_short: np.ndarray
    react_long: np.ndarray
    react_short: np.ndarray
    ev_total_long: np.ndarray
    ev_total_short: np.ndarray
    ev_react_long: np.ndarray
    ev_react_short: np.ndarray
    ev_contra_long: np.ndarray
    ev_contra_short: np.ndarray
    band_long: np.ndarray
    band_short: np.ndarray
    rev_sup_long: np.ndarray
    rev_sup_short: np.ndarray
    dom_long: np.ndarray
    dom_short: np.ndarray
    high_sub_long: np.ndarray
    high_sub_short: np.ndarray
    htf_contra_long: np.ndarray
    htf_contra_short: np.ndarray


def _classify_progress(prog: float, cfg: PineConfig) -> str:
    if prog >= cfg.strong_progress_atr:
        return "STRONG_UP"
    if prog >= cfg.weak_progress_atr:
        return "UP"
    if prog <= -cfg.strong_progress_atr:
        return "STRONG_DOWN"
    if prog <= -cfg.weak_progress_atr:
        return "DOWN"
    if abs(prog) < cfg.weak_progress_atr * 0.5:
        return "NEUTRAL"
    return "TRANSITION"


def _dominant(s15: str, s5: str, s1: str) -> str:
    if s15 in ("STRONG_UP", "STRONG_DOWN"):
        return s15
    if s5 in ("STRONG_UP", "STRONG_DOWN"):
        return s5
    if s15 in ("UP", "DOWN"):
        return s15
    return s5 if s5 != "NEUTRAL" else s1


def _ctx15_at(s: PineSeries, i: int) -> tuple[str, float, int]:
    if i < 20:
        return "NEUTRAL", 0.0, 0
    bull = bear = 0.0
    if np.isfinite(s.m15_h[i]) and np.isfinite(s.m15_h4[i]):
        if s.m15_h[i] > s.m15_h4[i]:
            bull += 0.5
        elif s.m15_h[i] < s.m15_h4[i]:
            bear += 0.5
    if np.isfinite(s.m15_l[i]) and np.isfinite(s.m15_l4[i]):
        if s.m15_l[i] > s.m15_l4[i]:
            bull += 0.5
        elif s.m15_l[i] < s.m15_l4[i]:
            bear += 0.5
    if np.isfinite(s.m15_c12[i]):
        prog = (s.m15_c[i] - s.m15_c12[i]) / s.m15_atr[i]
        if prog > 0.5:
            bull += 1.0
        elif prog < -0.5:
            bear += 1.0
    impulse = s.imp15m8[i]
    if s.m15_atr[i] > 0 and impulse / s.m15_atr[i] > 2.0:
        if s.m15_c[i] > s.m15_c[i - 8]:
            bull += 0.5
        else:
            bear += 0.5
    rng = impulse
    pos = (s.m15_c[i] - s.rl15m8[i]) / rng if rng > 0 else 0.5
    if pos > 0.7:
        bull += 0.5
    elif pos < 0.3:
        bear += 0.5
    m5_rng = s.m5_h[i] - s.m5_l[i]
    m5_prior = s.m5_range_sma4[i]
    if m5_prior > 0 and m5_rng / m5_prior > 1.3:
        if s.m5_c[i] > s.m5_o[i]:
            bull += 0.5
        else:
            bear += 0.5
    net = bull - bear
    strength = max(-2.0, min(2.0, net))
    if strength >= 1.0:
        state = "BULLISH"
    elif strength <= -1.0:
        state = "BEARISH"
    elif abs(strength) < 0.5 and (bull + bear) > 0:
        state = "TRANSITION"
    else:
        state = "NEUTRAL"
    score = int(round(max(-2.0, min(2.0, strength))))
    return state, strength, score


def _ctx5_at(s: PineSeries, i: int) -> tuple[str, int, int]:
    if i < 20:
        return "NEUTRAL", 0, 0
    bull = bear = 0
    if np.isfinite(s.m5_last_sh[i]) and np.isfinite(s.m5_prev_sh[i]):
        if s.m5_last_sh[i] > s.m5_prev_sh[i]:
            bull += 1
        elif s.m5_last_sh[i] < s.m5_prev_sh[i]:
            bear += 1
    if np.isfinite(s.m5_last_sl[i]) and np.isfinite(s.m5_prev_sl[i]):
        if s.m5_last_sl[i] > s.m5_prev_sl[i]:
            bull += 1
        elif s.m5_last_sl[i] < s.m5_prev_sl[i]:
            bear += 1
    mom5 = (s.m5_c[i] - s.m5_c[i - 5]) / s.m5_atr[i]
    if mom5 > 0.3:
        bull += 1
    elif mom5 < -0.3:
        bear += 1
    net = bull - bear
    d = "BULLISH" if net >= 2 else "BEARISH" if net <= -2 else "NEUTRAL"
    return d, bull, bear


def _compute_context(s: PineSeries, i: int) -> tuple[str, int, int]:
    if i < 20:
        return "NEUTRAL", 0, 0
    bull = bear = 0
    if np.isfinite(s.sh_at_i[i]) and np.isfinite(s.sh_at_i10[i]):
        if s.sh_at_i[i] > s.sh_at_i10[i]:
            bull += 1
        elif s.sh_at_i[i] < s.sh_at_i10[i]:
            bear += 1
    if np.isfinite(s.sl_at_i[i]) and np.isfinite(s.sl_at_i10[i]):
        if s.sl_at_i[i] > s.sl_at_i10[i]:
            bull += 1
        elif s.sl_at_i[i] < s.sl_at_i10[i]:
            bear += 1
    mom = (s.cl[i] - s.cl[i - 5]) / s.atr_use[i]
    if mom > 0.3:
        bull += 1
    elif mom < -0.3:
        bear += 1
    m5_body = (s.m5_c[i] - s.m5_o[i]) / s.m5_atr[i]
    if m5_body > 0.2:
        bull += 1
    elif m5_body < -0.2:
        bear += 1
    if i > 15:
        m15_mom = (s.m15_c[i] - s.m15_c[i - 15]) / s.m15_atr[i]
        if m15_mom > 0.3:
            bull += 1
        elif m15_mom < -0.3:
            bear += 1
    net = bull - bear
    d = "BULLISH" if net >= 2 else "BEARISH" if net <= -2 else "NEUTRAL"
    return d, bull, bear


def _loc1m(s: PineSeries, i: int, direction: str) -> int:
    if i < 30:
        return 0
    sc = 0
    if direction == "LONG" and np.isfinite(s.sl_at_i[i]):
        if abs(s.cl[i] - s.sl_at_i[i]) / s.atr_use[i] < 0.5:
            sc += 1
    if direction == "SHORT" and np.isfinite(s.sh_at_i[i]):
        if abs(s.cl[i] - s.sh_at_i[i]) / s.atr_use[i] < 0.5:
            sc += 1
    imp = s.imp1m20[i]
    if imp > 0:
        pb = (s.rh1m20[i] - s.cl[i]) / imp if direction == "LONG" else (s.cl[i] - s.rl1m20[i]) / imp
        if 0.15 <= pb <= 0.6:
            sc += 1
        rng_pos = (s.cl[i] - s.rl1m20[i]) / imp
        if direction == "LONG" and rng_pos < 0.35:
            sc += 1
        if direction == "SHORT" and rng_pos > 0.65:
            sc += 1
    return sc


def _loc5m(s: PineSeries, i: int, direction: str) -> int:
    if i < 30:
        return 0
    sc = 0
    prox = 0.5
    if direction == "LONG" and np.isfinite(s.m5_last_sl[i]):
        if abs(s.m5_c[i] - s.m5_last_sl[i]) / s.m5_atr[i] < prox:
            sc += 1
    if direction == "SHORT" and np.isfinite(s.m5_last_sh[i]):
        if abs(s.m5_c[i] - s.m5_last_sh[i]) / s.m5_atr[i] < prox:
            sc += 1
    imp = s.imp5m20[i]
    if imp > 0:
        pb = (s.rh5m20[i] - s.m5_c[i]) / imp if direction == "LONG" else (s.m5_c[i] - s.rl5m20[i]) / imp
        if 0.15 <= pb <= 0.6:
            sc += 1
    if direction == "LONG" and np.isfinite(s.m15_l[i]):
        if abs(s.m5_c[i] - s.m15_l[i]) / s.m5_atr[i] < prox * 1.5:
            sc += 1
    if direction == "SHORT" and np.isfinite(s.m15_h[i]):
        if abs(s.m5_c[i] - s.m15_h[i]) / s.m5_atr[i] < prox * 1.5:
            sc += 1
    return min(sc, 2)


def _location(s: PineSeries, i: int, direction: str) -> int:
    return min(3, _loc1m(s, i, direction) + _loc5m(s, i, direction))


def _reactions(s: PineSeries, i: int, direction: str, cfg: PineConfig) -> int:
    if i < 4:
        return 0
    sc = 0
    if direction == "LONG":
        new_ext = s.lo[i] < s.lo[i - 1]
        prog = (s.lo[i - 1] - s.lo[i]) / s.atr_use[i] if new_ext else 0.0
        if new_ext and prog < 0.15 and s.cl[i] > s.cl[i - 1]:
            sc += 1
    else:
        new_ext = s.hi[i] > s.hi[i - 1]
        prog = (s.hi[i] - s.hi[i - 1]) / s.atr_use[i] if new_ext else 0.0
        if new_ext and prog < 0.15 and s.cl[i] < s.cl[i - 1]:
            sc += 1
    dl = cfg.decel_lookback
    if i >= dl + 1:
        if direction == "LONG":
            m0 = abs(s.cl[i - 1] - s.cl[i - 2])
            m1 = abs(s.cl[i - 2] - s.cl[i - 3])
            sell0 = m0 if s.cl[i - 1] < s.cl[i - 2] else 0.0
            sell1 = m1 if s.cl[i - 2] < s.cl[i - 3] else 0.0
            if sell0 > 0 and sell1 > 0 and sell0 < sell1 * 0.7:
                sc += 1
        else:
            m0 = abs(s.cl[i - 1] - s.cl[i - 2])
            m1 = abs(s.cl[i - 2] - s.cl[i - 3])
            buy0 = m0 if s.cl[i - 1] > s.cl[i - 2] else 0.0
            buy1 = m1 if s.cl[i - 2] > s.cl[i - 3] else 0.0
            if buy0 > 0 and buy1 > 0 and buy0 < buy1 * 0.7:
                sc += 1
    prior = s.cl[i - 2]
    if direction == "LONG":
        if s.cl[i] > prior and s.cl[i - 1] < prior:
            sc += 1
    else:
        if s.cl[i] < prior and s.cl[i - 1] > prior:
            sc += 1
    body = s.cl[i] - s.op[i]
    abs_body = abs(body) / s.atr_use[i]
    if direction == "LONG":
        if body > 0 and abs_body >= cfg.body_thresh_atr:
            sc += 1
    else:
        if body < 0 and abs_body >= cfg.body_thresh_atr:
            sc += 1
    ms = cfg.micro_shift_bars
    if i >= ms:
        if direction == "LONG":
            if s.cl[i] > s.cl[i - 1] > s.cl[i - 2]:
                sc += 1
        else:
            if s.cl[i] < s.cl[i - 1] < s.cl[i - 2]:
                sc += 1
    br = s.hi[i] - s.lo[i]
    if br > 0:
        if direction == "LONG":
            lw = min(s.cl[i], s.op[i]) - s.lo[i]
            if lw / br >= cfg.wick_rejection_pct and s.cl[i] > s.op[i]:
                sc += 1
        else:
            uw = s.hi[i] - max(s.cl[i], s.op[i])
            if uw / br >= cfg.wick_rejection_pct and s.cl[i] < s.op[i]:
                sc += 1
    return min(sc, 3)


def _score15m(score: int, direction: str) -> int:
    if direction == "LONG":
        if score > 0:
            return min(2, score)
        if score < -1:
            return max(-2, score)
        return 0
    if score < 0:
        return min(2, abs(score))
    if score > 1:
        return max(-2, -score)
    return 0


def _evidence(
    s: PineSeries,
    i: int,
    direction: str,
    ctx15_state: str,
    ctx15_strength: float,
    ctx5_dir: str,
    ctx5_bull: int,
    ctx5_bear: int,
    cfg: PineConfig,
) -> tuple[int, int, int]:
    loc = _location(s, i, direction)
    c15 = _score15m(int(round(max(-2, min(2, ctx15_strength)))), direction)
    dir5 = min(2, ctx5_bull if direction == "LONG" else ctx5_bear)
    react = _reactions(s, i, direction, cfg)
    contra = 0
    if direction == "LONG" and ctx15_state == "BEARISH" and ctx15_strength <= -1.0:
        contra -= 1
    if direction == "SHORT" and ctx15_state == "BULLISH" and ctx15_strength >= 1.0:
        contra -= 1
    if direction == "LONG" and ctx5_dir == "BEARISH" and ctx5_bear >= 2:
        contra -= 1
    if direction == "SHORT" and ctx5_dir == "BULLISH" and ctx5_bull >= 2:
        contra -= 1
    total = loc + c15 + dir5 + react + contra
    return total, react, contra


def _confidence(
    s: PineSeries,
    i: int,
    direction: str,
    ctx15_state: str,
    ctx15_strength: float,
    cfg: PineConfig,
) -> tuple[str, str, str, str, bool]:
    """Returns band, rev_sup, dom, high_sub, htf_contra_code."""
    p1 = (s.cl[i] - s.cl[i - cfg.progress_lb_1m]) / s.atr_use[i] if i >= cfg.progress_lb_1m else 0.0
    p5 = (s.m5_c[i] - s.m5_c[i - cfg.progress_lb_5m]) / s.m5_atr[i]
    p15 = (s.m15_c[i] - s.m15_c[i - cfg.progress_lb_15m]) / s.m15_atr[i]
    s1 = _classify_progress(p1, cfg)
    s5 = _classify_progress(p5, cfg)
    s15 = _classify_progress(p15, cfg)
    dom = _dominant(s15, s5, s1)
    hh = np.isfinite(s.sh_at_i[i]) and np.isfinite(s.sh_at_i10[i]) and s.sh_at_i[i] > s.sh_at_i10[i]
    hl = np.isfinite(s.sl_at_i[i]) and np.isfinite(s.sl_at_i10[i]) and s.sl_at_i[i] > s.sl_at_i10[i]
    lh = np.isfinite(s.sh_at_i[i]) and np.isfinite(s.sh_at_i10[i]) and s.sh_at_i[i] < s.sh_at_i10[i]
    ll = np.isfinite(s.sl_at_i[i]) and np.isfinite(s.sl_at_i10[i]) and s.sl_at_i[i] < s.sl_at_i10[i]
    struct_intact = hh or hl if direction == "LONG" else lh or ll
    dom_bull = dom in ("STRONG_UP", "UP")
    dom_bear = dom in ("STRONG_DOWN", "DOWN")
    aligned = (direction == "LONG" and dom_bull) or (direction == "SHORT" and dom_bear)
    score = 0
    htf_contra = False
    if direction == "LONG":
        if ctx15_state == "BEARISH" and ctx15_strength <= -1.0:
            htf_contra = True
    else:
        if ctx15_state == "BULLISH" and ctx15_strength >= 1.0:
            htf_contra = True
    if aligned and struct_intact:
        score += 3
    elif not aligned:
        score -= 1
    if direction == "LONG" and ctx15_state == "BULLISH":
        score += 1
    elif direction == "SHORT" and ctx15_state == "BEARISH":
        score += 1
    elif htf_contra:
        score -= 1
    band = "HIGH" if score >= 4 else "MEDIUM" if score >= 2 else "LOW"
    rev_sup = "NONE"
    high_sub = ""
    if band == "HIGH":
        high_sub = "HIGH_CLEAN" if not htf_contra else "HIGH_CONFLICTED"
    return band, rev_sup, dom, high_sub, htf_contra


def decide_e(total: int, react: int, contra: int, wait_used: int, cfg: PineConfig) -> str:
    if total >= cfg.take_threshold:
        return "TAKE"
    if react >= 1 and total >= cfg.take_threshold - 1:
        return "WAIT" if wait_used < cfg.max_wait_bars else "TAKE"
    if total <= 1 or contra <= -2:
        return "PASS"
    if wait_used < cfg.max_wait_bars:
        return "WAIT"
    return "PASS"


def p4_abstain(direction: str, rev_sup: str, dom: str, ctx15_state: str) -> bool:
    strong_contra = (
        (direction == "LONG" and ctx15_state == "BEARISH" and dom in ("DOWN", "STRONG_DOWN"))
        or (direction == "SHORT" and ctx15_state == "BULLISH" and dom in ("UP", "STRONG_UP"))
    )
    weak_rev = rev_sup in ("NONE", "WEAK")
    return strong_contra and weak_rev


def h1_abstain(high_sub: str, htf_contra: bool) -> bool:
    return high_sub == "HIGH_CONFLICTED" and htf_contra


def precompute_features(
    s: PineSeries,
    start_i: int,
    end_i: int,
    cfg: PineConfig = DEFAULT_CFG,
) -> FeatureSlice:
    n = end_i - start_i
    sl = slice(start_i, end_i)

    def arr(dtype=str):
        if dtype is str:
            return np.empty(n, dtype=object)
        return np.zeros(n, dtype=dtype)

    out = FeatureSlice(
        ctx_dir=arr(str),
        bull_sc=np.zeros(n, dtype=int),
        bear_sc=np.zeros(n, dtype=int),
        ctx15_state=arr(str),
        ctx15_strength=np.zeros(n),
        ctx15_score=np.zeros(n, dtype=int),
        ctx5_dir=arr(str),
        ctx5_bull=np.zeros(n, dtype=int),
        ctx5_bear=np.zeros(n, dtype=int),
        loc_long=np.zeros(n, dtype=int),
        loc_short=np.zeros(n, dtype=int),
        react_long=np.zeros(n, dtype=int),
        react_short=np.zeros(n, dtype=int),
        ev_total_long=np.zeros(n, dtype=int),
        ev_total_short=np.zeros(n, dtype=int),
        ev_react_long=np.zeros(n, dtype=int),
        ev_react_short=np.zeros(n, dtype=int),
        ev_contra_long=np.zeros(n, dtype=int),
        ev_contra_short=np.zeros(n, dtype=int),
        band_long=arr(str),
        band_short=arr(str),
        rev_sup_long=arr(str),
        rev_sup_short=arr(str),
        dom_long=arr(str),
        dom_short=arr(str),
        high_sub_long=arr(str),
        high_sub_short=arr(str),
        htf_contra_long=np.zeros(n, dtype=bool),
        htf_contra_short=np.zeros(n, dtype=bool),
    )

    for k, i in enumerate(range(start_i, end_i)):
        ctx, bull, bear = _compute_context(s, i)
        c15_st, c15_str, c15_sc = _ctx15_at(s, i)
        c5, c5b, c5r = _ctx5_at(s, i)
        out.ctx_dir[k] = ctx
        out.bull_sc[k] = bull
        out.bear_sc[k] = bear
        out.ctx15_state[k] = c15_st
        out.ctx15_strength[k] = c15_str
        out.ctx15_score[k] = c15_sc
        out.ctx5_dir[k] = c5
        out.ctx5_bull[k] = c5b
        out.ctx5_bear[k] = c5r
        out.loc_long[k] = _location(s, i, "LONG")
        out.loc_short[k] = _location(s, i, "SHORT")
        out.react_long[k] = _reactions(s, i, "LONG", cfg)
        out.react_short[k] = _reactions(s, i, "SHORT", cfg)
        etl, erl, ecl = _evidence(s, i, "LONG", c15_st, c15_str, c5, c5b, c5r, cfg)
        ets, ers, ecs = _evidence(s, i, "SHORT", c15_st, c15_str, c5, c5b, c5r, cfg)
        out.ev_total_long[k] = etl
        out.ev_total_short[k] = ets
        out.ev_react_long[k] = erl
        out.ev_react_short[k] = ers
        out.ev_contra_long[k] = ecl
        out.ev_contra_short[k] = ecs
        bl, rl, dl, hsl, hcl = _confidence(s, i, "LONG", c15_st, c15_str, cfg)
        bs, rs, ds, hss, hcs = _confidence(s, i, "SHORT", c15_st, c15_str, cfg)
        out.band_long[k] = bl
        out.band_short[k] = bs
        out.rev_sup_long[k] = rl
        out.rev_sup_short[k] = rs
        out.dom_long[k] = dl
        out.dom_short[k] = ds
        out.high_sub_long[k] = hsl
        out.high_sub_short[k] = hss
        out.htf_contra_long[k] = hcl
        out.htf_contra_short[k] = hcs

    return out
