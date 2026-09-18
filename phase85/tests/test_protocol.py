"""Unit tests — protocol."""
from __future__ import annotations

import unittest

from phase85.ninjatrader.fake_bridge import FakeExecutionBridge
from phase85.protocol.codec import ProtocolError, command_from_dict, decode_line, encode_message, parse_utc
from phase85.protocol.messages import PROTOCOL_VERSION, Command


TOKEN = "unit-test-execution-token"


class ProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = FakeExecutionBridge(expected_token=TOKEN, expected_account="SIM101")
        self.bridge.connect(TOKEN)

    def _cmd(self, **over) -> str:
        base = {
            "protocol_version": PROTOCOL_VERSION,
            "command": "PING",
            "command_id": "c1",
            "created_at_utc": "2026-09-18T12:00:00Z",
            "account": "SIM101",
            "instrument": "MNQ 12-26",
            "quantity": 1,
        }
        base.update(over)
        return encode_message(base)

    def test_valid_auth(self) -> None:
        self.assertTrue(self.bridge.authenticated)
        evs = self.bridge.handle_line(self._cmd(), TOKEN)
        self.assertEqual(evs[0].event, "PONG")

    def test_invalid_auth(self) -> None:
        evs = self.bridge.handle_line(self._cmd(), "wrong")
        self.assertEqual(evs[0].reason, "AUTH_FAILED")

    def test_missing_auth(self) -> None:
        evs = self.bridge.handle_line(self._cmd(), "")
        self.assertEqual(evs[0].reason, "AUTH_FAILED")

    def test_valid_command(self) -> None:
        cmd = command_from_dict(decode_line(self._cmd(command="ENTER_LONG", command_id="e1")))
        self.assertEqual(cmd.command, "ENTER_LONG")

    def test_malformed_json(self) -> None:
        evs = self.bridge.handle_line("{not-json", TOKEN)
        self.assertEqual(evs[0].reason, "MALFORMED_JSON")

    def test_unknown_command(self) -> None:
        evs = self.bridge.handle_line(self._cmd(command="SHELL"), TOKEN)
        self.assertEqual(evs[0].reason, "UNKNOWN_COMMAND")

    def test_unsupported_protocol_version(self) -> None:
        evs = self.bridge.handle_line(self._cmd(protocol_version=99), TOKEN)
        self.assertEqual(evs[0].reason, "UNSUPPORTED_PROTOCOL")

    def test_invalid_timestamp(self) -> None:
        evs = self.bridge.handle_line(self._cmd(created_at_utc="not-a-date"), TOKEN)
        self.assertEqual(evs[0].reason, "INVALID_TIMESTAMP")

    def test_invalid_quantity(self) -> None:
        evs = self.bridge.handle_line(self._cmd(quantity=0, command="ENTER_LONG"), TOKEN)
        self.assertEqual(evs[0].reason, "INVALID_QUANTITY")

    def test_invalid_account(self) -> None:
        evs = self.bridge.handle_line(self._cmd(command="ENTER_LONG", account="OTHER", command_id="a1"), TOKEN)
        self.assertEqual(evs[0].reason, "REJECT_ACCOUNT_NOT_ALLOWED")

    def test_invalid_contract(self) -> None:
        evs = self.bridge.handle_line(
            self._cmd(command="ENTER_LONG", instrument="NQ 12-26", command_id="n1"),
            TOKEN,
        )
        self.assertEqual(evs[0].reason, "REJECT_CONTRACT_MISMATCH")

    def test_duplicate_command(self) -> None:
        line = self._cmd(command="ENTER_LONG", command_id="dup1")
        first = self.bridge.handle_line(line, TOKEN)
        self.assertTrue(any(e.event == "FILLED" for e in first))
        second = self.bridge.handle_line(line, TOKEN)
        self.assertEqual(second[0].event, "DUPLICATE_COMMAND")

    def test_duplicate_event_same_command_id(self) -> None:
        line = self._cmd(command="ENTER_LONG", command_id="dup2", event_id="evt-same")
        self.bridge.handle_line(line, TOKEN)
        again = self.bridge.handle_line(line, TOKEN)
        self.assertEqual(again[0].reason, "DUPLICATE_COMMAND")

    def test_out_of_order_events_do_not_crash(self) -> None:
        self.bridge.out_of_order_events = True
        evs = self.bridge.handle_line(self._cmd(command="ENTER_LONG", command_id="oo1"), TOKEN)
        names = [e.event for e in evs]
        self.assertIn("ORDER_ACCEPTED", names)
        self.assertIn("FILLED", names)

    def test_parse_utc(self) -> None:
        dt = parse_utc("2026-09-18T12:00:00Z")
        self.assertEqual(dt.tzinfo.utcoffset(dt).total_seconds(), 0)

    def test_command_dataclass_roundtrip(self) -> None:
        cmd = Command(command="FLATTEN", command_id="f1", created_at_utc="2026-09-18T12:00:00Z", quantity=1)
        again = command_from_dict(decode_line(encode_message(cmd.to_dict())))
        self.assertEqual(again.command, "FLATTEN")


if __name__ == "__main__":
    unittest.main()
