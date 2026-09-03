#!/usr/bin/env python3
"""FSM forensic trace — every gate boolean around a target bar."""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58j.research.lw_data import load_markets_lw
from phase72b.python.autonomous_mirror_engine import (
    AutonomousMirrorEngine,
    MirrorState,
    _pos_active,
    _state_label,
)
from phase72b.python.config import DEFAULT_CFG
from phase72b.python.pine_features import decide_e, h1_abstain, p4_abstain, precompute_features
from phase72b.python.series_builder import build_pine_series
from phase72b.tools.trace_timestamp import mirror_fsm_start


@dataclass
class ForensicRow:
    timestamp: str
    bar_index: int
    state_before: str
    state_after: str
    p58_state: int
    armed_direction: str
    in_trade: bool
    trade_direction: str
    p58_in_trade: bool
    p58_trade_dir: str
    raw_short: bool
    raw_long: bool
    signal_short: bool
    signal_long: bool
    take_short: bool
    take_long: bool
    cooldown: bool
    cooldown_rem: int
    cooldown_block: bool
    gate_open: bool
    already_in_trade_block: bool
    armed_state_block: bool
    pos_active_block: bool
    p58_block_signals: bool
    total_short: int
    total_long: int
    take_threshold_hit: bool
    is_new_opp: bool
    cur_opp_id: str
    cur_opp_last_si: int
    bars_since_opp: int
    struct_gap: int
    decide_e: str
    p4_abstain: bool
    h1_abstain: bool
    p4_result: str
    h1_result: str
    band_short: str
    rev_sup_short: str
    dom_short: str
    high_sub_short: str
    htf_contra_short: bool
    ev_total_short: int
    pending_take: bool
    pending_dir: str
    pending_signal_bar: int
    entry_pending: bool
    entry_fired: bool
    exit_on_same_bar: bool
    prev_exit: bool
    branch: str
    all_take_conds: dict = field(default_factory=dict)


