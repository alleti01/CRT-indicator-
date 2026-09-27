# Live path audit

Accepted webhook: `phase74/webhook/secure_receiver.py` calls `on_signal` first, then `_shadow_cdx_levels`.

That hook calls `cdx_vision.shadow_hook.enqueue_shadow`. If `CDX_VISION_ENABLED` is false, it returns immediately and does not start a thread. The flag is still false, so the running bot does not capture on live signals.

When the flag is true, a daemon thread runs `cdx_vision.live_job.run_shadow_job` after the webhook has already returned. That job:

1. Finds `TradingView.exe` only.
2. Rejects a minimized window.
3. Captures with PrintWindow, and uses an MSS screen grab if that image is blank.
4. Crops the right-side label region.
5. Runs local Tesseract.
6. Parses and validates.
7. Requires two consecutive identical SL, TP1, and TP2.
8. Appends `cdx_vision/logs/vision_levels.jsonl` and `forward_rehearsal/cdx_native_levels.csv`.

There is no import of the NinjaTrader execution adapter anywhere in `cdx_vision`. A vision failure cannot cancel a stop or flatten a position.

The manual proof did not wait for a new webhook. `python -m cdx_vision.test_trigger` ran the same job against the open app.
