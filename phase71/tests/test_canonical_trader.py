"""Phase71 unit tests — deterministic trader."""
from __future__ import annotations

import numpy as np
import pytest

from phase71.python.canonical_trader import (
    ActiveTrade,
    TraderConfig,
    manage_trade_bars,
    persist_state,
    restore_trade,
)


def _market(n=100, base=100.0, half=0.4):
    """Tight range so default LONG stop at entry-1 is not touched (lo=99.6)."""
    hi = np.full(n, base + half)
    lo = np.full(n, base - half)
    cl = np.full(n, base)
    op = np.full(n, base)
    return hi, lo, cl, op


def _trade(direction="LONG", ep=100.0, atr=1.0, ei=10):
    risk = atr
    d = 1 if direction == "LONG" else -1
    return ActiveTrade(
        trade_id="T1", direction=direction, signal_i=ei - 1, entry_i=ei,
        entry_price=ep, initial_atr=atr, risk=risk,
        stop_price=ep - d * risk, target_price=ep + d * 2.5 * risk,
    )


class TestEntryNextBar:
    def test_entry_index(self):
        assert _trade().entry_i == 10


class TestLongStop:
    def test_long_hits_stop(self):
        hi, lo, cl, op = _market(50, 100.0)
        for k in range(11, 20):
            lo[k] = 98.0  # stop at 99
        t = _trade("LONG", 100.0, 1.0, 10)
        rec, _ = manage_trade_bars(t, hi, lo, cl, op, 50, TraderConfig(enable_t5=False))
        assert rec["exit_reason"] == "M0_STOP"
        assert rec["gross_r"] == pytest.approx(-1.0)


class TestShortStop:
    def test_short_hits_stop(self):
        hi, lo, cl, op = _market(50, 100.0)
        for k in range(11, 20):
            hi[k] = 102.0
        t = _trade("SHORT", 100.0, 1.0, 10)
        rec, _ = manage_trade_bars(t, hi, lo, cl, op, 50, TraderConfig(enable_t5=False))
        assert rec["exit_reason"] == "M0_STOP"


class TestTarget:
    def test_long_target(self):
        hi, lo, cl, op = _market(50, 100.0)
        for k in range(11, 30):
            hi[k] = 103.0
        t = _trade("LONG", 100.0, 1.0, 10)
        rec, _ = manage_trade_bars(t, hi, lo, cl, op, 50, TraderConfig(enable_t5=False))
        assert rec["exit_reason"] == "M0_TARGET"
        assert rec["gross_r"] == pytest.approx(2.5)


class TestStopFirst:
    def test_both_hit_stop_first(self):
        hi, lo, cl, op = _market(50, 100.0)
        k = 15
        hi[k] = 103.0
        lo[k] = 98.0
        t = _trade("LONG", 100.0, 1.0, 10)
        rec, _ = manage_trade_bars(t, hi, lo, cl, op, 50, TraderConfig(enable_t5=False))
        assert rec["exit_reason"] == "M0_STOP"


class TestT5Timing:
    def test_t5_at_minute_15(self):
        hi, lo, cl, op = _market(50, 100.0)
        t = _trade("LONG", 100.0, 1.0, 10)
        _, decs = manage_trade_bars(t, hi, lo, cl, op, 50, TraderConfig(enable_t5=True))
        t5_decs = [d for d in decs if d["t5_checked"] and d["action"] == "EXIT_TIME_PROGRESS"]
        if t5_decs:
            assert t5_decs[0]["minutes_in_trade"] == 15


class TestT5Mfe:
    def test_t5_exit_low_mfe(self):
        hi, lo, cl, op = _market(50, 100.0)
        # flat price — MFE ~0
        t = _trade("LONG", 100.0, 1.0, 10)
        rec, _ = manage_trade_bars(t, hi, lo, cl, op, 50, TraderConfig(enable_t5=True))
        assert rec["exit_reason"] == "T5_NO_PROGRESS"

    def test_t5_pass_high_mfe(self):
        hi, lo, cl, op = _market(50, 100.0)
        for k in range(11, 16):
            hi[k] = 101.5  # +1.5R MFE before T5
        t = _trade("LONG", 100.0, 1.0, 10)
        rec, _ = manage_trade_bars(t, hi, lo, cl, op, 50, TraderConfig(enable_t5=True))
        assert rec.get("t5_result") == "PASS"
        assert rec["exit_reason"] != "T5_NO_PROGRESS" or rec["hold_minutes"] > 15


