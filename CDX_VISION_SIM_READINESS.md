# SIM readiness

Not ready. This phase does not send a SIM order.

Before a later phase may drive SIM from these levels:

- at least 50 reviewed signals
- zero accepted SL values that were wrong
- zero accepted direction conflicts
- exact tick match on accepted SL, TP1, and TP2
- ambiguous sets rejected
- timeout, window move, DPI, and restart checked on the real desktop

Funded routing is out of scope. `VisionConfig.may_route_orders` is false and is covered by a unit test.