class ForensicEngine(AutonomousMirrorEngine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fsm_rows: list[ForensicRow] = []

    def on_bar(self, i: int):
        s, f, st, cfg = self.s, self.f, self.st, self.cfg
        k = self._feat(i)
        state_before = _state_label(st)
        prev_p58_in_trade = st.p58_in_trade
        prev_pos = st.pos_state

        row_meta = ForensicRow(
            timestamp=str(s.idx[i]),
            bar_index=i + self.global_offset,
            state_before=state_before,
            state_after="",
            p58_state=st.p58_state,
            armed_direction=st.p58_dir,
            in_trade=False,
            trade_direction="",
            p58_in_trade=st.p58_in_trade,
            p58_trade_dir=st.p58_trade_dir,
            raw_short=False,
            raw_long=False,
            signal_short=False,
            signal_long=False,
            take_short=False,
            take_long=False,
            cooldown=st.p58_state == 3,
            cooldown_rem=st.cooldown_rem,
            cooldown_block=st.p58_state == 3,
            gate_open=False,
            already_in_trade_block=st.p58_in_trade,
            armed_state_block=st.p58_state not in (1, -1),
            pos_active_block=_pos_active(st),
            p58_block_signals=st.p58_block_signals,
            total_short=0,
            total_long=0,
            take_threshold_hit=False,
            is_new_opp=False,
            cur_opp_id=st.cur_opp_id,
            cur_opp_last_si=st.cur_opp_last_si,
            bars_since_opp=(i - st.cur_opp_last_si) if st.cur_opp_last_si >= 0 else 9999,
            struct_gap=cfg.struct_gap,
            decide_e="",
            p4_abstain=False,
            h1_abstain=False,
            p4_result="",
            h1_result="",
            band_short="",
            rev_sup_short="",
            dom_short="",
            high_sub_short="",
            htf_contra_short=False,
            ev_total_short=0,
            pending_take=st.pending_take,
            pending_dir=st.pending_dir,
            pending_signal_bar=st.pending_signal_bar,
            entry_pending=st.pending_take and i == st.pending_signal_bar + 1,
            entry_fired=False,
            exit_on_same_bar=False,
            prev_exit=False,
            branch="",
        )

        ev = super().on_bar(i)
        row_meta.state_after = ev.state_after
        row_meta.p58_state = st.p58_state
        row_meta.in_trade = ev.in_trade
        row_meta.trade_direction = ev.trade_direction
        row_meta.p58_in_trade = st.p58_in_trade
        row_meta.raw_short = ev.raw_short
        row_meta.raw_long = ev.raw_long
        row_meta.signal_short = ev.signal_short
        row_meta.signal_long = ev.signal_long
        row_meta.take_short = ev.take_short
        row_meta.take_long = ev.take_long
        row_meta.ev_total_short = ev.ev_total_short
        row_meta.entry_fired = ev.enter_short or ev.enter_long
        row_meta.exit_on_same_bar = ev.exit_stop or ev.exit_target or ev.exit_time
        row_meta.prev_exit = prev_pos in ("LONG_ACTIVE", "SHORT_ACTIVE") and st.pos_state == "FLAT"

        gate_open = (
            not _pos_active(st) and not st.p58_in_trade and st.p58_state != 3 and not st.p58_block_signals
        )
        row_meta.gate_open = gate_open

        if 0 <= k < len(f.ctx_dir) and st.p58_state == -1:
            dir_str = "SHORT"
            react_sc = f.react_short[k]
            loc_sc = f.loc_short[k]
            ctx_sc = min(2, f.bear_sc[k])
            contra = -1 if f.ctx_dir[k] == "NEUTRAL" and f.bull_sc[k] >= 2 else 0
            total = ctx_sc + loc_sc + react_sc + contra
            row_meta.total_short = total
            row_meta.take_threshold_hit = total >= cfg.take_threshold
            is_new = (
                not st.cur_opp_id
                or dir_str != st.cur_opp_dir
                or (i - st.cur_opp_last_si) > cfg.struct_gap
            )
            row_meta.is_new_opp = is_new
            row_meta.cur_opp_id = st.cur_opp_id
            row_meta.cur_opp_last_si = st.cur_opp_last_si
            row_meta.bars_since_opp = (i - st.cur_opp_last_si) if st.cur_opp_last_si >= 0 else 9999

            if row_meta.take_threshold_hit and gate_open:
                if is_new:
                    dec = decide_e(
                        int(f.ev_total_short[k]),
                        int(f.ev_react_short[k]),
                        int(f.ev_contra_short[k]),
                        0,
                        cfg,
                    )
                    row_meta.decide_e = dec
                    if dec == "TAKE":
                        band = f.band_short[k]
                        rev = f.rev_sup_short[k]
                        dom = f.dom_short[k]
                        hs = f.high_sub_short[k]
                        htf = f.htf_contra_short[k]
                        p4 = p4_abstain(dir_str, rev, dom, f.ctx15_state[k])
                        h1 = h1_abstain(hs, htf)
                        row_meta.p4_abstain = p4
                        row_meta.h1_abstain = h1
                        row_meta.p4_result = "ABSTAIN" if p4 else "KEEP"
                        row_meta.h1_result = "ABSTAIN" if h1 else "KEEP"
                        row_meta.band_short = str(band)
                        row_meta.rev_sup_short = str(rev)
                        row_meta.dom_short = str(dom)
                        row_meta.high_sub_short = str(hs)
                        row_meta.htf_contra_short = bool(htf)
                        row_meta.all_take_conds = {
                            "gate_open": gate_open,
                            "p58_state_armed_short": st.p58_state == -1,
                            "total_ge_threshold": total >= cfg.take_threshold,
                            "is_new_opp": is_new,
                            "decide_e_take": dec == "TAKE",
                            "not_p4_abstain": not p4,
                            "not_h1_abstain": not h1,
                            "not_pos_active": not _pos_active(st),
                        }
                        if ev.signal_short:
                            row_meta.branch = "TAKE_FIRED"
                        elif p4:
                            row_meta.branch = "P4_ABSTAIN"
                        elif h1:
                            row_meta.branch = "H1_ABSTAIN"
                        elif _pos_active(st):
                            row_meta.branch = "POS_ACTIVE_BLOCK"
                        else:
                            row_meta.branch = "TAKE_PATH_NOT_FIRED"
                    elif dec == "WAIT":
                        row_meta.branch = "DECIDE_WAIT"
                    else:
                        row_meta.branch = "DECIDE_PASS"
                else:
                    row_meta.branch = "NOT_NEW_OPP_UPDATE_ONLY"
                    row_meta.all_take_conds = {
                        "gate_open": gate_open,
                        "total_ge_threshold": True,
                        "is_new_opp": False,
                    }
            elif not gate_open:
                row_meta.branch = "GATE_CLOSED"
            else:
                row_meta.branch = "BELOW_THRESHOLD"

        self.fsm_rows.append(row_meta)
        return ev


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timestamp", required=True)
    ap.add_argument("--timezone", default="America/Chicago")
    ap.add_argument("--before", type=int, default=10)
    ap.add_argument("--after", type=int, default=5)
    args = ap.parse_args()

    m1, m5, m15 = load_markets_lw()
    center = pd.Timestamp(args.timestamp, tz=args.timezone)
    ci = int(m1.index.get_loc(center))
    mirror_start = mirror_fsm_start(m1, ci)
    end_i = min(len(m1) - 61, ci + args.after + 1)

    i0 = max(0, mirror_start - 3000)
    m1s = m1.iloc[i0:end_i]
    series = build_pine_series(m1s, m5, m15, DEFAULT_CFG)
    feat_start = mirror_start - i0
    feat_end = end_i - i0
    features = precompute_features(series, feat_start, feat_end, DEFAULT_CFG)

    eng = ForensicEngine(series, features, feat_start, DEFAULT_CFG, global_offset=i0)
    eng.run(feat_end)

    lo, hi = ci - args.before, ci + args.after
    rows = [r for r in eng.fsm_rows if lo <= r.bar_index <= hi]

    cols = [
        "timestamp", "bar_index", "state_before", "state_after", "p58_state", "armed_direction",
        "in_trade", "trade_direction", "p58_in_trade", "raw_short", "signal_short", "take_short",
        "gate_open", "cooldown_block", "already_in_trade_block", "pos_active_block",
        "total_short", "take_threshold_hit", "is_new_opp", "bars_since_opp", "decide_e",
        "p4_abstain", "h1_abstain", "branch", "all_take_conds", "ev_total_short",
        "pending_take", "entry_fired", "exit_on_same_bar",
    ]
    print("=" * 120)
    print(f"FSM FORENSIC | center={args.timestamp} | bars {lo}..{hi} | mirror_start={mirror_start}")
    print("=" * 120)
    for r in rows:
        d = {c: getattr(r, c) for c in cols}
        print(d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
