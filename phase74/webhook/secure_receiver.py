"""Secure webhook receiver with auth, rate limiting, logging."""
from __future__ import annotations

import json
import logging
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Callable

from phase73.config.loader import Phase73Config
from phase73.webhook.deduplicator import SignalDeduplicator
from phase73.webhook.schemas import PineSignal, WebhookReason
from phase73.webhook.validator import validate_webhook_payload
from phase74.latency.tracker import LatencyTracker

log = logging.getLogger("phase74.webhook")


class RateLimiter:
    def __init__(self, max_per_minute: int = 60) -> None:
        self.max_per_minute = max_per_minute
        self._hits: deque[float] = deque()

    def allow(self) -> bool:
        now = time.time()
        while self._hits and now - self._hits[0] > 60:
            self._hits.popleft()
        if len(self._hits) >= self.max_per_minute:
            return False
        self._hits.append(now)
        return True


SignalCallback = Callable[[PineSignal, WebhookReason, LatencyTracker], None]
RejectCallback = Callable[[dict, WebhookReason, str], None]


class SecureWebhookReceiver:
    def __init__(
        self,
        cfg: Phase73Config,
        secret: str,
        on_signal: SignalCallback,
        on_reject: RejectCallback | None = None,
        deduplicator: SignalDeduplicator | None = None,
        rate_limit: int = 60,
    ) -> None:
        self.cfg = cfg
        self.secret = secret
        self.on_signal = on_signal
        self.on_reject = on_reject or (lambda _p, _r, _d: None)
        self.deduplicator = deduplicator or SignalDeduplicator(cfg.log_dir / "signal_ids.jsonl")
        self.rate_limiter = RateLimiter(rate_limit)
        self._server: HTTPServer | None = None
        self._thread: Thread | None = None

    def _auth_ok(self, headers) -> bool:
        if not self.secret:
            return False  # require secret in production dress rehearsal
        auth = headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:] == self.secret
        return headers.get("X-Webhook-Secret", "") == self.secret

    def handle_payload(self, payload: dict, *, headers: dict | None = None, received_at: datetime | None = None) -> tuple[bool, WebhookReason, str]:
        received_at = received_at or datetime.now(timezone.utc)
        tracker = LatencyTracker(webhook_received_at=received_at)

        if headers is not None and not self._auth_ok(headers):
            self.on_reject(payload, WebhookReason.WEBHOOK_INVALID, "auth failed")
            return False, WebhookReason.WEBHOOK_INVALID, "auth failed"

        if not self.rate_limiter.allow():
            self.on_reject(payload, WebhookReason.WEBHOOK_INVALID, "rate limit")
            return False, WebhookReason.WEBHOOK_INVALID, "rate limit"

        t0 = time.perf_counter()
        result = validate_webhook_payload(payload, self.cfg, now=received_at)
        tracker.webhook_validated_at = datetime.now(timezone.utc)
        tracker.webhook_validation_ms = (time.perf_counter() - t0) * 1000

        if not result.ok:
            log.info("webhook rejected reason=%s detail=%s", result.reason.value, result.detail)
            self.on_reject(payload, result.reason, result.detail)
            return False, result.reason, result.detail

        assert result.signal is not None
        dup = self.deduplicator.check_and_record(result.signal.signal_id)
        if dup:
            self.on_reject(payload, dup, "duplicate")
            return False, dup, "duplicate"

        if result.signal.signal_time_utc:
            tracker.pine_to_webhook_ms = (received_at - result.signal.signal_time_utc).total_seconds() * 1000

        log.info("webhook valid signal_id=%s event=%s", result.signal.signal_id, result.signal.event)
        self.on_signal(result.signal, WebhookReason.WEBHOOK_VALID, tracker)
        return True, WebhookReason.WEBHOOK_VALID, ""

    def start(self, host: str, port: int, path: str = "/webhook") -> None:
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args) -> None:
                return

            def do_POST(self) -> None:  # noqa: N802
                if self.path != path:
                    self.send_response(404)
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                try:
                    payload = json.loads(body.decode())
                except json.JSONDecodeError:
                    receiver.on_reject({}, WebhookReason.WEBHOOK_INVALID, "json")
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"ok":false}')
                    return
                hdrs = {k: v for k, v in self.headers.items()}
                ok, reason, _ = receiver.handle_payload(payload, headers=hdrs)
                self.send_response(200 if ok else 409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": ok, "reason": reason.value}).encode())

        self._server = HTTPServer((host, port), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        log.info("secure webhook listening %s:%s%s", host, port, path)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
