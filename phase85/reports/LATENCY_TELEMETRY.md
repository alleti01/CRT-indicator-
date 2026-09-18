# Latency telemetry

Recorded timestamps (when present):

| Tag | Meaning |
|---|---|
| T0 | Phase72A signal time |
| T1 | webhook received |
| T2 | Python decision |
| T3 | execution command created |
| T4 | bridge received / send time |
| T5 | NinjaTrader submit |
| T6 | ack |
| T7 | first fill |
| T8 | final fill |
| T9 | protection submitted |
| T10 | protection working |

Deltas: TV→webhook, webhook→decision, decision→bridge, bridge→submit, submit→ack, submit→fill, fill→protection, end-to-end.

Summaries: median / P95 / max via `LatencyTracker.summary()`.

**No live TV→NT samples exist in this checkout.** Unit tests exercise the recorder on the fake bridge only. Do not treat those in-process microseconds as production latency.

Live numbers must be collected on Windows during SIM rehearsal before any performance claim.
