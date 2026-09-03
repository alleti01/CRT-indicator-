#!/usr/bin/env python3
"""Phase59F — bar-by-bar Python vs Pine-semantics diff for LW-063138 window."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58.research.instrument import NQ
from phase58j.research.lw_data import build_market_arrays_lw
from phase59.tools.phase59_parity import _load_cfg

TZ = NQ.timezone
OUT = ROOT / "phase59" / "reports"
WIN_START = pd.Timestamp("2026-08-26 13:20:00", tz=TZ)
WIN_END = pd.Timestamp("2026-08-26 13:42:00", tz=TZ)

COMPARE_COLS = [
    "atr",
    "ctxDir",
    "bullSc",
    "bearSc",
    "reactL",
    "reactS",
    "p58State",
    "p58Dir",
    "p58InTrade",
    "armedBars",
    "armedPrice",
    "total_score",
    "rawTake",
    "decision",
    "internal_entry",
    "internal_stop",
    "internal_target",
    "internal_exit_reason",
    "pendingTake",
    "pendingDir",
]


def _pine_state_name(v: int) -> str:
    return {0: "WATCH", 1: "ARMED_LONG", -1: "ARMED_SHORT", 2: "IN_LONG", -2: "IN_SHORT", 3: "COOLDOWN"}.get(v, str(v))


def simulate_pine_internal_semantics(df: pd.DataFrame, cfg: dict, fixed: bool = False) -> pd.DataFrame:
    """Mirror Pine phase59 internal trade lifecycle (fixed=True matches Phase59F patch)."""
    p58_stop_atr = cfg.get("stop_atr", 0.75)
    target_r = cfg.get("target_r", 2.5)
    max_hold = cfg.get("max_hold_min", 60)
    cooldown_bars = cfg.get("cooldown_bars", 3)

    rows = []
    p58_in = False
    p58_dir = ""
    p58_state = 0
    p58_entry_bar = -1
    p58_entry = np.nan
    p58_stop = np.nan
    p58_target = np.nan
    p58_deadline = -1
    cooldown_rem = 0
    pending_take = False
    pending_dir = ""
    pending_sig_bar = -1

    for _, r in df.iterrows():
        bi = int(r["bar_i"])
        o, h, l, c = r["open"], r["high"], r["low"], r["close"]
        atr = float(r["atr"])

        exit_reason = ""
        # M1 pending entry T+1 (open)
        if pending_take and bi == pending_sig_bar + 1:
            pending_take = False
            pending_dir = ""
            pending_sig_bar = -1

        # Pine: manage internal trade (entry bar excluded)
        if p58_in and bi > p58_entry_bar:
            if p58_dir == "LONG":
                hit_stop = l <= p58_stop
                hit_tgt = h >= p58_target
            else:
                hit_stop = h >= p58_stop
                hit_tgt = l <= p58_target
            if hit_stop or hit_tgt or bi >= p58_deadline:
                p58_in = False
                p58_state = 3
                cooldown_rem = cooldown_bars
                p58_dir = ""
                exit_reason = "STOP" if hit_stop else ("TARGET" if hit_tgt else "TIME")

        # Cooldown
        if p58_state == 3 and not p58_in:
            cooldown_rem -= 1
            if cooldown_rem <= 0:
                p58_state = 0

        # Entry bar fix — Pine recalculates stop from OPEN + current bar ATR
        if p58_in and bi == p58_entry_bar:
            p58_entry = o
            risk = p58_stop_atr * atr
            if p58_dir == "LONG":
                p58_stop = p58_entry - risk
                p58_target = p58_entry + target_r * risk
            else:
                p58_stop = p58_entry + risk
                p58_target = p58_entry - target_r * risk

        rows.append(
            {
                "bar_i": bi,
                "ts_chicago": r["ts_chicago"],
                "pine_p58InTrade": p58_in,
                "pine_p58State": p58_state,
                "pine_p58StateName": _pine_state_name(p58_state),
                "pine_p58Dir": p58_dir,
                "pine_internal_entry": p58_entry if p58_in or exit_reason else np.nan,
                "pine_internal_stop": p58_stop if p58_in or exit_reason else np.nan,
                "pine_internal_target": p58_target if p58_in or exit_reason else np.nan,
                "pine_internal_exit": exit_reason,
                "pine_pendingTake": pending_take,
            }
        )

        # Simulate TAKE from Python rawTake (same signal timing)
        if bool(r["rawTake"]) and not p58_in and p58_state != 3:
            d = str(r["p58Dir"])
            ep58 = c
            risk58 = p58_stop_atr * atr
            p58_in = True
            p58_dir = d
            p58_entry_bar = bi + 1
            p58_entry = o  # placeholder
            if d == "LONG":
                p58_stop = ep58 - risk58
                p58_target = ep58 + target_r * risk58
            else:
                p58_stop = ep58 + risk58
                p58_target = ep58 - target_r * risk58
            p58_deadline = bi + 1 + max_hold
            p58_state = 2 if d == "LONG" else -2
            pending_take = True
            pending_dir = d
            pending_sig_bar = bi

    return pd.DataFrame(rows)


def simulate_pine_fixed_internal(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Pine fix: entry/stop from signal-bar ATR + entry-bar close proxy (Python parity)."""
    p58_stop_atr = cfg.get("stop_atr", 0.75)
    target_r = cfg.get("target_r", 2.5)
    max_hold = cfg.get("max_hold_min", 60)
    cooldown_bars = cfg.get("cooldown_bars", 3)

    rows = []
    p58_in = False
    p58_dir = ""
    p58_state = 0
    p58_entry_bar = -1
    p58_entry = np.nan
    p58_stop = np.nan
    p58_target = np.nan
    p58_deadline = -1
    p58_signal_atr = np.nan
    cooldown_rem = 0

    for _, r in df.iterrows():
        bi = int(r["bar_i"])
        o, h, l, c = r["open"], r["high"], r["low"], r["close"]
        atr = float(r["atr"])
        exit_reason = ""

        if p58_in and bi > p58_entry_bar:
            if p58_dir == "LONG":
                hit_stop = l <= p58_stop
                hit_tgt = h >= p58_target
            else:
                hit_stop = h >= p58_stop
                hit_tgt = l <= p58_target
            if hit_stop or hit_tgt or bi >= p58_deadline:
                p58_in = False
                p58_state = 3
                cooldown_rem = cooldown_bars
                p58_dir = ""
                exit_reason = "STOP" if hit_stop else ("TARGET" if hit_tgt else "TIME")

        if p58_state == 3 and not p58_in:
            cooldown_rem -= 1
            if cooldown_rem <= 0:
                p58_state = 0

        # Fix: on entry bar, set entry/stop from signal ATR + entry bar close (Python cl[i+1])
        if p58_in and bi == p58_entry_bar:
            p58_entry = c  # Python proxy for open
            risk = p58_stop_atr * p58_signal_atr
            if p58_dir == "LONG":
                p58_stop = p58_entry - risk
                p58_target = p58_entry + target_r * risk
            else:
                p58_stop = p58_entry + risk
                p58_target = p58_entry - target_r * risk

        rows.append(
            {
                "bar_i": bi,
                "ts_chicago": r["ts_chicago"],
                "fixed_p58InTrade": p58_in,
                "fixed_p58State": p58_state,
                "fixed_internal_stop": p58_stop if p58_in or exit_reason else np.nan,
                "fixed_internal_exit": exit_reason,
            }
        )

        if bool(r["rawTake"]) and not p58_in and p58_state != 3:
            d = str(r["p58Dir"])
            p58_signal_atr = atr
            p58_in = True
            p58_dir = d
            p58_entry_bar = bi + 1
            p58_deadline = bi + 1 + max_hold
            p58_state = 2 if d == "LONG" else -2

    return pd.DataFrame(rows)


