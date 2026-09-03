#!/usr/bin/env python3
"""Phase59G — post-Phase59F bar-by-bar Pine vs Python state diff (13:31–13:41)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58.research.context import compute_context
from phase58.research.location import compute_location
from phase58.research.reaction import compute_all_reactions
from phase58.research.trader_engine import TraderEngine
from phase58.research.trader_state import State
from phase58j.research.lw_data import build_market_arrays_lw
from phase59.tools.phase59_parity import _load_cfg

OUT = ROOT / "phase59" / "reports"
WIN = ("2026-08-26 13:31:00", "2026-08-26 13:42:00")


def _st_name(v: int) -> str:
    return {0: "WATCH", 1: "ARMED_LONG", -1: "ARMED_SHORT", 2: "IN_LONG", -2: "IN_SHORT", 3: "COOLDOWN"}.get(v, str(v))


def _py_st(st: State) -> int:
    return {
        State.WATCH: 0,
        State.ARMED_LONG: 1,
        State.ARMED_SHORT: -1,
        State.IN_LONG: 2,
        State.IN_SHORT: -2,
        State.COOLDOWN: 3,
    }[st]


class PineStateSim:
    """Simulate Pine phase59_canonical_live Layer A ordering (Phase59F internal fix)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.p58_stop_atr = cfg.get("stop_atr", 0.75)
        self.target_r = cfg.get("target_r", 2.5)
        self.max_hold = cfg.get("max_hold_min", 60)
        self.cooldown_bars = cfg.get("cooldown_bars", 3)
        self.take_threshold = cfg.get("take_threshold", 4)
        self.armed_min = cfg.get("armed_min_score", 2)
        self.armed_timeout = cfg.get("armed_timeout_bars", 15)
        self.max_chase = cfg.get("max_chase_atr", 1.5)
        self.p58_skip_cd_dec = False
        self.reset()

    def reset(self) -> None:
        self.p58_state = 0
        self.p58_dir = ""
        self.p58_in = False
        self.p58_trade_dir = ""
        self.p58_entry_bar = -1
        self.p58_entry = np.nan
        self.p58_stop = np.nan
        self.p58_target = np.nan
        self.p58_deadline = -1
        self.p58_signal_atr = np.nan
        self.cooldown_rem = 0
        self.armed_bar = 0
        self.armed_bars = 0
        self.armed_price = np.nan
        self.pb_extreme = np.nan
        self.pending_take = False
        self.pending_dir = ""
        self.pending_sig_bar = -1
        self.decision = "WATCH"
        self.exit_reason = ""
        self.p58_skip_cd_dec = False
        self.p58_block_signals = False

    def _manage_internal(self, bi: int, h: float, l: float) -> None:
        self.exit_reason = ""
        if self.p58_in and bi > self.p58_entry_bar:
            if self.p58_trade_dir == "LONG":
                hit_stop = l <= self.p58_stop
                hit_tgt = h >= self.p58_target
            else:
                hit_stop = h >= self.p58_stop
                hit_tgt = l <= self.p58_target
            if hit_stop or hit_tgt or bi >= self.p58_deadline:
                self.p58_in = False
                self.p58_state = 3
                self.cooldown_rem = self.cooldown_bars
                self.p58_trade_dir = ""
                self.p58_dir = ""
                self.p58_skip_cd_dec = True
                self.exit_reason = "STOP" if hit_stop else ("TARGET" if hit_tgt else "TIME")

    def _cooldown(self) -> None:
        if self.p58_state == 3 and not self.p58_in:
            if not self.p58_skip_cd_dec:
                self.cooldown_rem -= 1
            self.p58_skip_cd_dec = False
            if self.cooldown_rem <= 0:
                self.p58_state = 0
                self.p58_dir = ""
                self.armed_bar = 0
                self.armed_bars = 0
                self.armed_price = np.nan
                self.pb_extreme = np.nan
                self.p58_block_signals = True
            self.decision = "COOLDOWN"

    def _signals(self, bi: int, ctx_dir: str, bull: int, bear: int, loc_l: int, loc_s: int,
                 react_l: int, react_s: int, close: float, lo: float, hi: float, atr: float) -> None:
        if self.p58_in or self.p58_state == 3:
            return
        self.decision = "WATCH"
        if self.p58_state == 0 and ctx_dir in ("BULLISH", "BEARISH"):
            trade_dir = "LONG" if ctx_dir == "BULLISH" else "SHORT"
            loc_sc = loc_l if trade_dir == "LONG" else loc_s
            ctx_sc = min(2, bull if trade_dir == "LONG" else bear)
            if ctx_sc + loc_sc >= self.armed_min:
                self.p58_state = 1 if trade_dir == "LONG" else -1
                self.p58_dir = trade_dir
                self.armed_bar = bi
                self.armed_bars = 0
                self.armed_price = close
                self.pb_extreme = close
                self.decision = f"ARMED {trade_dir}"

        if self.p58_state in (1, -1):
            self.armed_bars += 1
            dir_str = self.p58_dir
            if dir_str == "LONG":
                self.pb_extreme = min(self.pb_extreme, lo)
            else:
                self.pb_extreme = max(self.pb_extreme, hi)
            react_sc = react_l if dir_str == "LONG" else react_s
            loc_sc = loc_l if dir_str == "LONG" else loc_s
            ctx_sc = min(2, bull if dir_str == "LONG" else bear)
            contra = 0
            if dir_str == "LONG" and ctx_dir == "NEUTRAL" and bear >= 2:
                contra -= 1
            if dir_str == "SHORT" and ctx_dir == "NEUTRAL" and bull >= 2:
                contra -= 1
            total = ctx_sc + loc_sc + react_sc + contra
            det = (close - self.armed_price) / atr if dir_str == "LONG" else (self.armed_price - close) / atr

            if self.armed_bars > self.armed_timeout:
                self.p58_state = 0
                self.p58_dir = ""
                self.decision = "INVALIDATED"
            elif (dir_str == "LONG" and ctx_dir == "BEARISH") or (dir_str == "SHORT" and ctx_dir == "BULLISH"):
                self.p58_state = 0
                self.p58_dir = ""
                self.decision = "INVALIDATED"
            elif det > self.max_chase and react_sc >= 1:
                self.p58_state = 0
                self.p58_dir = ""
                self.decision = "MISSED"
            elif total >= self.take_threshold:
                self.decision = f"TAKE {dir_str}"
                self.pending_take = True
                self.pending_dir = dir_str
                self.pending_sig_bar = bi
                self.p58_in = True
                self.p58_trade_dir = dir_str
                self.p58_entry_bar = bi + 1
                self.p58_signal_atr = atr
                self.p58_entry = np.nan
                self.p58_stop = np.nan
                self.p58_target = np.nan
                self.p58_deadline = bi + 1 + self.max_hold
                self.p58_state = 2 if dir_str == "LONG" else -2
                self.armed_bar = 0
                self.armed_bars = 0
                self.armed_price = np.nan
                self.pb_extreme = np.nan
            else:
                self.decision = "WAIT" if react_sc >= 1 else "ARMED"

    def on_bar(self, row: dict, lo: float, hi: float) -> dict:
        bi = int(row["bar_i"])
        o, h, l, c = row["open"], hi, lo, row["close"]
        atr = float(row["atr"])

        # pending M1 entry T+1
        if self.pending_take and bi == self.pending_sig_bar + 1:
            self.pending_take = False
            self.pending_dir = ""

        if self.p58_in and (self.p58_state == 1 or self.p58_state == -1):
            self.p58_state = 2 if self.p58_trade_dir == "LONG" else -2

        if self.p58_in and bi == self.p58_entry_bar:
            self.p58_entry = c
            risk = self.p58_stop_atr * self.p58_signal_atr
            if self.p58_trade_dir == "LONG":
                self.p58_stop = self.p58_entry - risk
                self.p58_target = self.p58_entry + self.target_r * risk
            else:
                self.p58_stop = self.p58_entry + risk
                self.p58_target = self.p58_entry - self.target_r * risk

        self._manage_internal(bi, h, l)
        self._cooldown()
        if not self.p58_in and self.p58_state != 3 and not self.p58_block_signals:
            self._signals(
                bi, row["ctxDir"], int(row.get("bullSc", 0)), int(row.get("bearSc", 0)),
                int(row.get("locScLong", 0)), int(row.get("locScShort", 0)),
                int(row["reactL"]), int(row["reactS"]), c, l, h, atr,
            )
        if self.p58_block_signals:
            self.p58_block_signals = False

        return {
            "pine_p58InTrade": self.p58_in,
            "pine_p58State": self.p58_state,
            "pine_p58StateName": _st_name(self.p58_state),
            "pine_p58Dir": self.p58_dir,
            "pine_internal_stop": self.p58_stop,
            "pine_internal_entry": self.p58_entry,
            "pine_exit": self.exit_reason,
            "pine_pendingTake": self.pending_take,
            "pine_decision": self.decision,
        }


