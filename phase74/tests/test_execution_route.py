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
