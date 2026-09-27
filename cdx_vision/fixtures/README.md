# CDX vision fixtures

Place a real TradingView screenshot here when the CDX Entry, SL, TP1, and TP2 text is readable.

Suggested name: `cdx_short_30909.png`

Known example to check by hand, not invented as an image in this repo:

- direction SHORT
- entry 30909.50
- stop 30947.00
- TP1 30872.00
- TP2 30845.00

The parser tests use those numbers as OCR tokens. They do not pretend a screenshot exists.

A sidecar `image.tokens.json` next to a saved screenshot can be read by:

    python -m cdx_vision.inspect_capture path/to/image.png
