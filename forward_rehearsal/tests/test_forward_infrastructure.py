"""Forward rehearsal infrastructure tests."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from phase73.replay.runner import _synthetic_bars
from phase73.trader.fsm import TraderState
from phase73.webhook.schemas import WebhookReason, make_test_signal
from phase74.latency.tracker import LatencyTracker
from phase74.market_data.live_provider import StreamLiveDataProvider
from phase74.runtime.live_stack import LiveStack

from forward_rehearsal.audits.latency_audit import latency_distribution
from forward_rehearsal.audits.reconciliation import SignalReconciler
from forward_rehearsal.freeze import build_manifest, verify_manifest, write_manifest
from forward_rehearsal.runtime.forward_session import ForwardSession, load_forward_config
from forward_rehearsal.shadow.state_auditor import ShadowState, StateMachineAuditor


def infra_cfg():
    cfg = load_forward_config("infra-test")
    td = tempfile.mkdtemp()
    cfg.raw.setdefault("logging", {})["log_dir"] = td
    cfg.raw.setdefault("persistence", {})["state_file"] = str(Path(td) / "state.json")
    cfg.raw["persistence"]["idempotency_file"] = str(Path(td) / "idempotency.jsonl")
    cfg.raw.setdefault("contracts", {})["contract_month"] = "202609"
    return cfg


class ForwardInfrastructureTests(unittest.TestCase):
    def test_freeze_manifest_valid(self):
        write_manifest()
        ok, errs = verify_manifest()
        self.assertTrue(ok, errs)
        m = build_manifest()
        self.assertEqual(m["pine"]["required_sha256"], m["pine"]["sha256"])

    def test_reconciliation_match_and_duplicate(self):
        r = SignalReconciler()
        now = datetime.now(timezone.utc)
        r.record(
            signal_id="s1",
            tv_timestamp=now,
            webhook_timestamp=now,
            market_bar_timestamp=now,
            direction="LONG",
            signal_price=20000,
            atr=10,
            engine_action="WOULD_ENTER_LONG",
            reason="shadow entry",
            latency_ms=50,
        )
        r.record(
            signal_id="s1",
            tv_timestamp=now,
            webhook_timestamp=now,
            market_bar_timestamp=now,
            direction="LONG",
            signal_price=20000,
            atr=10,
            engine_action="WOULD_ENTER_LONG",
            reason="duplicate",
            latency_ms=50,
        )
        self.assertEqual(r.summary()["duplicates"], 1)

    def test_latency_distribution(self):
        d = latency_distribution([10, 20, 30, 40, 5000])
        self.assertEqual(d["count"], 5)
        self.assertEqual(d["median"], 30)
        self.assertEqual(d["max"], 5000)

    def test_state_machine_invalid_transition_halts(self):
        a = StateMachineAuditor()
        a.shadow_state = ShadowState.SHADOW_FLAT
        ok = a.transition_shadow(ShadowState.SHADOW_ACTIVE_LONG, trigger="bad", detail="skip states")
        self.assertFalse(ok)
        self.assertTrue(a.halted)

    def test_infra_shadow_session(self):
        cfg = infra_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(80))
        md.connect()
        stack = LiveStack(cfg, md)
        session = ForwardSession(cfg, stack, stage="infra-test", allow_synthetic=True)
        bar = md.latest_bar()
        sig = make_test_signal(
            "SIGNAL_LONG",
            signal_id="syn-test-long",
            signal_bar_time_utc=bar.timestamp,
            signal_time_utc=bar.timestamp,
            signal_price=bar.close,
            context="SYNTHETIC_INFRA",
        )
        r = session.stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        self.assertTrue(r.get("shadow") or r.get("ok"))
        self.assertEqual(stack.engine.state, TraderState.FLAT)
        for _ in range(5):
            md.advance()
            session.on_closed_bar()
        summary = session.finalize()
        self.assertGreater(summary["processed_signals"], 0)
        recon = Path(__file__).resolve().parents[1] / "reports" / "SHADOW_SIGNAL_RECONCILIATION.csv"
        self.assertTrue(recon.exists())

    def test_local_paper_entry_infra(self):
        cfg = load_forward_config("local-paper")
        td = tempfile.mkdtemp()
        cfg.raw["logging"]["log_dir"] = td
        cfg.raw["persistence"]["state_file"] = str(Path(td) / "state.json")
        cfg.raw["persistence"]["idempotency_file"] = str(Path(td) / "idempotency.jsonl")
        cfg.raw.setdefault("contracts", {})["contract_month"] = "202609"
        md = StreamLiveDataProvider(_synthetic_bars(80))
        md.connect()
        stack = LiveStack(cfg, md)
        session = ForwardSession(cfg, stack, stage="local-paper", allow_synthetic=True)
        bar = md.latest_bar()
        sig = make_test_signal(
            "SIGNAL_LONG",
            signal_id="syn-paper-long",
            signal_bar_time_utc=bar.timestamp,
            signal_time_utc=bar.timestamp,
            signal_price=bar.close,
            context="SYNTHETIC_INFRA",
        )
        session.stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        self.assertEqual(stack.engine.state, TraderState.LONG_ACTIVE)
        session.finalize()

    def test_restart_checkpoint(self):
        cfg = infra_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(40))
        md.connect()
        stack = LiveStack(cfg, md)
        session = ForwardSession(cfg, stack, stage="infra-test", allow_synthetic=True)
        bar = md.latest_bar()
        sig = make_test_signal(
            signal_id="syn-restart",
            signal_bar_time_utc=bar.timestamp,
            signal_time_utc=bar.timestamp,
            signal_price=bar.close,
            context="SYNTHETIC_INFRA",
        )
        session.stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        session.persist_checkpoint()
        cp = session.session_dir / "checkpoint.json"
        self.assertTrue(cp.exists())
        data = json.loads(cp.read_text())
        self.assertIn("syn-restart", data["processed_signals"])


if __name__ == "__main__":
    unittest.main()
