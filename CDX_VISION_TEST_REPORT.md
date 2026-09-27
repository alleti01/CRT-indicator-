# CDX vision tests

`python -m unittest cdx_vision.tests.test_vision`

10 tests, all passed.

Covered: tick parsing, the known short numbers, long geometry, direction conflict, invalid short ordering, two-frame agreement, a 2-against-1 OCR split rejected, duplicate signal_id, restart-stale request, timeout, append-only ledger, and funded flag still unable to route.

Not covered by an image yet: a real TradingView PNG. The fixture file is not in the repo.
