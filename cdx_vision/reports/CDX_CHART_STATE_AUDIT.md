# Chart state audit

The reader works when the bot chart is on 3 minutes and the trade is written as CDX ENTRY, SL, TP1, and TP2.

## What failed

The chart was left on 15 seconds, 30 seconds, or 1 minute. Those views still show CDX LONG / CDX SHORT. They often do not draw the native Entry / SL / TP1 / TP2 labels. The reader then saw ribbon prices such as 30922.55 and rejected them, so no order was placed.

A second bug treated a visible CDX LONG or CDX SHORT marker as proof the current trade was on screen. That stopped auto-right before the native labels could be found.

Timeframe was not read before OCR. 30s, 1m, and 3m were not distinguished.

## What it does now

The bot chart is the TradingView window whose title contains the configured pattern (default MNQ). A second personal chart is not selected.

Before level OCR, the toolbar interval is read. If it is not 3m, the bot window is focused, the interval menu is opened, and the "3 minutes" row is clicked. The toolbar is read again. Level OCR does not run until that read says 3m.

A CDX LONG or CDX SHORT marker does not stop recovery. Auto-right runs only after the timeframe is 3m, and it stops when the chart does not move, not when the marker is visible.

Ribbon prices that are off the 0.25 tick stay rejected.

## Live check

The dedicated window is TradingView.exe, title starting MNQ1!.

Detected 15s, 30s, 5m, and 1m were switched back to 3m. The toolbar was read as 3m after the switch. No order was sent.
