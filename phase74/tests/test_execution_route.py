"""Paper TAKE also routes a Phase85 SIM entry when the adapter is attached."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from phase73.replay.runner import _synthetic_bars
from phase73.webhook.schemas import WebhookReason, make_test_signal
from phase74.latency.tracker import LatencyTracker
from phase74.market_data.live_provider import StreamLiveDataProvider
from phase74.runtime.live_stack import LiveStack
from phase74.tests.test_phase74_integration import p74_cfg
from phase85.tests.support import ready_sim


class ExecutionRouteTests(unittest.TestCase):
    def test_paper_take_sends_nt_enter(self) -> None:
        cfg = p74_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        adapter, bridge = ready_sim(Path(tempfile.mkdtemp()))
        stack = LiveStack(cfg, md, execution_adapter=adapter)
        bar = md.latest_bar()
        now = datetime.now(timezone.utc)
        result = stack.on_webhook_signal(
            make_test_signal(
                "SIGNAL_LONG",
                signal_bar_time_utc=bar.timestamp,
                signal_time_utc=now,
                signal_price=bar.close,
            ),
            WebhookReason.WEBHOOK_VALID,
            LatencyTracker(),
        )
        self.assertTrue(result.get("ok"), result)
        commands = [cmd.command for cmd in bridge.submitted_commands]
        self.assertIn("ENTER_LONG", commands)
        self.assertIn("PLACE_PROTECTION", commands)

    def test_no_adapter_stays_local_sim(self) -> None:
        cfg = p74_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        result = stack.on_webhook_signal(
            make_test_signal(
                "SIGNAL_LONG",
                signal_bar_time_utc=bar.timestamp,
                signal_time_utc=bar.timestamp,
                signal_price=bar.close,
            ),
            WebhookReason.WEBHOOK_VALID,
            LatencyTracker(),
        )
        self.assertTrue(result.get("ok"), result)
        self.assertIsNone(stack.execution_adapter)

    def test_open_nt_position_does_not_open_another_paper_trade(self) -> None:
        cfg = p74_cfg()
        cfg.raw["quality_gates"]["enabled"] = True
        cfg.raw["quality_gates"]["filter_signals"] = False
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        adapter, bridge = ready_sim(Path(tempfile.mkdtemp()))
        stack = LiveStack(cfg, md, execution_adapter=adapter)
        bar = md.latest_bar()
        now = datetime.now(timezone.utc)
        first = stack.on_webhook_signal(
            make_test_signal(
                "SIGNAL_LONG",
                signal_bar_time_utc=bar.timestamp,
                signal_time_utc=now,
                signal_price=bar.close,
            ),
            WebhookReason.WEBHOOK_VALID,
            LatencyTracker(),
        )
        self.assertTrue(first.get("ok"), first)
        from phase73.execution.positions import PositionBook, PositionSnapshot
        from phase73.trader.fsm import TraderState

        stack.engine.mgmt = None
        stack.engine.book = PositionBook()
        stack.engine.state = TraderState.FLAT
        stack.broker.broker_position = PositionSnapshot()
        stack._active_trade_id = None
        before = len(bridge.submitted_commands)
        second = stack.on_webhook_signal(
            make_test_signal(
                "SIGNAL_SHORT",
                signal_id="second-while-open",
                signal_bar_time_utc=bar.timestamp,
                signal_time_utc=now,
                signal_price=bar.close,
            ),
            WebhookReason.WEBHOOK_VALID,
            LatencyTracker(),
        )
        self.assertFalse(second.get("ok"), second)
        self.assertEqual(second.get("reason"), "PRE_ENTRY_BLOCKED")
        self.assertEqual(stack.engine.state, TraderState.FLAT)
        self.assertEqual(len(bridge.submitted_commands), before)
        self.assertEqual(stack._day_halt.losers if stack._day_halt else 0, 0)

    def test_nt_reject_voids_paper_trade(self) -> None:
        cfg = p74_cfg()
        cfg.raw["quality_gates"]["enabled"] = True
        cfg.raw["quality_gates"]["filter_signals"] = False
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        adapter, bridge = ready_sim(Path(tempfile.mkdtemp()))
        bridge.inject_unexpected_position("LONG", 1)
        stack = LiveStack(cfg, md, execution_adapter=adapter)
        bar = md.latest_bar()
        now = datetime.now(timezone.utc)
        result = stack.on_webhook_signal(
            make_test_signal(
                "SIGNAL_SHORT",
                signal_bar_time_utc=bar.timestamp,
                signal_time_utc=now,
                signal_price=bar.close,
            ),
            WebhookReason.WEBHOOK_VALID,
            LatencyTracker(),
        )
        self.assertFalse(result.get("ok"), result)
        self.assertEqual(result.get("reason"), "REJECT_POSITION_OPEN")
        from phase73.trader.fsm import TraderState

        self.assertEqual(stack.engine.state, TraderState.FLAT)
        self.assertEqual(stack.journal._open, {})
        self.assertFalse((cfg.log_dir / "paper_trades.csv").exists())
        self.assertEqual(stack._day_halt.losers if stack._day_halt else 0, 0)
