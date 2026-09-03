#!/usr/bin/env python3
"""Early SHORT signal forensic — Aug 30 21:24-21:35 Chicago."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
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


@dataclass
class BarForensic:
    timestamp: str
    bar_index: int
    open: float
    high: float
    low: float
    close: float
    atr: float
    m5_completed_j: int
    m15_completed_j: int
    m5_c: float
    m15_c: float
    ctx_dir: str
    bull_sc: int
    bear_sc: int
    loc_long: int
    loc_short: int
    react_long: int
    react_short: int
    ev_total_long: int
    ev_total_short: int
    ev_react_long: int
    ev_react_short: int
    ev_contra_long: int
    ev_contra_short: int
    ctx15_state: str
    band_short: str
    rev_sup_short: str
    dom_short: str
    high_sub_short: str
    htf_contra_short: bool
    cur_opp_id: str
    cur_opp_dir: str
    cur_opp_last_si: int
    bars_since_opp: int
    is_new_opp: bool
    state_before: str
    state_after: str
    p58_state: int
    p58_dir: str
    p58_in_trade: bool
    cooldown: bool
    cooldown_rem: int
    p58_block_signals: bool
    gate_open: bool
    armed_bars: int
    armed_total_short: int
    raw_short: bool
    dec_e_short: str
    p4_abstain: bool
    h1_abstain: bool
    pos_active_block: bool
    signal_short: bool
    signal_fired_this_bar: bool
    branch: str
    take_bools: dict


class ForensicEngine(AutonomousMirrorEngine):
    rows: list[BarForensic]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []
        self._last_signal_short = False

    def on_bar(self, i: int):
        s, f, st, cfg = self.s, self.f, self.st, self.cfg
        k = self._feat(i)
        state_before = _state_label(st)
        st_snap = {
            "cur_opp_id": st.cur_opp_id,
            "cur_opp_dir": st.cur_opp_dir,
            "cur_opp_last_si": st.cur_opp_last_si,
            "p58_state": st.p58_state,
            "p58_in_trade": st.p58_in_trade,
            "p58_block_signals": st.p58_block_signals,
            "armed_bars": st.armed_bars,
            "pos_active": _pos_active(st),
        }

        ev = super().on_bar(i)

        gate_open = (
            not st_snap["pos_active"]
            and not st_snap["p58_in_trade"]
            and st_snap["p58_state"] != 3
            and not st_snap["p58_block_signals"]
        )
        ctx_sc = min(2, f.bear_sc[k]) if k >= 0 else 0
        loc_sc = f.loc_short[k] if k >= 0 else 0
        react_sc = f.react_short[k] if k >= 0 else 0
        contra = -1 if f.ctx_dir[k] == "NEUTRAL" and f.bull_sc[k] >= 2 else 0 if k >= 0 else 0
        total = ctx_sc + loc_sc + react_sc + contra
        raw_short = st_snap["p58_state"] == -1 and total >= cfg.take_threshold
        is_new = (
            not st_snap["cur_opp_id"]
            or "SHORT" != st_snap["cur_opp_dir"]
            or (i - st_snap["cur_opp_last_si"]) > cfg.struct_gap
        )
        dec_e = ""
        p4 = h1 = False
        branch = ""
        take_bools = {}
        if st_snap["p58_state"] == -1 and k >= 0:
            if total >= cfg.take_threshold and gate_open:
                if is_new:
                    dec_e = decide_e(
                        int(f.ev_total_short[k]), int(f.ev_react_short[k]), int(f.ev_contra_short[k]), 0, cfg
                    )
                    p4 = p4_abstain("SHORT", f.rev_sup_short[k], f.dom_short[k], f.ctx15_state[k])
                    h1 = h1_abstain(f.high_sub_short[k], f.htf_contra_short[k])
                    take_bools = {
                        "gateOpen": gate_open,
                        "stateEligible_armed_short": st_snap["p58_state"] == -1,
                        "rawShort": raw_short,
                        "total": total,
                        "takeThreshold": cfg.take_threshold,
                        "total_ge_threshold": total >= cfg.take_threshold,
                        "isNewOpp": is_new,
                        "curOppDir_before": st_snap["cur_opp_dir"],
                        "curOppLastSi_before": st_snap["cur_opp_last_si"],
                        "structGap": cfg.struct_gap,
                        "decE": dec_e,
                        "decE_is_TAKE": dec_e == "TAKE",
                        "p4Abstain": p4,
                        "h1Abstain": h1,
                        "positionActive": st_snap["pos_active"],
                        "p58InTrade_before": st_snap["p58_in_trade"],
                        "p58BlockSignals_before": st_snap["p58_block_signals"],
                        "signalShort": ev.signal_short,
                    }
                    if ev.signal_short:
                        branch = "SIGNAL_FIRED"
                    elif dec_e != "TAKE":
                        branch = f"DECIDE_{dec_e}"
                    elif p4:
                        branch = "P4_ABSTAIN"
                    elif h1:
                        branch = "H1_ABSTAIN"
                    else:
                        branch = "TAKE_BLOCKED"
                else:
                    branch = "NOT_NEW_OPP"
            elif not gate_open:
                branch = "GATE_CLOSED"
            else:
                branch = "BELOW_THRESHOLD"

        cj5 = int(s.m5_completed_j[k]) if k >= 0 else -1
        cj15 = int(s.m15_completed_j[k]) if k >= 0 else -1
        self.rows.append(
            BarForensic(
                timestamp=str(s.idx[k + self.start_i] if False else s.idx[i]),
                bar_index=i + self.global_offset,
                open=float(s.op[i]),
                high=float(s.hi[i]),
                low=float(s.lo[i]),
                close=float(s.cl[i]),
                atr=float(s.atr_use[i]),
                m5_completed_j=cj5,
                m15_completed_j=cj15,
                m5_c=float(s.m5_c[i]),
                m15_c=float(s.m15_c[i]),
                ctx_dir=str(f.ctx_dir[k]) if k >= 0 else "",
                bull_sc=int(f.bull_sc[k]) if k >= 0 else 0,
                bear_sc=int(f.bear_sc[k]) if k >= 0 else 0,
                loc_long=int(f.loc_long[k]) if k >= 0 else 0,
                loc_short=int(f.loc_short[k]) if k >= 0 else 0,
                react_long=int(f.react_long[k]) if k >= 0 else 0,
                react_short=int(f.react_short[k]) if k >= 0 else 0,
                ev_total_long=int(f.ev_total_long[k]) if k >= 0 else 0,
                ev_total_short=int(f.ev_total_short[k]) if k >= 0 else 0,
                ev_react_long=int(f.ev_react_long[k]) if k >= 0 else 0,
                ev_react_short=int(f.ev_react_short[k]) if k >= 0 else 0,
                ev_contra_long=int(f.ev_contra_long[k]) if k >= 0 else 0,
                ev_contra_short=int(f.ev_contra_short[k]) if k >= 0 else 0,
                ctx15_state=str(f.ctx15_state[k]) if k >= 0 else "",
                band_short=str(f.band_short[k]) if k >= 0 else "",
                rev_sup_short=str(f.rev_sup_short[k]) if k >= 0 else "",
                dom_short=str(f.dom_short[k]) if k >= 0 else "",
                high_sub_short=str(f.high_sub_short[k]) if k >= 0 else "",
                htf_contra_short=bool(f.htf_contra_short[k]) if k >= 0 else False,
                cur_opp_id=st.cur_opp_id,
                cur_opp_dir=st.cur_opp_dir,
                cur_opp_last_si=st.cur_opp_last_si,
                bars_since_opp=(i - st.cur_opp_last_si) if st.cur_opp_last_si >= 0 else 9999,
                is_new_opp=is_new,
                state_before=state_before,
                state_after=ev.state_after,
                p58_state=st.p58_state,
                p58_dir=st.p58_dir,
                p58_in_trade=st.p58_in_trade,
                cooldown=st.p58_state == 3,
                cooldown_rem=st.cooldown_rem,
                p58_block_signals=st.p58_block_signals,
                gate_open=gate_open,
                armed_bars=st.armed_bars,
                armed_total_short=total,
                raw_short=raw_short,
                dec_e_short=dec_e,
                p4_abstain=p4,
                h1_abstain=h1,
                pos_active_block=_pos_active(st),
                signal_short=bool(ev.signal_short),
                signal_fired_this_bar=bool(ev.signal_short),
                branch=branch,
                take_bools=take_bools,
            )
        )
        return ev


def main() -> int:
    m1, m5, m15 = load_markets_lw()
    t0 = pd.Timestamp("2026-08-30 17:00:00", tz="America/Chicago")
    t_end = pd.Timestamp("2026-08-30 21:36:00", tz="America/Chicago")
    start_i = int(m1.index.get_loc(t0))
    end_i = int(m1.index.get_loc(t_end)) + 1
    i0 = max(0, start_i - 3000)
    m1s = m1.iloc[i0:end_i]
    series = build_pine_series(m1s, m5, m15, DEFAULT_CFG)
    feat_start = start_i - i0
    feat_end = end_i - i0
    features = precompute_features(series, feat_start, feat_end, DEFAULT_CFG)
    eng = ForensicEngine(series, features, feat_start, DEFAULT_CFG, global_offset=i0)
    eng.run(feat_end)

    bi0 = int(m1.index.get_loc(pd.Timestamp("2026-08-30 21:24:00", tz="America/Chicago")))
    bi1 = int(m1.index.get_loc(pd.Timestamp("2026-08-30 21:35:00", tz="America/Chicago")))
    rows = [asdict(r) for r in eng.rows if bi0 <= r.bar_index <= bi1]

    out = ROOT / "phase72b" / "reports" / "EARLY_SHORT_SIGNAL_FORENSIC.json"
    out.write_text(json.dumps(rows, indent=2, default=str))

    ref = next(r for r in rows if r["bar_index"] == int(m1.index.get_loc(pd.Timestamp("2026-08-30 21:29:00", tz="America/Chicago"))))
    print("=== 21:29 SIGNAL BOOLEAN TRACE ===")
    print(json.dumps(ref, indent=2, default=str))

    print("\n=== WINDOW SUMMARY ===")
    for r in rows:
        mark = " *** SIGNAL ***" if r["signal_short"] else ""
        print(
            f"{r['timestamp']} st {r['state_before']}->{r['state_after']} "
            f"rawS={r['raw_short']} totS={r['armed_total_short']} evS={r['ev_total_short']} "
            f"isNew={r['is_new_opp']} decE={r['dec_e_short']} p4={r['p4_abstain']} h1={r['h1_abstain']} "
            f"opp={r['cur_opp_id'][-12:] if r['cur_opp_id'] else '-'} since={r['bars_since_opp']} "
            f"{r['branch']}{mark}"
        )
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
