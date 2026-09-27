# CDX entry audit

## Before this change

The parser already recognized `CDX ENTRY` and `ENTRY`, and it could pair a label with a price on the same row. That path worked on a clean synthetic image.

On the live TradingView capture it did not. The stop and both targets are bright and sit in the right-hand label column. The entry label is a short, near-black line of text on the entry line itself. The same grayscale stretch that reads SL / TP1 / TP2 leaves that text too dark, so the frame had no visual entry.

When SL, TP1, and TP2 were valid and a webhook price was present, the validator filled `entry` from the webhook and set `entry_source` to `WEBHOOK`. There was no separate field for the visual price, the webhook price, and the fill. One `entry` field held whichever source won. The ledger schema was `1.0`.

No order code reads those fields.

## After this change

Priority is visual entry, then webhook, then an explicit fill. A missing visual entry does not get invented from the midpoint, the stop, or the current price.

The entry reader searches the right-hand label region for the near-black text, crops that band, and runs a fixed set of preprocesses: grayscale, inverted grayscale, dark-text stretch, the invert of that stretch, and CLAHE. A price is accepted only when at least two of those agree on the same tick-aligned value next to an Entry label. One dissenting price rejects the visual entry. The horizontal line is used only to find the crop.

Two consecutive frames must agree on that price before `entry_source` is `VISION`. If those frames agree on SL / TP1 / TP2 but not on the entry, the webhook price is used and the reason is `VISION_ENTRY_UNSTABLE`. If the entry text is simply absent, the reason is `VISION_ENTRY_NOT_FOUND_WEBHOOK_FALLBACK`. If neither visual nor webhook nor fill exists, the frame is `VISION_REJECT_ENTRY_UNAVAILABLE`.

A visual entry and a webhook price more than 100 points apart are both stored, and the row is marked `VISION_ENTRY_WEBHOOK_MISMATCH`. The visual price stays the native entry when it is the stable read. The 100-point band is only a flag. It does not place or cancel anything.

`entry` in the ledger is the native entry. Schema version 2 also stores `cdx_visual_entry`, `webhook_entry`, `actual_fill`, `entry_source`, native R source (`VISION` or `WEBHOOK_FALLBACK`), and the three signed differences. Older rows are left as written. A reader fills the new fields with blanks when they are absent.

## Known chart

The saved NQ screenshot reads:

- visual entry 30909.50
- SL 30947.00
- TP1 30872.00
- TP2 30845.00

`entry_source` is `VISION`. A test webhook of 30910.25 stayed in `webhook_entry` and was not copied over the visual price. Difference 0.75 points. Native R is 37.50 points from the visual entry and the stop. TP1 is 1.00R. TP2 is 1.72R.

The open app, at the time of the check, was on NQ around 30818 and did not have those labels on screen. That probe is a no-level result, not a failed read of this chart.

No vision path calls the NinjaTrader adapter.
