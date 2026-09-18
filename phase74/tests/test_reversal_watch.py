"""Opposite TAKE must not freeze stop management (Phase74 overlay)."""
from __future__ import annotations

import copy
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from phase73.market_data.bar import Bar
from phase73.replay.runner import _synthetic_bars
from phase73.trader.fsm import TraderAction, TraderState
from phase73.webhook.schemas import WebhookReason, make_test_signal
from phase74.config.loader import Phase74Config, load_phase74_config
from phase74.latency.tracker import LatencyTracker
from phase74.market_data.live_provider import StreamLiveDataProvider
from phase74.runtime.live_stack import LiveStack


def _cfg() -> Phase74Config:
    raw = copy.deepcopy(load_phase74_config().raw)
    raw.setdefault("mode", {}).update(
        {"shadow_mode": False, "paper_mode": True, "trading_enabled": True}
    )
    raw.setdefault("contracts", {})["contract_month"] = "202609"
    raw.setdefault("logging", {})["log_dir"] = tempfile.mkdtemp()
    raw.setdefault("persistence", {})["state_file"] = str(Path(raw["logging"]["log_dir"]) / "state.json")
    raw["persistence"]["idempotency_file"] = str(Path(raw["logging"]["log_dir"]) / "idempotency.jsonl")
    raw.setdefault("quality_gates", {})["enabled"] = False
    raw["quality_gates"]["allow_globex_entries"] = True
    raw.setdefault("trail_overlay", {})["enabled"] = False
    return Phase74Config(raw=raw)


class ReversalWatchOverlayTests(unittest.TestCase):
    def test_opposite_long_keeps_short_active_and_stop_exits(self) -> None:
        cfg = _cfg()
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        assert bar is not None
        stack.on_webhook_signal(
            make_test_signal(
                "SIGNAL_SHORT",
                signal_bar_time_utc=bar.timestamp,
                signal_time_utc=bar.timestamp,
                signal_price=bar.close,
            ),
            WebhookReason.WEBHOOK_VALID,
            LatencyTracker(),
        )
        self.assertEqual(stack.engine.state, TraderState.SHORT_ACTIVE)
        entry = stack.engine.book.internal.entry_price
        stop = stack.engine.mgmt.stop_price
        assert entry is not None and stop is not None

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
        self.assertEqual(result.get("action"), TraderAction.OPPOSITE_SIGNAL_RECEIVED.value)
        self.assertEqual(stack.engine.state, TraderState.SHORT_ACTIVE)
        self.assertEqual(stack.engine.book.internal.side, "SHORT")
        self.assertNotEqual(stack.engine.state, TraderState.REVERSAL_WATCH_LONG)

        thru = Bar(
            bar.timestamp + timedelta(minutes=1),
            entry,
            stop + 2.0,
            entry - 1.0,
            stop + 1.0,
        )
        md.ingest_tick(thru, finalized=True)
        stack.on_bar()
        self.assertEqual(stack.engine.state, TraderState.FLAT)
        self.assertEqual(stack.engine.book.internal.side, "FLAT")


if __name__ == "__main__":
    unittest.main()
