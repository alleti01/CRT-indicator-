"""Sequential Phase72A autonomous trader mirror — Pine bar loop order."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from phase72b.python.config import PineConfig, DEFAULT_CFG
from phase72b.python.pine_features import (
    FeatureSlice,
    decide_e,
    h1_abstain,
    p4_abstain,
    precompute_features,
)
from phase72b.python.series_builder import PineSeries, build_pine_series


@dataclass
class MirrorState:
    p58_state: int = 0
    p58_dir: str = ""
    armed_bar: int = 0
    armed_bars: int = 0
    armed_price: float = np.nan
    pb_extreme: float = np.nan
    cooldown_rem: int = 0
    p58_in_trade: bool = False
    p58_trade_dir: str = ""
    p58_entry_bar: int = -1
    p58_entry: float = np.nan
    p58_stop: float = np.nan
    p58_target: float = np.nan
    p58_deadline: int = -1
    p58_signal_atr: float = np.nan
    p58_skip_cooldown_dec: bool = False
    p58_block_signals: bool = False
    cur_opp_id: str = ""
    cur_opp_dir: str = ""
    cur_opp_last_si: int = -1
    pending_take: bool = False
    pending_dir: str = ""
    pending_signal_bar: int = -1
    pos_state: str = "FLAT"
    entry_px: float = np.nan
    init_atr: float = np.nan
    stop_px: float = np.nan
    tgt_px: float = np.nan
    entry_bar: int = -1
    signal_bar: int = -1
    pos_dir: int = 0
    run_mfe_r: float = 0.0
    t5_checked: bool = False
    skipped_signals: int = 0


def _pos_active(st: MirrorState) -> bool:
    return st.pos_state in ("LONG_ACTIVE", "SHORT_ACTIVE", "PENDING_LONG", "PENDING_SHORT")


def _state_label(st: MirrorState) -> str:
    """Mirror Pine f_p72bStateLbl() — pos active first, then p58 states."""
    if st.pos_state != "FLAT":
        return st.pos_state
    if st.p58_state == 3:
        return "COOLDOWN"
    if st.p58_state == 0:
        return "WATCH"
    if st.p58_state in (1, -1):
        return f"ARMED_{st.p58_dir}"
    if st.p58_state in (2, -2):
        d = st.p58_trade_dir if st.p58_in_trade else st.p58_dir
        return f"IN_{d}" if d else f"IN_{st.p58_dir}"
    return str(st.p58_state)


@dataclass
class EventRow:
    timestamp: pd.Timestamp
    bar_index: int
    open: float
    high: float
    low: float
    close: float
    atr: float
    state_before: str
    state_after: str
    signal_long: bool
    signal_short: bool
    enter_long: bool
    enter_short: bool
    entry_price: float
    in_trade: bool
    trade_direction: str
    stop_price: float
    target_price: float
    exit_stop: bool
    exit_target: bool
    exit_time: bool
    reason_code: str
    p58_state: int = 0
    ctx_dir: str = ""
    ev_total_long: int = 0
    ev_total_short: int = 0
    # Forensic / manual parity (observational — does not affect FSM)
    raw_long: bool = False
    raw_short: bool = False
    take_long: bool = False
    take_short: bool = False
    ctx_score_long: int = 0
    ctx_score_short: int = 0
    loc_long: int = 0
    loc_short: int = 0
    react_long: int = 0
    react_short: int = 0
    contra_long: int = 0
    contra_short: int = 0
    armed_direction: str = ""
    cooldown: bool = False
    cooldown_rem: int = 0
    gate_open: bool = False
    p4_result: str = ""
    h1_result: str = ""
    decision: str = ""
    band_long: str = ""
    band_short: str = ""
    dom_long: str = ""
    dom_short: str = ""
    known_at: str = ""


class AutonomousMirrorEngine:
    """Bar-by-bar mirror of phase72a_autonomous_trader.pine Layer A."""

    def __init__(
        self,
        series: PineSeries,
        features: FeatureSlice,
        start_i: int,
        cfg: PineConfig = DEFAULT_CFG,
        global_offset: int = 0,
    ):
        self.s = series
        self.f = features
        self.start_i = start_i
        self.global_offset = global_offset
        self.cfg = cfg
        self.st = MirrorState()
        self.events: list[EventRow] = []
        self.run_end_i: int = len(series.cl)

    def _feat(self, i: int) -> int:
        return i - self.start_i

    def on_bar(self, i: int) -> EventRow:
        s, f, st, cfg = self.s, self.f, self.st, self.cfg
        k = self._feat(i)
        state_before = _state_label(st)

        signal_long = signal_short = enter_long = enter_short = False
        exit_stop = exit_target = exit_time = False
        reason = ""
        entry_price = np.nan
        trade_dir = ""
        in_trade = _pos_active(st) or st.p58_in_trade

        if i >= cfg.warmup and i < self.run_end_i:
            if st.p58_in_trade and st.p58_state in (1, -1):
                st.p58_state = 2 if st.p58_trade_dir == "LONG" else -2

            if st.p58_in_trade and i == st.p58_entry_bar:
                st.p58_entry = s.cl[i]
                risk58 = cfg.p58_stop_atr * st.p58_signal_atr
                if st.p58_trade_dir == "LONG":
                    st.p58_stop = st.p58_entry - risk58
                    st.p58_target = st.p58_entry + cfg.target_r * risk58
                else:
                    st.p58_stop = st.p58_entry + risk58
                    st.p58_target = st.p58_entry - cfg.target_r * risk58

            if st.pending_take and i == st.pending_signal_bar + 1 and st.pos_state == "FLAT":
                st.entry_px = s.op[i]
                st.init_atr = s.atr_use[i]
                st.entry_bar = i
                st.signal_bar = st.pending_signal_bar
                st.pos_dir = 1 if st.pending_dir == "LONG" else -1
                risk = cfg.m1_stop_atr * st.init_atr
                if st.pos_dir == 1:
                    st.stop_px = st.entry_px - risk
                    st.tgt_px = st.entry_px + cfg.target_r * risk
                    enter_long = True
                    trade_dir = "LONG"
                else:
                    st.stop_px = st.entry_px + risk
                    st.tgt_px = st.entry_px - cfg.target_r * risk
                    enter_short = True
                    trade_dir = "SHORT"
                st.run_mfe_r = 0.0
                st.t5_checked = False
                st.pos_state = "LONG_ACTIVE" if st.pos_dir == 1 else "SHORT_ACTIVE"
                reason = "ENTER"
                entry_price = st.entry_px
                st.pending_take = False
                st.pending_dir = ""
                st.pending_signal_bar = -1

            if st.pos_state in ("LONG_ACTIVE", "SHORT_ACTIVE"):
                mins = i - st.entry_bar
                risk = cfg.m1_stop_atr * st.init_atr
                hit_stop = s.lo[i] <= st.stop_px if st.pos_dir == 1 else s.hi[i] >= st.stop_px
                hit_tgt = s.hi[i] >= st.tgt_px if st.pos_dir == 1 else s.lo[i] <= st.tgt_px
                exited = False
                if hit_stop and hit_tgt:
                    exited = True
                    exit_stop = True
                    reason = "M0_STOP"
                elif hit_stop:
                    exited = True
                    exit_stop = True
                    reason = "M0_STOP"
                elif hit_tgt:
                    exited = True
                    exit_target = True
                    reason = "M0_TARGET"
                if not exited:
                    fav = (
                        (s.hi[i] - st.entry_px) / risk
                        if st.pos_dir == 1
                        else (st.entry_px - s.lo[i]) / risk
                    )
                    st.run_mfe_r = max(st.run_mfe_r, fav)
                    if cfg.enable_t5 and not st.t5_checked and mins >= cfg.t5_bars:
                        st.t5_checked = True
                        if st.run_mfe_r < cfg.t5_mfe_r:
                            exited = True
                            exit_time = True
                            reason = "T5_NO_PROGRESS"
                    if not exited and mins >= cfg.max_hold_bars:
                        exited = True
                        exit_time = True
                        reason = "MAX_HOLD_60M"
                if exited:
                    st.pos_state = "FLAT"
                    st.entry_px = np.nan
                    st.run_mfe_r = 0.0
                    st.t5_checked = False
                    st.pos_dir = 0

            if st.p58_in_trade and i > st.p58_entry_bar:
                d = st.p58_trade_dir
                hit_stop = s.lo[i] <= st.p58_stop if d == "LONG" else s.hi[i] >= st.p58_stop
                hit_tgt = s.hi[i] >= st.p58_target if d == "LONG" else s.lo[i] <= st.p58_target
                if hit_stop or hit_tgt or i >= st.p58_deadline:
                    st.p58_in_trade = False
                    st.p58_state = 3
                    st.cooldown_rem = cfg.cooldown_bars
                    st.p58_trade_dir = ""
                    st.p58_dir = ""
                    st.p58_skip_cooldown_dec = True

            if st.p58_state == 3 and not st.p58_in_trade:
                if not st.p58_skip_cooldown_dec:
                    st.cooldown_rem -= 1
                st.p58_skip_cooldown_dec = False
                if st.cooldown_rem <= 0:
                    st.p58_state = 0
                    st.p58_dir = ""
                    st.armed_bar = 0
                    st.armed_bars = 0
                    st.armed_price = np.nan
                    st.pb_extreme = np.nan
                    st.p58_block_signals = True

            if not _pos_active(st) and not st.p58_in_trade and st.p58_state != 3 and not st.p58_block_signals:
                ctx_dir = f.ctx_dir[k]
                if st.p58_state == 0:
                    trade_dir = "LONG" if ctx_dir == "BULLISH" else "SHORT" if ctx_dir == "BEARISH" else ""
                    if trade_dir:
                        loc_sc = f.loc_long[k] if trade_dir == "LONG" else f.loc_short[k]
                        ctx_sc = min(2, f.bull_sc[k] if trade_dir == "LONG" else f.bear_sc[k])
                        if ctx_sc + loc_sc >= cfg.armed_min_score:
                            st.p58_state = 1 if trade_dir == "LONG" else -1
                            st.p58_dir = trade_dir
                            st.armed_bar = i
                            st.armed_bars = 0
                            st.armed_price = s.cl[i]
                            st.pb_extreme = s.cl[i]

                if st.p58_state in (1, -1):
                    st.armed_bars += 1
                    dir_str = st.p58_dir
                    if dir_str == "LONG":
                        st.pb_extreme = min(st.pb_extreme, s.lo[i])
                    else:
                        st.pb_extreme = max(st.pb_extreme, s.hi[i])

                    if st.armed_bars > cfg.armed_timeout_bars:
                        st.p58_state = 0
                        st.p58_dir = ""
                        st.armed_bar = 0
                        st.armed_bars = 0
                        st.armed_price = np.nan
                        st.pb_extreme = np.nan
                    elif (dir_str == "LONG" and ctx_dir == "BEARISH") or (
                        dir_str == "SHORT" and ctx_dir == "BULLISH"
                    ):
                        st.p58_state = 0
                        st.p58_dir = ""
                        st.armed_bar = 0
                        st.armed_bars = 0
                        st.armed_price = np.nan
                        st.pb_extreme = np.nan
                    else:
                        react_sc = f.react_long[k] if dir_str == "LONG" else f.react_short[k]
                        loc_sc = f.loc_long[k] if dir_str == "LONG" else f.loc_short[k]
                        ctx_sc = min(2, f.bull_sc[k] if dir_str == "LONG" else f.bear_sc[k])
                        contra = 0
                        if dir_str == "LONG" and ctx_dir == "NEUTRAL" and f.bear_sc[k] >= 2:
                            contra -= 1
                        if dir_str == "SHORT" and ctx_dir == "NEUTRAL" and f.bull_sc[k] >= 2:
                            contra -= 1
                        total = ctx_sc + loc_sc + react_sc + contra
                        deterioration = (
                            (s.cl[i] - st.armed_price) / s.atr_use[i]
                            if dir_str == "LONG"
                            else (st.armed_price - s.cl[i]) / s.atr_use[i]
                        )
                        if deterioration > cfg.max_chase_atr and react_sc >= 1:
                            st.p58_state = 0
                            st.p58_dir = ""
                            st.armed_bar = 0
                            st.armed_bars = 0
                            st.armed_price = np.nan
                            st.pb_extreme = np.nan
                        elif total >= cfg.take_threshold:
                            is_new = (
                                not st.cur_opp_id
                                or dir_str != st.cur_opp_dir
                                or (i - st.cur_opp_last_si) > cfg.struct_gap
                            )
                            if is_new:
                                st.cur_opp_id = f"OPP_{i}_{dir_str}"
                                st.cur_opp_dir = dir_str
                                st.cur_opp_last_si = i
                                ev_total = f.ev_total_long[k] if dir_str == "LONG" else f.ev_total_short[k]
                                ev_react = f.ev_react_long[k] if dir_str == "LONG" else f.ev_react_short[k]
                                ev_contra = f.ev_contra_long[k] if dir_str == "LONG" else f.ev_contra_short[k]
                                dec_e = decide_e(ev_total, ev_react, ev_contra, 0, cfg)
                                if dec_e == "TAKE":
                                    band = f.band_long[k] if dir_str == "LONG" else f.band_short[k]
                                    rev_sup = f.rev_sup_long[k] if dir_str == "LONG" else f.rev_sup_short[k]
                                    dom = f.dom_long[k] if dir_str == "LONG" else f.dom_short[k]
                                    high_sub = f.high_sub_long[k] if dir_str == "LONG" else f.high_sub_short[k]
                                    htf_c = f.htf_contra_long[k] if dir_str == "LONG" else f.htf_contra_short[k]
                                    ctx15 = f.ctx15_state[k]
                                    p4_ab = p4_abstain(dir_str, rev_sup, dom, ctx15)
                                    h1_ab = h1_abstain(high_sub, htf_c)
                                    if not p4_ab and not h1_ab and not _pos_active(st):
                                        st.pending_take = True
                                        st.pending_dir = dir_str
                                        st.pending_signal_bar = i
                                        if dir_str == "LONG":
                                            signal_long = True
                                        else:
                                            signal_short = True
                                        reason = "SIGNAL"
                                        st.p58_in_trade = True
                                        st.p58_trade_dir = dir_str
                                        st.p58_entry_bar = i + 1
                                        st.p58_signal_atr = s.atr_use[i]
                                        st.p58_entry = np.nan
                                        st.p58_stop = np.nan
                                        st.p58_target = np.nan
                                        st.p58_deadline = i + 1 + cfg.max_hold_bars
                                        st.p58_state = 2 if dir_str == "LONG" else -2
                                        st.armed_bar = 0
                                        st.armed_bars = 0
                                        st.armed_price = np.nan
                                        st.pb_extreme = np.nan
                            else:
                                st.cur_opp_last_si = i

            if st.p58_block_signals:
                st.p58_block_signals = False

        in_trade = _pos_active(st) or st.p58_in_trade
        if not trade_dir and st.pos_state in ("LONG_ACTIVE", "SHORT_ACTIVE"):
            trade_dir = "LONG" if st.pos_dir == 1 else "SHORT"
        stop_p = st.stop_px if _pos_active(st) else np.nan
        tgt_p = st.tgt_px if _pos_active(st) else np.nan

        def _arm_total(direction: str) -> tuple[int, int, int, int, int]:
            if k < 0 or k >= len(f.ctx_dir):
                return 0, 0, 0, 0, 0
            react = f.react_long[k] if direction == "LONG" else f.react_short[k]
            loc = f.loc_long[k] if direction == "LONG" else f.loc_short[k]
            ctx_sc = min(2, f.bull_sc[k] if direction == "LONG" else f.bear_sc[k])
            contra = 0
            if direction == "LONG" and f.ctx_dir[k] == "NEUTRAL" and f.bear_sc[k] >= 2:
                contra -= 1
            if direction == "SHORT" and f.ctx_dir[k] == "NEUTRAL" and f.bull_sc[k] >= 2:
                contra -= 1
            return ctx_sc + loc + react + contra, ctx_sc, loc, react, contra

        tot_l, csl, ll, rl, cl = _arm_total("LONG")
        tot_s, css, ls, rs, cs = _arm_total("SHORT")
        raw_l = st.p58_state == 1 and tot_l >= cfg.take_threshold
        raw_s = st.p58_state == -1 and tot_s >= cfg.take_threshold
        gate_open = (
            not _pos_active(st) and not st.p58_in_trade and st.p58_state != 3 and not st.p58_block_signals
        )
        ts = s.idx[i]

        row = EventRow(
            timestamp=s.idx[i],
            bar_index=i + self.global_offset,
            open=float(s.op[i]),
            high=float(s.hi[i]),
            low=float(s.lo[i]),
            close=float(s.cl[i]),
            atr=float(s.atr_use[i]),
            state_before=state_before,
            state_after=_state_label(st),
            signal_long=signal_long,
            signal_short=signal_short,
            enter_long=enter_long,
            enter_short=enter_short,
            entry_price=float(entry_price) if np.isfinite(entry_price) else np.nan,
            in_trade=in_trade,
            trade_direction=trade_dir,
            stop_price=float(stop_p) if np.isfinite(stop_p) else np.nan,
            target_price=float(tgt_p) if np.isfinite(tgt_p) else np.nan,
            exit_stop=exit_stop,
            exit_target=exit_target,
            exit_time=exit_time,
            reason_code=reason,
            p58_state=st.p58_state,
            ctx_dir=f.ctx_dir[k] if 0 <= k < len(f.ctx_dir) else "",
            ev_total_long=int(f.ev_total_long[k]) if 0 <= k < len(f.ev_total_long) else 0,
            ev_total_short=int(f.ev_total_short[k]) if 0 <= k < len(f.ev_total_short) else 0,
            raw_long=raw_l,
            raw_short=raw_s,
            take_long=signal_long,
            take_short=signal_short,
            ctx_score_long=csl,
            ctx_score_short=css,
            loc_long=ll,
            loc_short=ls,
            react_long=rl,
            react_short=rs,
            contra_long=cl,
            contra_short=cs,
            armed_direction=st.p58_dir,
            cooldown=st.p58_state == 3,
            cooldown_rem=st.cooldown_rem,
            gate_open=gate_open,
            p4_result="KEEP",  # populated on signal bars in trace from features if needed
            h1_result="KEEP",
            decision="",
            band_long=str(f.band_long[k]) if 0 <= k < len(f.band_long) else "",
            band_short=str(f.band_short[k]) if 0 <= k < len(f.band_short) else "",
            dom_long=str(f.dom_long[k]) if 0 <= k < len(f.dom_long) else "",
            dom_short=str(f.dom_short[k]) if 0 <= k < len(f.dom_short) else "",
            known_at=str(ts),
        )
        self.events.append(row)
        return row

    def run(self, end_i: int | None = None) -> list[EventRow]:
        e = end_i if end_i is not None else max(self.start_i, len(self.s.cl) - 61)
        self.run_end_i = e
        for i in range(self.start_i, e):
            self.on_bar(i)
        return self.events


def run_mirror(
    m1: pd.DataFrame,
    m5: pd.DataFrame,
    m15: pd.DataFrame,
    start_i: int | None = None,
    end_i: int | None = None,
    cfg: PineConfig = DEFAULT_CFG,
    pad_bars: int = 3000,
) -> tuple[PineSeries, list[EventRow], int, int]:
    s = start_i if start_i is not None else cfg.warmup
    e = end_i if end_i is not None else len(m1) - 61
    i0 = max(0, s - pad_bars)
    m1s = m1.iloc[i0:e]
    series = build_pine_series(m1s, m5, m15, cfg)
    feat_start = s - i0
    feat_end = e - i0
    features = precompute_features(series, feat_start, feat_end, cfg)
    eng = AutonomousMirrorEngine(series, features, feat_start, cfg, global_offset=i0)
    return series, eng.run(feat_end), s, e
