# Funded preflight checklist

Runtime output must include **all** of:

```
PHASE72A_FREEZE_OK
PHASE73_FREEZE_OK
NINJATRADER_DATA_CONNECTED
DATA_HEALTHY
EXECUTION_BRIDGE_CONNECTED
EXECUTION_AUTHENTICATED
EXECUTION_MODE=FUNDED
FUNDED_ACCOUNT_VERIFIED
CONTRACT=MNQ
CONTRACT_VERIFIED
MAX_QUANTITY=1
POSITION_RECONCILED
POSITION=FLAT
ORDERS_RECONCILED
UNEXPECTED_WORKING_ORDERS=0
KILL_SWITCH=OFF
TRADING_ENABLED=TRUE
EXTERNAL_ORDER_ROUTING=TRUE
NT_EXECUTION_BRIDGE_ENABLED=TRUE
SIM_GATE=PASS
FUNDED_EXECUTION_READY
```

Any miss → `FUNDED_EXECUTION_NOT_READY`.

Also required **outside** the process:

- Current Tradeify / NT automation rules checked **the same day** (see WINDOWS_SETUP)
- Supervised operator present for the first funded lifecycle
- MNQ qty 1 only; no auto-reverse; no size increase

First funded trade acceptance is a separate verdict: `PHASE85_FIRST_FUNDED_TRADE_PASS`.  
Any discrepancy → `PHASE85_FUNDED_EXECUTION_HALT`. Do not send another funded order until reviewed.

This repository has **not** completed SIM activation, so funded capability is **NOT READY**.
