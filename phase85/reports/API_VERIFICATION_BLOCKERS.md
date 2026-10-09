# Phase85 implementation stop — 2026-09-18

Current verdict: **PHASE85_NINJATRADER_API_BLOCKED**.

The user explicitly required stopping if the NinjaTrader API could not be verified. The pre-existing execution bridge cannot be validated against the documented API. Implementation stopped before source changes. No NinjaTrader runtime or funded connection was started.

The ChatGPT project mirror contained only AGENTS.md and an empty sources directory. The actual repository was located at `/Users/anishalleti/CRT indicator`, branch `main`, commit `e0a48b6`. Its untracked `phase85/` already existed before this task. The uploaded 81-section specification was recovered from the referenced conversation. The existing implementation and its earlier readiness report were not created in this task.

## API verification blocker

At `phase85/ninjatrader/CRTExecutionBridge.cs:299`, `:330`, and `:331`, `Account.CreateOrder` receives a string command ID as its last argument. The official signature specifies `CustomOrder customOrder`, not a string. The comment at line 286 incorrectly describes this argument as text. See [NinjaTrader CreateOrder documentation](https://docs.ninjatrader.com/ninjascript/createorder), checked 2026-09-18.

The event handlers at lines 433 and 447 also depend on `Order.CustomText` for command correlation. This member could not be verified in the official [Order reference](https://docs.ninjatrader.com/ninjascript/order). Absence from that reference is not proof that no platform version exposes it, but it is insufficient evidence to rely on it. No NinjaTrader assemblies were found in the inspected repository or /Applications, and no target Windows compile was available. This is a documented signature mismatch and an unverified member, not a reported compiler run.

Passing null for the custom-order argument alone would not repair durable command/order correlation. A replacement needs documented order identity, persistent association, restart reconciliation, and target-version compilation. Those changes were not attempted past the user's stop gate.

## Additional defects identified before the stop

These findings are not an exhaustive safety audit.

1. **No complete real transport/runtime path.** `phase85/ninjatrader/transport.py` defines a protocol requiring connect, send, snapshot, and verified identity fields. `ExecutionBridgeServer` exposes a different interface. The startup diagnostic does not start the server or attach the production signal flow. The previous Windows instructions referred to a future SIM runner that does not exist.
2. **Fills do not trigger protection automatically.** In `phase85/execution/adapter.py:354`, the FILLED handler computes M0 and records the fill, then returns at line 389. It does not submit protection. Existing lifecycle tests invoke protection separately, so their success does not prove the requested automatic lifecycle.
3. **Protection is reported working prematurely.** `CRTExecutionBridge.cs:334` submits the bracket and immediately emits STOP_WORKING and TARGET_WORKING. Submission is not confirmation from NinjaTrader. Asynchronous rejection must instead trigger the protection failure policy.
4. **Account callbacks lack adequate filtering.** Order, execution, and position callbacks do not first restrict events to the configured instrument and owned orders. They can therefore contaminate strategy state with unrelated account activity.
5. **Flatten cancels unrelated orders.** `FlattenAccount` calls `CancelWorking("")`; that method scans working orders account-wide without an instrument/ownership filter.
6. **Reconciliation response is incomplete.** `EmitPosition` computes a side but the event schema does not transmit it, and QUERY_ORDERS does not return an actual order snapshot. This cannot establish position/order agreement.
7. **Durable dedup failures are swallowed.** The C# command persistence read/write routines catch errors silently. The claimed restart duplicate guarantee is not established by that implementation.

## Freeze and baseline

Phase72A SHA256 matched `d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f` before reporting. The existing `verify_phase73_freeze()` returned `(True, [])` for all 16 critical modules. CRTBarBridge SHA256 matched `1a01a3f33c21cb3ac419e3ee7f3ab05448181b81a33bd5796f16ba2c6eeac880`. Its read-only static tests passed.

Phase73: 26 passed. Phase74: 74 passed, 3 failed. Existing Phase85: 69 passed. The Phase74 failures were present before any edit and concern intraday session resets in PropDayHalt. Their tests expect session-boundary resets, while the implementation rolls on the New York calendar date. No frozen behavior or tests were altered to make the baseline pass.

The first sandboxed Phase74 run also had nine loopback permission errors. A permitted rerun resolved all nine; the three strategy-related failures remained. The tests used synthetic data and loopback peers, not NinjaTrader or a broker.

## Required next work

Verify a supported correlation design and compile it against the target NinjaTrader 8 version before resuming implementation. Resolve the existing Phase74 baseline discrepancy through a separate decision about intended frozen behavior. Then complete the real runtime, automatic fill protection, confirmed order events, strict protocol/identity validation, durable dedup, reconciliation, and failure handling. Repeat the Python and real transport tests and conduct the Windows SIM checklist. No SIM activation evidence or funded-readiness claim exists.

Repository defaults remain SHADOW with all external-routing switches false. Do not use the prior Windows activation steps as an executable setup procedure while this blocker is open.
