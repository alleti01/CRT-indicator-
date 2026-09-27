# Auto-right

The key is Ctrl+Right. Alt+R is not used.

The flag is on for the live bot after this recovery test. A key is sent only when TradingView is the foreground window. If the picture does not change, the next key is not sent (`VISION_AUTO_RIGHT_NO_MOVEMENT`).

## Real off-screen recovery

The known short was on the NQ 3-minute chart. The view was moved left until the price labels left the screen. The first capture of the test did not contain a complete current level set.

TradingView was focused. Ctrl+Right was sent twice. The chart moved. The third press was not sent.

After the second move the read was:

- Entry 30909.50, source WEBHOOK. The faint entry line was on the chart and was not accepted by the visual entry reader on this pass. The supplied test price was used and labeled as a webhook fallback.
- SL 30947.00
- TP1 30872.00
- TP2 30845.00
- Geometry passed. Stop and TP1 are 37.50 points. TP2 is 1.72R.
- Two frames agreed.
- Status VISION_CONFIRMED
- Signal id `TEST_AUTORIGHT_354fde45`
- Order calls: 0

Debug images: `cdx_vision/debug/autoright_230318/`.
