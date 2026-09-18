# Phase85 test report

Date: 2026-09-18  
Harness: `python3 -m unittest discover -s phase85/tests`

## Result

**69 tests OK**

| Module | Coverage |
|---|---|
| `test_protocol` | auth, malformed JSON, unknown command, protocol version, timestamp, qty, account, contract, duplicates, out-of-order events |
| `test_lifecycle` | LONG target, SHORT stop, reject, partial, protection-failure halt, invalid TARGET_FILLED, M0 from actual fill, flatten, protect-qty cap |
| `test_duplicates` | webhook ×4, command ×4, Python restart replay, bridge replay |
| `test_safety_defaults` | default SHADOW, each routing flag, auth/account/contract/qty, stale, data health, reconcile, kill, no auto-reverse, FUNDED SIM-gate + multi-arm |
| `test_restart` | FLAT, ENTRY_PENDING, FILLED_UNPROTECTED, POSITION_PROTECTED, post-stop, post-target, unexpected position, orphan order |
| `test_disconnect` | data loss, bridge loss, protection left working, reconnect+reconcile |
| `test_freeze_static` | Pine hash, Phase73 freeze, CRTBarBridge hash + no order APIs, C# security scan, distinct tokens |
| `test_state_machine` | illegal transitions, happy path, HALTED latch |

## Not run (require Windows + NT8 SIM)

- Real NinjaTrader SIM LONG/SHORT
- Real stop/target/OCO on SIM
- Real flatten against NT
- Real Phase72A → NT SIM
- Funded preflight against a live funded account
- First funded trade

Fake bridge covers those *sequences* deterministically. It is not a substitute for the SIM checklist.

## Freeze after tests

| Check | Result |
|---|---|
| Phase72A SHA256 | `d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f` |
| Phase73 freeze | PASS |
| CRTBarBridge SHA256 | `1a01a3f33c21cb3ac419e3ee7f3ab05448181b81a33bd5796f16ba2c6eeac880` |
| Frozen git dirty | none |
