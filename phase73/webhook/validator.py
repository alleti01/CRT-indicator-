"""Deterministic webhook payload validation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from phase73.config.loader import Phase73Config
from phase73.webhook.schemas import (
    SCHEMA_VERSION,
    SIGNAL_EVENTS,
    WebhookReason,
    parse_signal_payload,
    PineSignal,
)

REQUIRED_FIELDS = (
    "schema_version",
    "strategy",
    "pine_hash",
    "signal_id",
    "event",
    "symbol",
    "timeframe",
    "signal_time_utc",
    "signal_bar_time_utc",
    "signal_price",
    "atr",
    "evidence",
)


@dataclass
class ValidationResult:
    ok: bool
    reason: WebhookReason
    signal: PineSignal | None = None
    detail: str = ""


def validate_webhook_payload(
    payload: dict[str, Any],
    cfg: Phase73Config,
    *,
    now: datetime | None = None,
) -> ValidationResult:
    now = now or datetime.now(timezone.utc)

    if not isinstance(payload, dict):
        return ValidationResult(False, WebhookReason.WEBHOOK_INVALID, detail="payload not object")

    for field in REQUIRED_FIELDS:
        if field not in payload:
            return ValidationResult(False, WebhookReason.WEBHOOK_INVALID, detail=f"missing {field}")

    if str(payload["schema_version"]) != SCHEMA_VERSION:
        return ValidationResult(
            False, WebhookReason.WEBHOOK_INVALID, detail=f"schema {payload['schema_version']}"
        )

    event = str(payload["event"])
    if event not in SIGNAL_EVENTS and event not in {"EXIT_STOP", "EXIT_TARGET", "ENTER_LONG", "ENTER_SHORT"}:
        return ValidationResult(False, WebhookReason.WEBHOOK_INVALID, detail=f"unknown event {event}")

    if str(payload["symbol"]).upper() != cfg.symbol.upper():
        return ValidationResult(False, WebhookReason.SIGNAL_WRONG_SYMBOL, detail=str(payload["symbol"]))

    if str(payload["timeframe"]) != cfg.timeframe:
        return ValidationResult(False, WebhookReason.SIGNAL_WRONG_TIMEFRAME, detail=str(payload["timeframe"]))

    if str(payload["pine_hash"]) != cfg.pine_hash:
        return ValidationResult(False, WebhookReason.SIGNAL_HASH_MISMATCH, detail="pine_hash mismatch")

    try:
        signal = parse_signal_payload(payload, received_at=now)
    except (KeyError, TypeError, ValueError) as exc:
        return ValidationResult(False, WebhookReason.WEBHOOK_INVALID, detail=str(exc))

    age = (now - signal.signal_time_utc).total_seconds()
    if age > cfg.webhook_staleness_limit_seconds:
        return ValidationResult(False, WebhookReason.SIGNAL_STALE, signal=signal, detail=f"age={age:.0f}s")

    return ValidationResult(True, WebhookReason.WEBHOOK_VALID, signal=signal)
