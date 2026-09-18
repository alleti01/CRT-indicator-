# Failure handling

| Failure | Behavior |
|---|---|
| Auth fail | Disconnect / no routing |
| Wrong account / contract / qty | Reject; no submit |
| Duplicate command / signal | Return existing state; no second order |
| Stale signal | `PASS_STALE_SIGNAL` |
| Unhealthy NT data | `PASS_DATA_UNHEALTHY` |
| Entry reject | Log reason; no blind retry; return idle |
| Protection failure | `FLATTEN` → confirm FLAT → `EXECUTION_HALTED` |
| Reconcile fail | `RECONCILIATION_REQUIRED`; block entries |
| Execution disconnect | Block new entries; do not cancel working protection |
| Market-data disconnect | Existing Phase74 health blocks entries |
| Kill switch / HALTED | Block new entries; protection left working |
| Opposite signal while in position | `REJECT_NO_AUTO_REVERSE` — exit+flat first, then a new entry |

HALTED recovery requires an explicit operator `reset_halt(operator_ack=True)`. It returns to DISABLED, not ENABLED.
