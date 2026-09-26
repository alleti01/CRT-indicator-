# Repaint report

**Status: UNKNOWN**

Historical TradingView markers on a live/scrolled chart are not a repaint test.

Required later, on a **new** CDX print:

1. Screenshot at first appearance
2. Screenshot at bar close
3. Screenshot +1 bar
4. Reload chart if practical

Log: remain / disappear / move / reverse.

Until that exists: **do not automate**. If any marker moves after close: `CDX_RE_REPAINT_DETECTED`.
