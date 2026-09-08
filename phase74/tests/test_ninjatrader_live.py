"""NinjaTrader live data bridge tests."""
from __future__ import annotations

import json
import re
import socket
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from phase73.market_data.bar import Bar
from phase73.market_data.health import DataHealth
from phase73.replay.runner import _synthetic_bars
from phase74.config.loader import load_phase74_config, verify_phase73_freeze
from phase74.market_data.live_provider import StreamLiveDataProvider, compare_replay_live_parity
from phase74.market_data.ninjatrader.protocol import bar_from_message, parse_line, parse_utc
from phase74.market_data.ninjatrader_live import NinjaTraderLiveDataProvider

ROOT = Path(__file__).resolve().parents[2]
CS_BRIDGE = ROOT / "phase74" / "market_data" / "ninjatrader" / "CRTBarBridge.cs"

FORBIDDEN_ORDER_APIS = [
    "EnterLong",
    "EnterShort",
    "ExitLong",
    "ExitShort",
    "SubmitOrder",
    "CancelOrder",
    "Account",
    "AtmStrategy",
    "Order.",
    "CreateOrder",
    "ChangeOrder",
]


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _send_line(sock: socket.socket, obj: dict) -> dict:
    sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("connection closed before ack")
        buf += chunk
    return json.loads(buf.decode("utf-8").strip())


class MockNTClient:
    def __init__(self, host: str, port: int, token: str, contract: str = "NQ 09-26") -> None:
        self.host = host
        self.port = port
        self.token = token
        self.contract = contract
        self.sock: socket.socket | None = None
        self.seq = 0

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=5)
        ack = _send_line(
            self.sock,
            {
                "type": "hello",
                "seq": self.seq,
                "auth": self.token,
                "contract": self.contract,
                "instrument": "NQ",
                "chart_timezone": "UTC",
            },
        )
        if not ack.get("ok"):
            raise RuntimeError(f"hello rejected: {ack}")

    def send_bar(self, bar: Bar) -> dict:
        assert self.sock is not None
        self.seq += 1
        return _send_line(
            self.sock,
            {
                "type": "bar",
                "seq": self.seq,
                "ts_utc": bar.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "contract": self.contract,
            },
        )

    def close(self) -> None:
        if self.sock:
            self.sock.close()
            self.sock = None


def _bars_from_df(df, start: int = 0, count: int | None = None):
    bars = []
    n = count or len(df)
    for i in range(start, min(start + n, len(df))):
        ts = df.index[i].to_pydatetime().replace(tzinfo=timezone.utc)
        row = df.iloc[i]
        bars.append(Bar(ts, float(row.open), float(row.high), float(row.low), float(row.close), float(row.volume)))
    return bars


class TestTimestampConversion(unittest.TestCase):
    def test_parse_utc_z_suffix(self):
        dt = parse_utc("2026-09-06T21:29:00Z")
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.hour, 21)
        self.assertEqual(dt.minute, 29)

    def test_bar_message_floor_minute(self):
        msg = {
            "type": "bar",
            "ts_utc": "2026-09-06T21:29:45Z",
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
            "volume": 10,
        }
        bar = bar_from_message(msg)
        self.assertEqual(bar.timestamp.second, 0)

    def test_parse_line_strips_utf8_bom(self):
        msg = parse_line('\ufeff{"type":"hello","seq":0,"auth":"x","contract":"NQ 09-26"}')
        self.assertEqual(msg["type"], "hello")


