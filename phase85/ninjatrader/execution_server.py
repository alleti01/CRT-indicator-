"""Python listener for CRTExecutionBridge. Same polarity as the bar bridge: NT connects out."""
from __future__ import annotations

import hmac
import logging
import socket
import threading
from collections import deque
from typing import Callable

from phase85.protocol.codec import ProtocolError, decode_line, encode_message, event_from_dict
from phase85.protocol.messages import Command, Event

log = logging.getLogger("phase85.execution_server")


class ExecutionBridgeServer:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        auth_token: str,
        on_event: Callable[[Event], None] | None = None,
        on_auth: Callable[[], None] | None = None,
        on_hello: Callable[[str, str], None] | None = None,
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("execution bridge must bind localhost")
        if not auth_token:
            raise ValueError("execution token required")
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self._on_event = on_event
        self._on_auth = on_auth
        self._on_hello = on_hello
        self._on_disconnect = on_disconnect
        self.connected = False
        self.authenticated = False
        self._sock: socket.socket | None = None
        self._client: socket.socket | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._outbound: deque[str] = deque()

    def start(self) -> None:
        self._stop.clear()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(1)
        self._sock.settimeout(1.0)
        threading.Thread(target=self._accept_loop, daemon=True, name="p85-exec-accept").start()
        log.info("phase85 execution bridge listening %s:%s", self.host, self.port)

    def stop(self) -> None:
        self._stop.set()
        if self._client:
            try:
                self._client.close()
            except OSError:
                pass
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        self.connected = False
        self.authenticated = False

    def send_command(self, command: Command) -> None:
        line = encode_message(command.to_dict())
        with self._lock:
            self._outbound.append(line)
        self._flush()

    def _flush(self) -> None:
        client = self._client
        if client is None or not self.authenticated:
            return
        with self._lock:
            while self._outbound:
                line = self._outbound.popleft()
                try:
                    client.sendall(line.encode("utf-8"))
                except OSError:
                    self.authenticated = False
                    return

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                client, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if addr[0] not in {"127.0.0.1", "::1"}:
                log.warning("rejected non-local execution client")
                client.close()
                continue
            if self._client:
                try:
                    self._client.close()
                except OSError:
                    pass
            self._client = client
            self.connected = True
            self.authenticated = False
            client.settimeout(1.0)
            threading.Thread(target=self._read_loop, daemon=True, name="p85-exec-read").start()

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
                    self._flush()
                    continue
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.strip():
                        self._handle_line(line.decode("utf-8", errors="replace"))
        except OSError:
            log.warning("execution bridge read error")
        finally:
            self.connected = False
            self.authenticated = False
            if self._on_disconnect:
                self._on_disconnect()

    def _handle_line(self, line: str) -> None:
        client = self._client
        if client is None:
            return
        try:
            obj = decode_line(line)
        except ProtocolError:
            client.sendall(encode_message({"type": "ack", "ok": False, "detail": "MALFORMED_JSON"}).encode("utf-8"))
            return
        if obj.get("type") == "hello":
            auth = str(obj.get("auth", ""))
            if not hmac.compare_digest(auth, self.auth_token):
                client.sendall(encode_message({"type": "ack", "ok": False, "detail": "AUTH_FAILED"}).encode("utf-8"))
                client.close()
                self._client = None
                self.authenticated = False
                return
            self.authenticated = True
            client.sendall(encode_message({"type": "ack", "ok": True, "detail": "OK"}).encode("utf-8"))
            if self._on_hello:
                self._on_hello(str(obj.get("account", "")), str(obj.get("instrument", "")))
            if self._on_auth:
                self._on_auth()
            self._flush()
            return
        if not self.authenticated:
            client.sendall(encode_message({"type": "ack", "ok": False, "detail": "NOT_AUTHENTICATED"}).encode("utf-8"))
            return
        if "event" in obj:
            try:
                ev = event_from_dict(obj)
            except ProtocolError:
                return
            if self._on_event:
                self._on_event(ev)
            return
        # ignore unexpected
        return
