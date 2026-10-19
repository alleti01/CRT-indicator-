"""Shadow ATR profiles: open, follow bars to an exit, day limits, persistence. No orders involved."""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from phase73.market_data.bar import Bar
from phase74.quality.shadow_profile import ProfileConfig, ShadowProfile, atr3

T0 = datetime(2026, 10, 20, 13, 0, tzinfo=timezone.utc)  # 9:00 ET


def _hist(n: int = 600, end: datetime = T0, base: float = 30000.0) -> list[Bar]:
    """n one-minute bars ending at `end`, each with a 4-point range."""
    out = []
    for i in range(n):
        t = end - timedelta(minutes=n - 1 - i)
        c = base + 10 * math.sin(i / 20)
        out.append(Bar(t, c, c + 2, c - 2, c, 10))
    return out


def _bar(minutes: int, high: float, low: float, close: float | None = None) -> Bar:
    c = close if close is not None else (high + low) / 2
    return Bar(T0 + timedelta(minutes=minutes), c, high, low, c, 10)


class ShadowProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.hist = _hist()
        self.atr = atr3(self.hist)
        self.cfg = ProfileConfig(name="t", stop_atr=1.5, target_r=2.0, risk_usd=600)

    def _profile(self, **kw) -> ShadowProfile:
        return ShadowProfile(ProfileConfig(**{**self.cfg.__dict__, **kw}), self.tmp)

    def _rows(self) -> list[dict]:
        return [json.loads(l) for l in (self.tmp / "shadow_profiles.jsonl").read_text().splitlines()]

    def test_opens_with_atr_stop_and_dollar_sizing(self) -> None:
        p = self._profile()
        self.assertEqual(p.on_signal("2026-10-20T13:00:00Z", "LONG", 30000.0, T0, self.hist), "OPEN")
        tr = p.state.open
        dist = 1.5 * self.atr
        self.assertAlmostEqual(tr.entry - tr.stop, dist, places=1)
        self.assertAlmostEqual(tr.target - tr.entry, 2 * dist, places=1)
        self.assertEqual(tr.qty, min(10, math.floor(600 / (dist * 2.0))))

    def test_quantity_is_capped_when_atr_is_tiny(self) -> None:
        p = self._profile(max_qty=7)
        p.on_signal("2026-10-20T13:00:00Z", "LONG", 30000.0, T0, self.hist)
        self.assertEqual(p.state.open.qty, 7)

    def test_target_close_books_profit_and_frees_the_slot(self) -> None:
        p = self._profile()
        p.on_signal("2026-10-20T13:00:00Z", "LONG", 30000.0, T0, self.hist)
        tr = p.state.open
        self.assertIsNone(p.on_bar(_bar(0, tr.target + 5, tr.entry)))  # signal bar itself is ignored
        out = p.on_bar(_bar(1, tr.target + 1, tr.entry - 1))
        self.assertEqual(out["exit_reason"], "TARGET")
        self.assertAlmostEqual(out["r"], 2.0, places=2)
        self.assertIsNone(p.state.open)
        self.assertGreater(p.state.balance, 0)

    def test_stop_wins_when_both_hit_in_one_bar(self) -> None:
        p = self._profile()
        p.on_signal("2026-10-20T13:00:00Z", "SHORT", 30000.0, T0, self.hist)
        tr = p.state.open
        out = p.on_bar(_bar(1, tr.stop + 1, tr.target - 1))
        self.assertEqual(out["exit_reason"], "STOP")
        self.assertAlmostEqual(out["r"], -1.0, places=2)

    def test_time_exit_after_max_hold(self) -> None:
        p = self._profile(max_hold_minutes=30)
        p.on_signal("2026-10-20T13:00:00Z", "LONG", 30000.0, T0, self.hist)
        self.assertIsNone(p.on_bar(_bar(10, 30001, 29999)))
        out = p.on_bar(_bar(30, 30003, 29999, 30002))
        self.assertEqual(out["exit_reason"], "TIME")
        self.assertAlmostEqual(out["points"], 2.0)

    def test_skips_while_a_position_is_open(self) -> None:
        p = self._profile()
        p.on_signal("2026-10-20T13:00:00Z", "LONG", 30000.0, T0, self.hist)
        self.assertEqual(p.on_signal("2026-10-20T13:03:00Z", "SHORT", 30000.0, T0, self.hist), "SKIP_POSITION_OPEN")

    def test_day_limit_after_one_winner(self) -> None:
        p = self._profile()
        p.on_signal("2026-10-20T13:00:00Z", "LONG", 30000.0, T0, self.hist)
        tr = p.state.open
        p.on_bar(_bar(1, tr.target + 1, tr.entry))
        self.assertEqual(p.on_signal("2026-10-20T13:30:00Z", "LONG", 30000.0, T0, self.hist), "SKIP_DAY_LIMIT")

    def test_ignores_test_signals_and_duplicates(self) -> None:
        p = self._profile()
        self.assertEqual(p.on_signal("d27035f4-30bb-4c19-9aa0-51cabf068a16", "LONG", 30000.0, T0, self.hist), "IGNORED")
        p.on_signal("2026-10-20T13:00:00Z", "LONG", 30000.0, T0, self.hist)
        self.assertEqual(p.on_signal("2026-10-20T13:00:00Z", "LONG", 30000.0, T0, self.hist), "DUPLICATE")

    def test_stale_bars_are_refused(self) -> None:
        p = self._profile()
        old = _hist(end=T0 - timedelta(days=17))
        self.assertEqual(p.on_signal("2026-10-20T13:00:00Z", "LONG", 30000.0, T0, old), "SKIP_STALE_BARS")
        self.assertIsNone(p.state.open)

    def test_15m_filter_skips_when_not_agreeing(self) -> None:
        p = self._profile(filter="15m_agrees")
        self.assertEqual(p.on_signal("2026-10-20T13:00:00Z", "LONG", 30000.0, T0, self.hist), "SKIP_15M_NOT_AGREEING")
        self.assertEqual(self._rows()[-1]["align_15m"], 0)

    def test_open_trade_and_balance_survive_restart(self) -> None:
        p = self._profile()
        p.on_signal("2026-10-20T13:00:00Z", "LONG", 30000.0, T0, self.hist)
        again = self._profile()
        self.assertEqual(again.state.open.signal_id, "2026-10-20T13:00:00Z")
        tr = again.state.open
        again.on_bar(_bar(1, tr.target + 1, tr.entry))
        self.assertGreater(self._profile().state.balance, 0)

    def test_eval_pass_is_recorded(self) -> None:
        p = self._profile(eval_target_usd=100.0)
        p.on_signal("2026-10-20T13:00:00Z", "LONG", 30000.0, T0, self.hist)
        tr = p.state.open
        out = p.on_bar(_bar(1, tr.target + 1, tr.entry))
        self.assertTrue(out["eval_status"].startswith("PASSED"))


if __name__ == "__main__":
    unittest.main()
