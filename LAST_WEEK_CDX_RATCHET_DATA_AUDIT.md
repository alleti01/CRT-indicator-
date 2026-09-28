# Last-week CDX ratchet data audit

Period: Monday Sep 22, 2026 through Saturday Sep 26, 2026. Times in the week list are America/New_York. No Sep 27 or Sep 28 trade is in this set.

No production file was changed for this check.

## What exists

| Item | Source | Result |
|---|---|---|
| Accepted CDX signals | `phase74/logs/signals.csv` and `LAST_WEEK_SIGNAL_SOURCE_AUDIT.md` | 15 webhook/fill pairs |
| Actual fills | `phase85/logs/audit.jsonl` | 15 fills |
| Actual exits with both prices | Account week list | 11 |
| 1-minute bars | `phase74/logs/bars.csv` | Present from Sep 22 00:00 UTC through the week |
| 3-minute bars | Built in the earlier replay from those 1-minute bars | Not stored as their own file |
| Exact CDX Entry, SL, and TP1 | `forward_rehearsal/cdx_native_levels.csv`, `cdx_vision/logs/vision_levels.jsonl` | None inside Sep 22–26 |

The earlier last-week file `LAST_WEEK_REPLAY.csv` leaves `cdx_native_stop_if_known` blank on every row. The signal audit says no alert stored a CDX stop.

## Native levels that exist, and why they are excluded

| Prices | When | Why excluded |
|---|---|---|
| Entry 30909.50, SL 30947.00, TP1 30872.00, TP2 30845.00 | Sep 27 | After the week |
| Entry 30796.25, SL 30863.75 on the chart, TP1 30717.75, TP2 30684.00 | Sep 27–28 | After the week. The stored stop 30803 was an OCR miss and is not used |

## Screenshots

`cdx_vision/fixtures/real/cdx_real_01.png` is the Sep 27 short above.

`cdx_real_02.png` through `cdx_real_06.png` are earlier TradingView shots. Their dates are before Sep 22, and the exact Entry, SL, and TP1 numbers were not transcribed. They are not assigned to any last-week fill.

## Coverage

15 last-week live fills. 11 have both an entry price and an exit price. 0 have an exact CDX Entry, SL, and TP1.

Coverage of the ratchet test: 0%.