def main() -> int:
    cfg = _load_cfg()
    py = pd.read_csv(ROOT / "phase59/reports/phase59e/python_trace_1320_1345_chicago.csv")
    py["ts_chicago"] = py["ts_chicago"].astype(str)

    pine = simulate_pine_internal_semantics(py, cfg)
    fixed = simulate_pine_fixed_internal(py, cfg)
    merged = py.merge(pine, on=["bar_i", "ts_chicago"]).merge(fixed, on=["bar_i", "ts_chicago"])

    diffs = []
    first_bar = None
    first_var = None
    for _, r in merged.iterrows():
        for col, py_col, pine_col in [
            ("p58InTrade", "p58InTrade", "pine_p58InTrade"),
            ("p58State", "p58State", "pine_p58State"),
            ("internal_stop", "internal_stop", "pine_internal_stop"),
        ]:
            pv = r[py_col]
            tv = r[pine_col]
            if isinstance(pv, (bool, np.bool_)):
                match = bool(pv) == bool(tv)
            elif pd.isna(pv) and pd.isna(tv):
                match = True
            elif pd.isna(pv) or pd.isna(tv):
                match = False
            elif isinstance(pv, (int, float)):
                match = abs(float(pv) - float(tv)) < 1e-6
            else:
                match = str(pv) == str(tv)
            if not match:
                diffs.append(
                    {
                        "ts_chicago": r["ts_chicago"],
                        "variable": col,
                        "python": pv,
                        "pine_semantics": tv,
                        "decision_py": r["decision"],
                        "pine_exit": r.get("pine_internal_exit", ""),
                    }
                )
                if first_bar is None:
                    first_bar = r["ts_chicago"]
                    first_var = col

    merged["state_match"] = merged["p58InTrade"] == merged["pine_p58InTrade"]
    merged["fixed_match"] = merged["p58InTrade"] == merged["fixed_p58InTrade"]

    OUT.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUT / "phase59f_bar_by_bar_diff.csv", index=False)

    trans = []
    prev_py = None
    prev_pine = None
    for _, r in merged.iterrows():
        cur_py = (r["p58InTrade"], r["p58State"], r["decision"])
        cur_pine = (r["pine_p58InTrade"], r["pine_p58State"], r.get("pine_internal_exit", ""))
        if prev_py and cur_py != prev_py:
            trans.append({"ts": r["ts_chicago"], "side": "python", "state": cur_py})
        if prev_pine and cur_pine != prev_pine:
            trans.append({"ts": r["ts_chicago"], "side": "pine", "state": cur_pine})
        prev_py, prev_pine = cur_py, cur_pine
    pd.DataFrame(trans).to_csv(OUT / "phase59f_state_transition_diff.csv", index=False)

    print("PHASE59F TRACE")
    print(f"First divergence bar: {first_bar}")
    print(f"First divergent variable: {first_var}")
    if diffs:
        d0 = diffs[0]
        print(f"  Python: {d0['python']}  Pine: {d0['pine_semantics']}")
    print(f"Bars with p58InTrade mismatch (broken Pine): {(~merged['state_match']).sum()}")
    print(f"Bars with p58InTrade mismatch (fixed Pine): {(~merged['fixed_match']).sum()}")

    key = merged.loc[merged["ts_chicago"].str.contains("13:2[6-9]|13:3[0-2]")]
    for _, r in key.iterrows():
        print(
            f"  {r['ts_chicago'][-14:-6]} py_in={r['p58InTrade']} pine_in={r['pine_p58InTrade']} "
            f"fix_in={r['fixed_p58InTrade']} py_stop={r['internal_stop']:.2f} pine_stop={r['pine_internal_stop']:.2f} "
            f"dec={r['decision']} pine_exit={r['pine_internal_exit']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
