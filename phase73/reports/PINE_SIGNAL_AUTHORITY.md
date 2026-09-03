# Pine Signal Authority

**Phase72B verdict:** `PHASE72B_MANUAL_PARITY_LIMIT_REACHED`

## Production rule

| Layer | Role |
|-------|------|
| **Pine (Phase72A)** | SIGNAL AUTHORITY — when to initiate LONG/SHORT opportunity |
| **Python (Phase73)** | EXECUTION + MANAGEMENT AUTHORITY — whether entry is still valid, order routing, position tracking, exits |

Python does **not** independently regenerate Pine signals in production.

## Frozen artifact

| Field | Value |
|-------|-------|
| File | `TV_REVIEW/phase72a_autonomous_trader.pine` |
| SHA256 | `d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f` |
| Pine version | 6 |
| Lines | 1837 |
| Symbol | NQ continuous 1m |
| Timeframe | 1m confirmed bars |

Full metadata: `phase73/config/PINE_SIGNAL_FREEZE.json`

## Authoritative signal events

- `SIGNAL_LONG`
- `SIGNAL_SHORT`

Optional informational (Python does not require for management):

- `EXIT_STOP`, `EXIT_TARGET`, `ENTER_LONG`, `ENTER_SHORT`

## Version policy

Any change to Layer A requires a **new** pine hash and explicit re-freeze. Phase73 webhook validator rejects hash mismatches with `SIGNAL_HASH_MISMATCH`.
