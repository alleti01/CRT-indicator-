"""Local webhook receiver for development (127.0.0.1 only)."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

from phase73.config.loader import Phase73Config
from phase73.webhook.deduplicator import SignalDeduplicator
from phase73.webhook.schemas import WebhookReason, PineSignal
from phase73.webhook.validator import validate_webhook_payload


SignalHandler = Callable[[PineSignal, WebhookReason], None]
ErrorHandler = Callable[[dict, WebhookReason, str], None]


class WebhookReceiver:
    def __init__(
        self,
        cfg: Phase73Config,
        on_signal: SignalHandler,
        on_reject: ErrorHandler | None = None,
        deduplicator: SignalDeduplicator | None = None,
    ) -> None:
        self.cfg = cfg
        self.on_signal = on_signal
        self.on_reject = on_reject or (lambda _p, _r, _d: None)
        self.deduplicator = deduplicator or SignalDeduplicator(cfg.log_dir / "signal_ids.jsonl")
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def handle_payload(self, payload: dict, now: datetime | None = None) -> tuple[bool, WebhookReason, str]:
        result = validate_webhook_payload(payload, self.cfg, now=now)
        if not result.ok:
            self.on_reject(payload, result.reason, result.detail)
            return False, result.reason, result.detail

        assert result.signal is not None
        dup = self.deduplicator.check_and_record(result.signal.signal_id)
        if dup:
            self.on_reject(payload, dup, "duplicate signal_id")
            return False, dup, "duplicate signal_id"

        self.on_signal(result.signal, WebhookReason.WEBHOOK_VALID)
        return True, WebhookReason.WEBHOOK_VALID, ""

    def start(self, host: str | None = None, port: int | None = None) -> None:
        host = host or str(self.cfg.section("webhook").get("host", "127.0.0.1"))
        port = int(port or self.cfg.section("webhook").get("port", 8787))
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args) -> None:  # noqa: A003
                return

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/webhook":
                    self.send_response(404)
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                try:
                    payload = json.loads(body.decode())
                except json.JSONDecodeError:
                    receiver.on_reject({}, WebhookReason.WEBHOOK_INVALID, "json decode")
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":false,"reason":"WEBHOOK_INVALID"}')
                    return

                ok, reason, _ = receiver.handle_payload(payload)
                self.send_response(200 if ok else 409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": ok, "reason": reason.value}).encode())

        self._server = HTTPServer((host, port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
