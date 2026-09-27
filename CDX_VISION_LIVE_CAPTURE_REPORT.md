# Live capture

`python -m cdx_vision.list_windows` found one window:

- process `TradingView.exe`
- title `NQ1!`
- hwnd 132428

`python -m cdx_vision.capture_now` saved a real image:

- method PRINTWINDOW
- size 2560x1380
- not blank
- path `cdx_vision/debug/manual_20260927_175439/window.png`

Chrome was not used. The capture target is the TradingView desktop app only.

`python -m cdx_vision.ready` printed CAPTURE PASS with method PRINTWINDOW.
