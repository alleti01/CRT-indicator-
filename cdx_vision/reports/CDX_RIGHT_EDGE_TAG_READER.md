# Right-edge tag reader

Window fractions:

| Region | Box |
| --- | --- |
| Old label OCR | 0.18, 0.10, 0.78, 0.88 |
| Chart lines | 0.08, 0.12, 0.72, 0.78 |
| Level labels | 0.18, 0.18, 0.70, 0.70 |
| Right-edge tags | 0.60, 0.16, 0.80, 0.72 |
| Price-scale exclusion | 0.78, 0.10, 0.84, 0.80 |
| Alerts panel exclusion | 0.80, 0.00, 1.00, 1.00 |

A tag is a compact colored rectangle. A line is a long near-horizontal run of the same color family. The tag price is OCR of that rectangle only. Screen Y is not converted into a price.

On the saved MNQ capture the reader found:

- 30658.25, green, tied to a green line
- 30617.03, rejected, off the 0.25 tick
- 30575.80, rejected, off the 0.25 tick
- a green tag with no line, rejected as a current-price tag

30658.25 is below the 8:42 webhook entry 30730.25. For a long, targets must be above the entry, so this tag is not TP1, TP2, or SL. No red on-tick tag was found, so SL is missing. The quartet stays unconfirmed.
