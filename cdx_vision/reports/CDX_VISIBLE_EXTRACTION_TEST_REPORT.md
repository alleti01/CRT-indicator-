# Visible extraction tests

`cdx_vision.tests.test_visible_extract`, `test_harden`, and `test_order_gate`: 30 passed.

Covered:

- MNQ1!, MNQ 12-26, and NQ1! accepted; ES1! rejected
- off-screen route may pan; a visible CDX marker does not
- a line-linked tag becomes SL or a target only on the correct side of entry
- a green tag with no CDX line is not a level
- label OCR and tag OCR disagreement is `VISION_LEVEL_CONFLICT`
- off-tick text such as 30575.80 is rejected
- the golden NQ short fixture still resolves 30909.50 / 30947.00 / 30872.00 / 30845.00
- one no-movement Ctrl+Right stops navigation
- vision still cannot place an order

No execution call is made by the inspector or the tag reader.