def _export_window(cfg: dict) -> pd.DataFrame:
    m = build_market_arrays_lw(swing=cfg.get("swing_period", 5))
    eng = TraderEngine(m, cfg)
    rows = []
    for i in range(eng.warmup, m.n - 61):
        snap = eng.on_bar_close(i)
        ts = str(m.idx[i])
        if ts < WIN[0] or ts >= WIN[1]:
            continue
        ctx = compute_context(m, i)
        loc_l = compute_location(m, i, "LONG")
        loc_s = compute_location(m, i, "SHORT")
        react_l = compute_all_reactions(m, i, "LONG", cfg)
        react_s = compute_all_reactions(m, i, "SHORT", cfg)
        t = eng.st.trade
        p58_in = t is not None and eng.st.state in (State.IN_LONG, State.IN_SHORT)
        rows.append({
            "bar_i": i,
            "ts_chicago": ts,
            "open": m.op[i], "high": m.hi[i], "low": m.lo[i], "close": m.cl[i],
            "atr": m.atr[i],
            "ctxDir": ctx["direction"],
            "bullSc": ctx["bull_score"],
            "bearSc": ctx["bear_score"],
            "locScLong": loc_l["score"],
            "locScShort": loc_s["score"],
            "reactL": react_l["score"],
            "reactS": react_s["score"],
            "p58InTrade": p58_in,
            "p58State": _py_st(eng.st.state),
            "p58StateName": eng.st.state.value,
            "p58Dir": eng.st.direction,
            "rawTake": snap.decision.value in ("TAKE_LONG", "TAKE_SHORT"),
            "decision": snap.decision.value,
            "internal_entry": float(t.entry_price) if t else np.nan,
            "internal_stop": float(t.stop) if t else np.nan,
            "armedBars": eng.st.armed_bars,
            "armedPrice": eng.st.armed_price,
        })
    return pd.DataFrame(rows)


