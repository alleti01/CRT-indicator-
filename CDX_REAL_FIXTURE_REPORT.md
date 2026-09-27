# Real fixture report

Six screenshots are in `cdx_vision/fixtures/real/`, with `manifest.json`.

`cdx_real_01.png` is the captured TradingView window, 2560 by 1380. It is the golden short.

Read from that image:

- Entry 30909.50, source VISION
- SL 30947.00
- TP1 30872.00
- TP2 30845.00
- Native R 37.50
- TP1 1.00R
- TP2 1.72R

A webhook price of 30910.25 stayed in `webhook_entry`. It did not replace the visual entry.

`cdx_real_02.png` through `cdx_real_06.png` are the earlier TradingView screenshots from `cdx_research/screenshots`. They show other sessions, older boxes, and the side panels. Their prices were not transcribed, and the tests do not invent expected numbers for them. The selector tests use placed tokens for the old-versus-new decision.
