"""ATR level source: live stop, target and size come from NinjaTrader bars, not the chart."""
from __future__ import annotations

import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from phase73.market_data.bar import Bar
from phase73.replay.runner import _synthetic_bars
from phase73.webhook.schemas import WebhookReason, make_test_signal
from phase74.latency.tracker import LatencyTracker
from phase74.market_data.live_provider import StreamLiveDataProvider
from phase74.quality.atr_levels import AtrLevelConfig, atr3, compute_atr_levels
from phase74.runtime.live_stack import LiveStack
from phase74.tests.test_phase74_integration import p74_cfg
from phase85.tests.support import ready_sim

T0 = datetime(2026, 10, 20, 13, 0, tzinfo=timezone.utc)


def _bars(n: int = 120) -> list[Bar]:
    out = []
    for i in range(n):
        c = 30000 + 10 * math.sin(i / 9)
        out.append(Bar(T0 - timedelta(minutes=n - 1 - i), c, c + 3, c - 3, c, 10))
    return out


class ComputeTests(unittest.TestCase):
    def test_levels_from_atr(self) -> None:
        bars = _bars()
        atr = atr3(bars)
        lv, why = compute_atr_levels("SHORT", 30000.0, T0, bars, AtrLevelConfig())
        self.assertEqual(why, "")
        self.assertAlmostEqual(lv.stop - 30000.0, 1.5 * atr, delta=0.25)
        self.assertAlmostEqual(30000.0 - lv.target, 3.0 * atr, delta=0.25)
        self.assertEqual(lv.stop % 0.25, 0)
        self.assertEqual(lv.qty, min(10, math.floor(600 / (lv.stop_points * 2.0))))

    def test_stale_bars_refuse(self) -> None:
        lv, why = compute_atr_levels("LONG", 30000.0, T0 + timedelta(hours=1), _bars(), AtrLevelConfig())
        self.assertIsNone(lv)
        self.assertEqual(why, "STALE_BARS")

    def test_too_little_history_refuses(self) -> None:
        lv, why = compute_atr_levels("LONG", 30000.0, T0, _bars(20), AtrLevelConfig())
        self.assertEqual(why, "NO_ATR")


class LiveRouteTests(unittest.TestCase):
    def _stack(self, source: str):
        cfg = p74_cfg()
        cfg.raw["levels"] = {"source": source, "atr": {"risk_usd": 600}}
        start = (datetime.now(timezone.utc) - timedelta(minutes=121)).replace(second=0, microsecond=0)
        md = StreamLiveDataProvider(_synthetic_bars(120, start))
        md.connect()
        while md.advance():
            pass
        adapter, bridge = ready_sim(Path(tempfile.mkdtemp()))
        return LiveStack(cfg, md, execution_adapter=adapter), md, adapter, bridge

    def _signal(self, md, *, at=None, direction="SIGNAL_LONG"):
        bar = md.latest_bar()
        return make_test_signal(
            direction,
            signal_bar_time_utc=bar.timestamp,
            signal_time_utc=at or datetime.now(timezone.utc),
            signal_price=bar.close,
        )

    def test_atr_source_sets_broker_stop_target_and_size(self) -> None:
        stack, md, adapter, bridge = self._stack("atr")
        sig = self._signal(md)
        expected, _ = compute_atr_levels("LONG", sig.signal_price, sig.signal_time_utc, list(md.recent_bars(2000)),
                                         AtrLevelConfig(tick_size=stack.contract.tick_size))
        result = stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        self.assertTrue(result.get("ok"), result)
        enter = [c for c in bridge.submitted_commands if c.command == "ENTER_LONG"]
        prot = [c for c in bridge.submitted_commands if c.command == "PLACE_PROTECTION"]
        self.assertEqual(enter[0].quantity, min(expected.qty, adapter.cfg.max_quantity))
        self.assertEqual(prot[0].stop_price, expected.stop)
        self.assertEqual(prot[0].target_price, expected.target)
        mgmt = stack.engine.mgmt
        self.assertEqual(mgmt.stop_price, expected.stop)
        self.assertEqual(mgmt.target_price, expected.target)
        self.assertIsNone(stack._trail)  # ATR trades exit at stop or target, no trail

    def test_atr_source_refuses_when_bars_are_stale(self) -> None:
        stack, md, adapter, bridge = self._stack("atr")
        sig = self._signal(md, at=datetime.now(timezone.utc) + timedelta(minutes=30))
        result = stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        self.assertFalse(result.get("ok"), result)
        self.assertEqual(result.get("reason"), "ATR_LEVELS_STALE_BARS")
        self.assertEqual([c.command for c in bridge.submitted_commands if c.command.startswith("ENTER")], [])

    def test_chart_source_keeps_the_old_fixed_stop(self) -> None:
        stack, md, adapter, bridge = self._stack("chart")
        result = stack.on_webhook_signal(self._signal(md), WebhookReason.WEBHOOK_VALID, LatencyTracker())
        self.assertTrue(result.get("ok"), result)
        self.assertAlmostEqual(stack.engine.mgmt.risk, 14.25)
        enter = [c for c in bridge.submitted_commands if c.command == "ENTER_LONG"]
        self.assertEqual(enter[0].quantity, max(1, int(stack.contract.default_quantity or 1)))

    def test_default_config_is_chart(self) -> None:
        from phase74.config.loader import load_phase74_config

        self.assertEqual(load_phase74_config().section("levels").get("source"), "chart")


if __name__ == "__main__":
    unittest.main()