def main() -> int:
    cfg = _load_cfg()
    # warm-start sim from full trace including 13:26 take
    full = pd.read_csv(ROOT / "phase59/reports/phase59e/python_trace_1320_1345_chicago.csv")
    full["ts_chicago"] = full["ts_chicago"].astype(str)

    sim = PineStateSim(cfg)
    # replay from 13:24 to seed state
    seed = full.copy()
    seed["bullSc"] = 0
    seed["bearSc"] = 0
    seed["locScLong"] = 0
    seed["locScShort"] = 0

    # enrich seed with scores from engine for key bars
    m = build_market_arrays_lw(swing=cfg.get("swing_period", 5))
    for idx, r in seed.iterrows():
        i = int(r["bar_i"])
        ctx = compute_context(m, i)
        loc_l = compute_location(m, i, "LONG")
        loc_s = compute_location(m, i, "SHORT")
        seed.at[idx, "bullSc"] = ctx["bull_score"]
        seed.at[idx, "bearSc"] = ctx["bear_score"]
        seed.at[idx, "locScLong"] = loc_l["score"]
        seed.at[idx, "locScShort"] = loc_s["score"]

    pine_rows = []
    for _, r in seed.iterrows():
        pr = sim.on_bar(r.to_dict(), r["low"], r["high"])
        pine_rows.append({**r.to_dict(), **pr})

    df = pd.DataFrame(pine_rows)
    focus = df.loc[df["ts_chicago"] >= "2026-08-26 13:31:00"].copy()

    first_diff = None
    for _, r in focus.iterrows():
        for col, pc, sc in [
            ("p58InTrade", "p58InTrade", "pine_p58InTrade"),
            ("p58State", "p58State", "pine_p58State"),
            ("internal_stop", "internal_stop", "pine_internal_stop"),
        ]:
            pv, sv = r[pc], r[sc]
            ok = (bool(pv) == bool(sv)) if pc == "p58InTrade" else (
                (pd.isna(pv) and pd.isna(sv)) or (not pd.isna(pv) and not pd.isna(sv) and abs(float(pv) - float(sv)) < 1e-4)
            )
            if not ok and first_diff is None:
                first_diff = (r["ts_chicago"], col, pv, sv)

    OUT.mkdir(parents=True, exist_ok=True)
    focus.to_csv(OUT / "phase59g_bar_by_bar_diff.csv", index=False)

    # cooldown variant: Python no decrement on exit bar
    print("PHASE59G — Pine sim (Phase59G cooldown + finalize order)")
    if first_diff:
        print(f"First diff after 13:31: {first_diff[0]} {first_diff[1]} py={first_diff[2]} pine={first_diff[3]}")
    else:
        print("No diff 13:31+ in internal/state columns (sim matches Python)")

    for _, r in focus.iterrows():
        t = r["ts_chicago"][-14:-6]
        print(
            f"  {t} py st={r['p58State']}({r['p58StateName']}) in={r['p58InTrade']} "
            f"pine st={r['pine_p58State']}({r['pine_p58StateName']}) in={r['pine_p58InTrade']} "
            f"dec={r['decision']} exit={r['pine_exit']} raw={r['rawTake']}"
        )

    # SHORT lifecycle from Python full trace
    short = full.loc[(full["ts_chicago"] >= "2026-08-26 13:26:00") & (full["ts_chicago"] <= "2026-08-26 13:35:00")]
    print("\nPython 13:26 SHORT lifecycle:")
    for _, r in short.iterrows():
        print(
            f"  {r['ts_chicago'][-14:-6]} {r['decision']} st={r['p58StateName']} in={r['p58InTrade']} "
            f"entry={r.get('internal_entry', '')} stop={r.get('internal_stop', '')} exit={r.get('internal_exit_reason', '')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
