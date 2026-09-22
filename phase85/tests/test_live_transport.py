"""Live NT transport hello / snapshot without a socket."""
from __future__ import annotations

import unittest

from phase85.ninjatrader.live_transport import LiveNtTransport
from phase85.protocol.messages import Event


class LiveNtTransportTests(unittest.TestCase):
    def test_hello_verifies_exact_account_and_contract(self) -> None:
        t = LiveNtTransport(expected_account="Sim101", expected_instrument="MNQ 12-26")
        t.handle_hello("Sim101", "MNQ 12-26")
        self.assertTrue(t.authenticated)
        self.assertTrue(t.account_verified)
        self.assertTrue(t.contract_verified)

    def test_hello_rejects_account_mismatch(self) -> None:
        t = LiveNtTransport(expected_account="Sim101", expected_instrument="MNQ 12-26")
        t.handle_hello("Other", "MNQ 12-26")
        self.assertTrue(t.authenticated)
        self.assertFalse(t.account_verified)

    def test_position_flat_updates_snapshot(self) -> None:
        t = LiveNtTransport(expected_account="Sim101", expected_instrument="MNQ 12-26")
        t.handle_hello("Sim101", "MNQ 12-26")
        t.handle_event(
            Event(
                event="POSITION_UPDATE",
                extra={"position_side": "LONG", "position_qty": 1},
            )
        )
        self.assertEqual(t.snapshot()["side"], "LONG")
        self.assertEqual(t.snapshot()["quantity"], 1)
        t.handle_event(Event(event="POSITION_FLAT"))
        self.assertEqual(t.snapshot()["side"], "FLAT")
        self.assertEqual(t.snapshot()["quantity"], 0)
