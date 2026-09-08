"""Localhost TCP server — accepts read-only bar feed from NinjaTrader bridge."""
from __future__ import annotations

import json
import logging
import socket
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from phase73.market_data.bar import Bar

from .protocol import bar_from_message, encode_ack, hello_from_message, parse_line

log = logging.getLogger("phase74.ninjatrader.server")


@dataclass
class BridgeStats:
    bars_received: int = 0
    duplicates_rejected: int = 0
    out_of_order_rejected: int = 0
    auth_failures: int = 0
    last_bar_latency_ms: float = 0.0
    last_seq: int = -1
    connected_at: datetime | None = None
    contract: str = ""


class NinjaTraderBridgeServer:
    """
    Python-side listener. NinjaTrader CRTBarBridge indicator connects as TCP client.
    Authentication required on first hello message. Fail-closed on auth mismatch.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        *,
        auth_token: str,
        on_bar: Callable[[Bar, BridgeStats], None] | None = None,
        on_authenticated: Callable[[str], None] | None = None,
        on_disconnect: Callable[[], None] | None = None,
        trust_localhost: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self.trust_localhost = trust_localhost
        self._on_bar = on_bar
        self._on_authenticated = on_authenticated
        self._on_disconnect = on_disconnect
        self._sock: socket.socket | None = None
        self._client: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._accept_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._authenticated = False
        self._client_addr: tuple[str, int] | None = None
        self.stats = BridgeStats()
        self._last_bar_ts: datetime | None = None
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._authenticated

    def start(self) -> None:
        if self._sock is not None:
            return
        self._stop.clear()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(1)
        self._sock.settimeout(1.0)
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True, name="nt-bridge-accept")
        self._accept_thread.start()
        log.info("ninjatrader bridge listening %s:%s", self.host, self.port)

    def stop(self) -> None:
        self._stop.set()
        if self._client:
            try:
                self._client.close()
            except OSError:
                pass
            self._client = None
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._authenticated = False
        if self._on_disconnect:
            self._on_disconnect()

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                client, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            log.info("ninjatrader bridge client connected from %s", addr)
            if self._client:
                try:
                    self._client.close()
                except OSError:
                    pass
            self._client = client
            self._client_addr = addr
            self._client.settimeout(1.0)
            self._authenticated = False
            with self._lock:
                self.stats = BridgeStats()
            self._thread = threading.Thread(target=self._read_loop, daemon=True, name="nt-bridge-read")
            self._thread.start()

    def _read_loop(self) -> None:
        client = self._client
        if client is None:
            return
        buf = b""
        try:
            while not self._stop.is_set():
                try:
                    chunk = client.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    self._handle_line(line.decode("utf-8", errors="replace"))
        except OSError as exc:
            log.warning("ninjatrader bridge read error: %s", type(exc).__name__)
        finally:
            log.info("ninjatrader bridge client disconnected")
            try:
                client.close()
            except OSError:
                pass
            if self._client is client:
                self._client = None
            self._client_addr = None
            self._authenticated = False
            if self._on_disconnect:
                self._on_disconnect()

    def _handle_line(self, line: str) -> None:
        client = self._client
        if client is None:
            return
        try:
            msg = parse_line(line)
        except (ValueError, json.JSONDecodeError) as exc:
            log.warning("invalid message: %s", exc)
            client.sendall(encode_ack(ok=False, detail="PARSE_ERROR").encode("utf-8"))
            return

        mtype = msg.get("type")
        if mtype == "hello":
            hello = hello_from_message(msg)
            if hello.auth != self.auth_token:
                local_trusted = (
                    self.trust_localhost
                    and self._client_addr is not None
                    and self._client_addr[0] in ("127.0.0.1", "::1")
                )
                if not local_trusted:
                    with self._lock:
                        self.stats.auth_failures += 1
                    log.warning(
                        "ninjatrader bridge auth failed (sent_len=%s, expected_len=%s)",
                        len(hello.auth or ""),
                        len(self.auth_token or ""),
                    )
                    client.sendall(encode_ack(ok=False, detail="AUTH_FAILED", seq=hello.seq).encode("utf-8"))
                    client.close()
                    self._client = None
                    self._client_addr = None
                    self._authenticated = False
                    return
                log.warning(
                    "ninjatrader bridge auth mismatch accepted (trust_localhost, sent_len=%s)",
                    len(hello.auth or ""),
                )
            self._authenticated = True
            with self._lock:
                self.stats.connected_at = datetime.now(timezone.utc)
                self.stats.contract = hello.contract
                self.stats.last_seq = hello.seq
            client.sendall(encode_ack(ok=True, detail="OK", seq=hello.seq).encode("utf-8"))
            if self._on_authenticated:
                self._on_authenticated(hello.contract)
            return

        if not self._authenticated:
            client.sendall(encode_ack(ok=False, detail="NOT_AUTHENTICATED").encode("utf-8"))
            return

        if mtype == "heartbeat":
            return

        if mtype == "bar":
            seq = int(msg.get("seq", -1))
            with self._lock:
                if seq <= self.stats.last_seq and self.stats.last_seq >= 0:
                    self.stats.out_of_order_rejected += 1
                    client.sendall(encode_ack(ok=False, detail="OUT_OF_ORDER_SEQ", seq=seq).encode("utf-8"))
                    return
            try:
                bar = bar_from_message(msg)
            except (KeyError, ValueError, TypeError) as exc:
                client.sendall(encode_ack(ok=False, detail=str(exc), seq=seq).encode("utf-8"))
                return
            with self._lock:
                if self._last_bar_ts is not None and bar.timestamp <= self._last_bar_ts:
                    self.stats.duplicates_rejected += 1
                    client.sendall(encode_ack(ok=False, detail="DUPLICATE_OR_OOO_TS", seq=seq).encode("utf-8"))
                    return
                self._last_bar_ts = bar.timestamp
                self.stats.last_seq = seq
                received = datetime.now(timezone.utc)
                bar_close = bar.timestamp.replace(tzinfo=timezone.utc)
                bar_close_time = bar_close + timedelta(minutes=1)
                self.stats.last_bar_latency_ms = max(0.0, (received - bar_close_time).total_seconds() * 1000)
                self.stats.bars_received += 1
            client.sendall(encode_ack(ok=True, detail="BAR", seq=seq).encode("utf-8"))
            if self._on_bar:
                self._on_bar(bar, self.stats)
            return

        client.sendall(encode_ack(ok=False, detail=f"UNKNOWN_TYPE:{mtype}").encode("utf-8"))
