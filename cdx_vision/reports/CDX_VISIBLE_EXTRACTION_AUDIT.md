# Visible extraction audit

The 8:42 AM MNQ long failed before any level was confirmed.

## What the code did

The webhook was valid. The first capture of TradingView MNQ1! did not produce Entry, SL, TP1, and TP2, so auto-right sent Ctrl+Right. The chart was already on the live bars, so the picture did not change. The reader stopped with `VISION_AUTO_RIGHT_NO_MOVEMENT` and sent no order.

## Answers

The 30,658.25 tag was inside the old OCR crop (window fraction 0.18–0.78). It was not clipped by that ROI.

MNQ was not rejected. The request ticker was MNQ, and no symbol check dropped it.

OCR saw fragments of the tag and, on the saved capture, the dedicated tag reader reads `30658.25` exactly. It was not assigned to TP1 or TP2. There is no TP1/TP2 word next to it. It sits on a green line below the webhook entry 30730.25, so it cannot be a long target.

A red line was detected. No on-tick red price tag was read, so there is no SL candidate.

There was no Entry text candidate. The webhook entry remains only a fallback, and the fallback is not used unless SL, TP1, and TP2 are all confirmed.

Nothing was rejected as a stale historical trade. Active-trade selection never ran, because no quartet was built. Geometry and two-frame consensus were not reached.

## Routing change

If the capture already contains a CDX LONG or CDX SHORT marker, the reader does not pan. It reads right-edge tags that sit on a detected horizontal line. A tag with no line is not a CDX level. Off-tick text is rejected. A missing price is not guessed.
