# Auto-right

The key is Ctrl+Right. Alt+R is not used.

The flag defaults to false. `python -m cdx_vision.test_auto_right` turns it on for that process only.

Unit checks, with a fake navigator and no real keystrokes:

- Levels already visible: 0 keypresses.
- Visible after one move: 1 keypress, then stop.
- Visible after two moves: 2 keypresses, then stop.
- Still hidden after 3 moves: stop, reason exhausted.
- Focus fails: 0 keypresses.
- Foreground window is not TradingView: 0 keypresses.
- Window minimized: 0 keypresses.

Live run against the open TradingView app:

- First capture: current levels not visible.
- Focus succeeded.
- Ctrl+Right was sent 3 times, which is the maximum.
- That pan moved the chart onto the short. The labels were then left of the old right-hand search box, so the first pass still rejected them.
- The search box was widened, and a lone visible trade is no longer discarded for sitting left of empty space.
- The next read, with no further pan, confirmed Entry 30909.50, SL 30947.00, TP1 30872.00, TP2 30845.00, source VISION.
- Order calls: 0.

The running bot was not switched to `CDX_VISION_ENABLED=true`, and auto-right stays off unless that test command or the env flag is set.