class TestNinjaTraderLiveProvider(unittest.TestCase):
    def setUp(self):
        self.port = _free_port()
        self.token = "test-secret-token"
        self.received: list[Bar] = []
        self.provider = NinjaTraderLiveDataProvider(
            host="127.0.0.1",
            port=self.port,
            auth_token=self.token,
            bootstrap_bars=15,
            expected_contract_prefix="NQ",
            on_bar=lambda b: self.received.append(b),
        )
        self.provider.connect()
        time.sleep(0.05)
        self.client = MockNTClient("127.0.0.1", self.port, self.token)

    def tearDown(self):
        self.client.close()
        self.provider.disconnect()

    def test_auth_required(self):
        bad = MockNTClient("127.0.0.1", self.port, "wrong-token")
        with self.assertRaises(RuntimeError):
            bad.connect()

    def test_atr_bootstrap_and_readiness(self):
        df = _synthetic_bars(30)
        bars = _bars_from_df(df, count=30)
        self.client.connect()
        for bar in bars[:10]:
            ack = self.client.send_bar(bar)
            self.assertTrue(ack.get("ok"), ack)
            time.sleep(0.005)
        self.assertFalse(self.provider.atr_ready)
        for bar in bars[10:20]:
            ack = self.client.send_bar(bar)
            self.assertTrue(ack.get("ok"), ack)
            time.sleep(0.005)
        self.assertTrue(self.provider.atr_ready)
        self.assertEqual(self.provider.health().state, DataHealth.DATA_HEALTHY)

    def test_atr_parity_with_stream_provider(self):
        df = _synthetic_bars(40)
        stream = StreamLiveDataProvider(df)
        stream.connect()
        self.client.connect()
        bars = _bars_from_df(df, count=40)
        for bar in bars:
            self.client.send_bar(bar)
            stream.advance()
            time.sleep(0.005)
        self.assertAlmostEqual(self.provider.atr(), stream.atr(), places=6)

    def test_provider_interchangeability(self):
        df = _synthetic_bars(30)
        ok, errs = compare_replay_live_parity(df, n_bars=25)
        self.assertTrue(ok, errs)
        self.client.connect()
        for bar in _bars_from_df(df, count=25):
            ack = self.client.send_bar(bar)
            self.assertTrue(ack.get("ok"), ack)
        nt_last = self.provider.latest_bar()
        stream = StreamLiveDataProvider(df)
        stream.connect()
        for _ in range(24):
            stream.advance()
        stream_last = stream.latest_bar()
        self.assertIsNotNone(nt_last)
        self.assertIsNotNone(stream_last)
        self.assertEqual(nt_last.timestamp, stream_last.timestamp)
        self.assertAlmostEqual(nt_last.close, stream_last.close, places=6)

    def test_duplicate_rejected(self):
        df = _synthetic_bars(5)
        self.client.connect()
        bar = _bars_from_df(df, count=1)[0]
        self.assertTrue(self.client.send_bar(bar).get("ok"))
        ack = self.client.send_bar(bar)
        self.assertFalse(ack.get("ok"))
        self.assertIn("DUPLICATE", ack.get("detail", ""))

    def test_out_of_order_seq_rejected(self):
        df = _synthetic_bars(5)
        self.client.connect()
        bar = _bars_from_df(df, count=1)[0]
        self.client.send_bar(bar)
        ack = _send_line(
            self.client.sock,
            {
                "type": "bar",
                "seq": 1,
                "ts_utc": (bar.timestamp + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.5,
                "volume": 1,
                "contract": "NQ 09-26",
            },
        )
        self.assertFalse(ack.get("ok"))

    def test_stale_health_after_disconnect(self):
        df = _synthetic_bars(20)
        self.client.connect()
        for bar in _bars_from_df(df, count=20):
            self.client.send_bar(bar)
        self.client.close()
        time.sleep(0.1)
        self.provider._handle_disconnect()
        self.assertEqual(self.provider.health().state, DataHealth.DATA_MISSING)
        self.assertEqual(self.provider.health().detail, "DATA_DISCONNECTED")

    def test_restart_requires_reauth(self):
        df = _synthetic_bars(40)
        self.client.connect()
        for bar in _bars_from_df(df, count=16):
            self.client.send_bar(bar)
        self.client.close()
        time.sleep(0.05)
        self.provider._handle_disconnect()
        self.assertFalse(self.provider.atr_ready)
        client2 = MockNTClient("127.0.0.1", self.port, self.token)
        client2.connect()
        for bar in _bars_from_df(df, start=16, count=20):
            client2.send_bar(bar)
            time.sleep(0.005)
        self.assertTrue(self.provider.atr_ready)
        client2.close()

    def test_contract_mismatch_fail_closed(self):
        self.provider.disconnect()
        port = _free_port()
        provider = NinjaTraderLiveDataProvider(
            host="127.0.0.1",
            port=port,
            auth_token=self.token,
            bootstrap_bars=5,
            expected_contract_prefix="NQ",
        )
        provider.connect()
        time.sleep(0.05)
        bad = MockNTClient("127.0.0.1", port, self.token, contract="ES 09-26")
        bad.connect()
        time.sleep(0.05)
        from phase74.market_data.connection import ConnectionState

        self.assertEqual(provider.connection_state, ConnectionState.DATA_DISCONNECTED)
        provider.disconnect()
        bad.close()


class TestNinjaTraderSafetyScan(unittest.TestCase):
    def test_no_order_apis_in_ninjascript(self):
        self.assertTrue(CS_BRIDGE.exists(), f"missing {CS_BRIDGE}")
        text = CS_BRIDGE.read_text(encoding="utf-8")
        hits = []
        for api in FORBIDDEN_ORDER_APIS:
            if re.search(rf"\b{re.escape(api)}\b", text):
                hits.append(api)
        self.assertEqual(hits, [], f"forbidden order APIs found: {hits}")

    def test_config_safety_defaults(self):
        cfg = load_phase74_config()
        self.assertFalse(cfg.trading_enabled)
        self.assertTrue(cfg.shadow_mode)
        self.assertFalse(cfg.external_order_routing)


class TestFreezeGuard(unittest.TestCase):
    def test_phase73_freeze_unchanged(self):
        ok, errs = verify_phase73_freeze()
        self.assertTrue(ok, errs)


if __name__ == "__main__":
    unittest.main()
