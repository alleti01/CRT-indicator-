# End to end

`python -m cdx_vision.test_trigger --side SHORT --price 30909.50` ran the same function the webhook thread calls.

Result written to `cdx_vision/logs/vision_levels.jsonl`:

- signal_id TEST_21330526a111
- direction SHORT
- entry 30909.50 source WEBHOOK
- stop 30947.00
- tp1 30872.00
- tp2 30845.00
- status VISION_CONFIRMED
- agreeing frames 2

No order function was called. `CDX_VISION_ENABLED` on the running bot remains false, so the next real webhook will not capture until that flag is turned on. The worker path itself ran and wrote the ledger.
