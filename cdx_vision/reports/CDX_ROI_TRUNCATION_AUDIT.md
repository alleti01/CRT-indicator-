# ROI truncation audit

The level scan was `cdx_vision/config/windows_chart.json` key `ocr_roi`, loaded by `load_roi()` in `cdx_vision/live_job.py`.

```
x_start 0.18
y_start 0.10
x_end   0.78
y_end   0.88
```

That box was a fraction of the whole TradingView window so the OCR would stay left of the alerts sidebar. On the current MNQ chart the Entry, SL, TP1, and TP2 prices sit on that 78% line, so the crop cuts the decimals off before OCR runs.

`current_roi_overlay.png` draws that line through the prices.

The replacement box follows the chart pane. Its right edge is the dark gutter before the right-hand toolbar, which on this capture is about 85% of the window width. A price that still touches that edge expands the crop at most twice. A cut token such as `SL_30785,` is not accepted as a price.
