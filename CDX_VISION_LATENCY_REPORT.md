# CDX vision latency

No live capture burst has been timed against TradingView. The service is idle until a webhook arrives, and only if `CDX_VISION_ENABLED=true`.

The timeout default is 5 seconds from `webhook_received_at` to the read. A request older than the process start is `VISION_REJECT_RESTART_STALE`. A request older than 5 seconds is `VISION_TIMEOUT`.

T0 through T5 will be filled from `cdx_vision/logs/vision_levels.jsonl` after the first enabled shadow sessions. Do not tune the timeout before those rows exist.
