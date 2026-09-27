# CDX vision current architecture

Inspection only. The live order path was not changed except for a disabled-by-default call that returns immediately when `CDX_VISION_ENABLED` is false.

## Webhook entry

`phase74/webhook/secure_receiver.py`, `SecureWebhookReceiver.handle_payload`.

Auth, rate limit, and `phase73/webhook/validator.py` `validate_webhook_payload` run first. A valid signal is deduplicated by `signal_id` in `phase73/webhook/deduplicator.py`. Then `on_signal` runs the existing Phase74 stack.

## Signal object

`phase73/webhook/schemas.py` `PineSignal`.

The id is the webhook field `signal_id`. Direction is `SIGNAL_LONG` or `SIGNAL_SHORT` via `PineSignal.direction`. Price is `signal_price`. Time is `signal_time_utc`. The `timeframe` field is `1m` even when the CDX chart is 3-minute, because the validator rejects any other timeframe.

## Decision and execution

`phase74/runtime/live_stack.py` `on_webhook_signal` decides the trade. `phase85/execution/adapter.py` routes the NinjaTrader order when execution is enabled. Vision is not on that path.

## Safe integration point

After `on_signal` returns, `secure_receiver` calls `cdx_vision.shadow_hook.enqueue_shadow`. That function returns immediately unless `CDX_VISION_ENABLED=true`. It has no order client. `VisionConfig.may_route_orders` is hard-coded false for this build.

Logging stays on the existing `logging` loggers (`phase74.webhook`, `cdx_vision.service`). The vision ledger is separate and append-only: `cdx_vision/logs/vision_levels.jsonl`.
