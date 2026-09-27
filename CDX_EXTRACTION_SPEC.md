# CDX extraction spec

Prices are `Decimal`. A price is accepted only when it is a positive multiple of 0.25. A digit string is never given a new decimal point.

## Entry

Labels: `CDX ENTRY`, `CDXENTRY`, `ENTRY`. A lone `CDX` token can pair with a price on the same row inside the entry reader only.

The entry crop is the band of near-black text in the right-hand label region (pixels with red, green, and blue all below 12, in a run 6 to 28 pixels tall). If that band is absent, the crop is the vertical midpoint between the SL and TP1 tokens.

Preprocesses, in order: grayscale autocontrast, its invert, dark stretch (`pixel * 8`), invert of that stretch, CLAHE. A variant that returns zero entry prices does not vote. A variant that returns two different prices rejects the visual entry. Acceptance requires at least two variants to return the same price.

The price must sit on the same row as the label, or within 1.5 label-heights and to its right. Two frames must show that same price before `entry_source` is `VISION`.

## SL

Label: `SL` (also `$L` from the earlier OCR misread). The price is on the label token or the nearest price token to its right on the same row. A red or pink horizontal line may be used later to choose the crop. It does not set the price.

## TP1

Label: `TP1`, `TP 1`, or `TPI`. Same row rule as SL. Green or teal may locate the band. The number still has to be read.

## TP2

Label: `TP2` or `TP 2`. Same rules as TP1. TP2 is not computed from TP1 or from R.

## Pairing

Each SL is paired with the TP1, TP2, and Entry whose box center is closest in x, then in y. Two different trades on the same chart stay separate.

## Active trade

The OCR crop's right edge is the current-bar side.

- Cluster center x / crop width `< 0.45`: historical. Status `STALE`. It cannot be the webhook trade.
- A `CDX LONG` or `CDX SHORT` marker within 220 px in x and 80 px in y of the cluster sets that cluster's direction. If it disagrees with the webhook direction, status `DIRECTION_CONFLICT`.
- If the webhook price is present, a visual entry more than 500 points away is `PRICE_FAR`. If the entry was not read, the stop or either target must be within 500 points of the webhook price.
- Remaining clusters are `CURRENT`. The one with the largest x is selected.
- If the top two `CURRENT` clusters have different stop/target prices and their x centers differ by less than 80 px, the result is `VISION_AMBIGUOUS_LEVEL_SET`.

No current cluster, and at least one stale cluster: `VISION_CURRENT_SIGNAL_OFFSCREEN`. That is the trigger for auto-right, together with no CDX text at all.

## Panels

These tokens are dropped before level parsing: a percent sign, `RSI`, `WIN RATE`, `AVG RUNNER`, `TRADES`, `WINS`, `LOSSES`, `VOLATILITY`, `BIAS`, `SCHEMA`, `NQ=`, a trailing `R` multiple, or a clock time `HH:MM`. A bare price with no CDX label is not an entry, stop, or target.

## Auto-right

Trigger: the first capture has no current level set (`VISION_NO_CDX_TEXT`, `VISION_NO_CURRENT_CDX_LEVELS`, `VISION_LEVELS_NOT_VISIBLE`, `VISION_CURRENT_SIGNAL_OFFSCREEN`, or `VISION_REJECT_STALE_TRADE_LEVELS`).

Flag: `CDX_VISION_AUTO_RIGHT_ENABLED`, default false.

Steps, at most `CDX_VISION_AUTO_RIGHT_MAX_ATTEMPTS` (default 3):

1. Refuse if the window is minimized.
2. Bring `TradingView.exe` to the foreground. If it is not the foreground window, send nothing.
3. Click the normalized chart point (`CDX_VISION_CHART_FOCUS_X` 0.40, `CDX_VISION_CHART_FOCUS_Y` 0.45). Check the foreground window again.
4. Send Ctrl+Right only if that check still names the same window.
5. Wait `CDX_VISION_REDRAW_DELAY_MS` (default 400).
6. Capture again. Frames from before the pan are not used as consensus frames.

If a level set appears, one more capture is taken on the settled chart and the two new frames must match. If the attempts run out: `VISION_LEVELS_NOT_VISIBLE_AFTER_NAVIGATION`.

Vertical scale is not changed. A level that is still off the price scale after the pan is not guessed.
