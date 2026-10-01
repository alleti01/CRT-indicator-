# TP2 extraction audit

Entry 30812.00, SL 30785.50, and TP1 30838.50 were already read from the main chart crop. TP2 was not.

The TP2 pixels are in that crop. The loss is later: the green target line runs through the same rows as the words `TP2 30871.75`. A tall crop makes Tesseract read the first digit as 2 (`20671.75` or `P2`) and drop the letters TP2, so the parser never receives a TP2 label.

The fix is a separate 16-pixel band just above that green line, upscaled 6x. On the saved LONG capture that band OCRs as `TP2 30871.75`. The price is not filled in. A read that does not contain the letters TP2 is ignored, including a bare price-scale number.