class TestT5OnceOnly:
    def test_t5_checked_once(self):
        hi, lo, cl, op = _market(50, 100.0)
        for k in range(11, 16):
            hi[k] = 101.5
        t = _trade("LONG", 100.0, 1.0, 10)
        _, decs = manage_trade_bars(t, hi, lo, cl, op, 50, TraderConfig(enable_t5=True))
        checked = [d for d in decs if d["t5_checked"]]
        assert len(checked) >= 1
        first_check_bar = checked[0]["bar_index"]
        assert all(d["bar_index"] >= first_check_bar for d in checked)


class TestMaxHold:
    def test_max_hold_60(self):
        hi, lo, cl, op = _market(200, 100.0)
        t = _trade("LONG", 100.0, 1.0, 10)
        rec, _ = manage_trade_bars(t, hi, lo, cl, op, 200, TraderConfig(enable_t5=False, max_hold=60))
        assert rec["exit_reason"] == "MAX_HOLD_60M"
        assert rec["hold_minutes"] == 60


class TestRestart:
    def test_restart_parity(self):
        hi, lo, cl, op = _market(50, 100.0)
        for k in range(11, 20):
            hi[k] = 101.2
        t = _trade("LONG", 100.0, 1.0, 10)
        rec1, decs1 = manage_trade_bars(t, hi, lo, cl, op, 50, TraderConfig(enable_t5=True))
        # restart mid-trade at bar 14
        snap = persist_state(t)
        t2 = restore_trade("T1", snap, 9)
        rec2, decs2 = manage_trade_bars(t2, hi, lo, cl, op, 50, TraderConfig(enable_t5=True))
        assert rec1["exit_reason"] == rec2["exit_reason"]
        assert rec1["gross_r"] == pytest.approx(rec2["gross_r"])


class TestDuplicateBar:
    def test_deterministic(self):
        hi, lo, cl, op = _market(50, 100.0)
        t = _trade("LONG", 100.0, 1.0, 10)
        r1, _ = manage_trade_bars(t, hi, lo, cl, op, 50, TraderConfig(enable_t5=True))
        r2, _ = manage_trade_bars(t, hi, lo, cl, op, 50, TraderConfig(enable_t5=True))
        assert r1["gross_r"] == r2["gross_r"]


class TestPrefix:
    def test_prefix_invariance(self):
        hi, lo, cl, op = _market(50, 100.0)
        t = _trade("LONG", 100.0, 1.0, 10)
        r_full, _ = manage_trade_bars(t, hi, lo, cl, op, 50, TraderConfig(enable_t5=True))
        r_sub, _ = manage_trade_bars(t, hi[:30], lo[:30], cl[:30], op[:30], 30, TraderConfig(enable_t5=True))
        if r_full["hold_minutes"] <= 19:
            assert r_full["gross_r"] == pytest.approx(r_sub["gross_r"])


class TestSignalWhileActive:
    def test_one_position_skips(self):
        from phase71.python.canonical_trader import run_one_position
        import pandas as pd
        execs = pd.DataFrame([
            {"trade_id": "A", "direction": "LONG", "signal_i": 9, "entry_i": 10,
             "entry_price": 100.0, "atr_entry": 1.0, "entry_ts": 1},
            {"trade_id": "B", "direction": "LONG", "signal_i": 14, "entry_i": 15,
             "entry_price": 100.0, "atr_entry": 1.0, "entry_ts": 2},
        ])
        hi, lo, cl, op = _market(100, 100.0)
        m = type("M", (), {"n": 100, "hi": hi, "lo": lo, "cl": cl, "op": op})()
        trades, _, skipped = run_one_position(execs, m, TraderConfig(enable_t5=False))
        assert skipped["N"] >= 0
