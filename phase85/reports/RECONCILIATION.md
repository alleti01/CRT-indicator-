# Reconciliation

NinjaTrader/account state is authoritative for exposure.

On every startup and after reconnect:

1. Query account / connection / position / working orders
2. Compare to Python expected snapshot
3. Block new entries until OK

## Compared

instrument, direction, quantity, working stop, working target, unexpected/orphan orders

## Outcomes

| Situation | Result |
|---|---|
| Python FLAT, NT FLAT | OK |
| Python FLAT, NT LONG unprotected | `RECONCILIATION_REQUIRED` |
| Python FLAT, NT LONG protected | `RECONCILIATION_REQUIRED` (recover only after operator review) |
| Orphan working order | `RECONCILIATION_REQUIRED` |

No automatic speculative corrective orders.  
Mismatch → block entries. Flatten only on explicit command or protection-failure halt.
