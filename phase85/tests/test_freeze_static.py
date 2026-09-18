"""Static freeze + C# security scan."""
from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from phase74.config.loader import verify_phase73_freeze
from phase85.config import CRTBARBRIDGE_RELPATH, CRTBARBRIDGE_SHA256, FROZEN_PINE_HASH

REPO = Path(__file__).resolve().parents[2]
CS = REPO / "phase85" / "ninjatrader" / "CRTExecutionBridge.cs"
BAR = REPO / CRTBARBRIDGE_RELPATH
PINE = REPO / "TV_REVIEW" / "phase72a_autonomous_trader.pine"


class FreezeStaticTests(unittest.TestCase):
    def test_phase72a_hash_unchanged(self) -> None:
        actual = hashlib.sha256(PINE.read_bytes()).hexdigest()
        self.assertEqual(actual, FROZEN_PINE_HASH)

    def test_phase73_freeze(self) -> None:
        ok, errors = verify_phase73_freeze()
        self.assertTrue(ok, errors)

    def test_crtbarbridge_hash(self) -> None:
        actual = hashlib.sha256(BAR.read_bytes()).hexdigest()
        self.assertEqual(actual, CRTBARBRIDGE_SHA256)

    def test_crtbarbridge_has_no_order_routing_apis(self) -> None:
        text = BAR.read_text(encoding="utf-8")
        for tok in ("CreateOrder", "Account.Submit", "EnterLong", "EnterShort", "Flatten(", "OrderAction"):
            self.assertNotIn(tok, text)

    def test_execution_bridge_exists_and_is_separate(self) -> None:
        self.assertTrue(CS.exists())
        self.assertNotEqual(CS.resolve(), BAR.resolve())
        text = CS.read_text(encoding="utf-8")
        self.assertIn("CreateOrder", text)
        self.assertIn("ENTER_LONG", text)

    def test_execution_bridge_security_scan(self) -> None:
        text = CS.read_text(encoding="utf-8")
        forbidden = (
            "Process.Start",
            "ProcessStartInfo",
            "System.Diagnostics.Process",
            "Assembly.Load",
            "Eval(",
            "HttpClient",
            "WebClient",
            "WebRequest",
            "DownloadString",
            "File.Delete",
            "cmd.exe",
            "/bin/sh",
        )
        for tok in forbidden:
            self.assertNotIn(tok, text)
        self.assertIn("127.0.0.1", text)
        self.assertIn("MaxQuantity", text)
        self.assertIn("DUPLICATE_COMMAND", text)
        self.assertIn("crt_execution_token.txt", text)
        self.assertNotIn("PHASE74_WEBHOOK_SECRET", text)
        self.assertNotIn("NINJATRADER_BRIDGE_TOKEN", text)

    def test_bar_bridge_uses_different_token_file(self) -> None:
        bar = BAR.read_text(encoding="utf-8")
        exe = CS.read_text(encoding="utf-8")
        self.assertIn("crt_bridge_token.txt", bar)
        self.assertNotIn("crt_execution_token.txt", bar)
        self.assertIn("crt_execution_token.txt", exe)
        self.assertNotIn("crt_bridge_token.txt", exe)
