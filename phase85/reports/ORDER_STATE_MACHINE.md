# Order state machine

```
IDLE
  → ENTRY_PENDING → ENTRY_ACCEPTED → PARTIALLY_FILLED → FILLED_UNPROTECTED
  → PROTECTION_PENDING → POSITION_PROTECTED
  → EXIT_PENDING → FLAT → IDLE

FILLED_UNPROTECTED / PROTECTION_PENDING
  → PROTECTION_FAILURE → FLATTENING → FLAT → HALTED

Any serious mismatch
  → RECONCILIATION_REQUIRED   (blocks new entries)

Critical failure
  → HALTED   (no silent auto-resume)
```

Impossible transitions raise `InvalidTransition` and are audit-logged.  
Example: `IDLE → TARGET_FILLED` does not mutate state.

An entry is **not** considered established at `FILLED`.  
Safe establishment is `POSITION_PROTECTED` (stop **and** target working).

`flatten command sent` ≠ FLAT. Only `POSITION_FLAT` from NinjaTrader confirms it.
