# Hardening

The entry reader, the SL/TP reader, schema version 2, and the order ban are unchanged in behavior on the golden chart.

Added:

- Active-trade selection by x position, webhook direction, and webhook price.
- Rejection of alert, HTF, performance, and bare scale text.
- Ctrl+Right recovery, off by default, with a foreground check before every key.
- Ledger fields for whether the first capture already showed the trade, and for how many pans were sent.
- One acquisition job per `signal_id` while a capture is in flight.
- `python -m cdx_vision.inspect_capture` with `--side` and `--webhook-price`.
- `python -m cdx_vision.test_auto_right`.

The golden image still reads Entry 30909.50, SL 30947.00, TP1 30872.00, TP2 30845.00, source VISION.

The live chart, after three pans, did not present a confirmable current level set. That row was rejected. No order was sent.
