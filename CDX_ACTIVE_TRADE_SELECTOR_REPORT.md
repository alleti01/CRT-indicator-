# Active trade selector

The selector lives in `cdx_vision/active_trade_selector.py`.

A level cluster whose center is left of 45 percent of the OCR crop is historical. It is not chosen, even when its entry matches the webhook price.

When an old short at 29709.50 sits on the left and the known short at 30909.50 sits on the right, the webhook price 30910 selects the right-hand trade.

When only the left-hand trade is present, the result is `VISION_REJECT_STALE_TRADE_LEVELS`. The old stop is not written as the current trade.

Two different current sets whose x centers are within 80 pixels produce `VISION_AMBIGUOUS_LEVEL_SET`.

A current cluster marked `CDX LONG` is rejected when the webhook says SHORT.

Alert, HTF, and performance tokens, clock times, and a bare scale price do not become Entry, SL, TP1, or TP2. The known short next to those tokens is still read as 30947 / 30909.50 / 30872 / 30845.
