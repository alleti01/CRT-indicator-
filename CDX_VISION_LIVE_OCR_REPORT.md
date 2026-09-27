# Live OCR

The open chart is a CDX short. Tesseract read the label column as:

- SL 30947.00
- TP1 30872.00
- TP2 30845.00

Those match the chart exactly, on the 0.25 tick.

The faint "CDX ENTRY 30909.50" line was not read. The test trigger supplied 30909.50, and the ledger marks `entry_source` as WEBHOOK. The stop and both targets came from the screen.

Geometry for that set: 30947.00 > 30909.50 > 30872.00 > 30845.00. Stop distance 37.50 points. TP1 is 1.00R. TP2 is 1.72R.

Two consecutive frames agreed. Status VISION_CONFIRMED. Signal id `TEST_21330526a111`.
