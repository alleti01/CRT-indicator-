# CDX vision build

Shadow only. Vision cannot place, change, or cancel an order.

## What was built

`cdx_vision/` reads CDX Entry, SL, TP1, and TP2 from OCR tokens, checks NQ tick size and long/short order, and requires two consecutive frames to agree. A single disagreeing frame in the middle is rejected even if another frame matches. The webhook direction is not overridden.

Live capture uses the Win32 window list and `PrintWindow`. OCR is a plug-in. This machine does not have Tesseract, and no cloud OCR is used. A live chart read therefore fails closed with `VISION_NO_CDX_TEXT` until a local OCR engine is connected. Tests inject tokens so the parser does not depend on that.

`CDX_VISION_ENABLED` defaults to false. With the flag off, the webhook path does not start a capture.

## Known example, as tokens

SHORT entry 30909.50, SL 30947.00, TP1 30872.00, TP2 30845.00.

Stop distance 37.50 points. TP1 distance 37.50 points, 1.00R. TP2 distance 64.50 points, 1.72R. At 1 NQ that stop is $750. At 1 MNQ it is $75. No order is sized from this.

No screenshot of that example is in the repo. See `cdx_vision/fixtures/README.md`.
