# Execution protocol

Transport: JSON-lines over localhost TCP.

Polarity matches the market-data bridge: **Python listens**, NinjaTrader connects.

| Role | Bind / connect | Port | Token file |
|---|---|---|---|
| Market data `CRTBarBridge` | NT → Python | 8765 | `crt_bridge_token.txt` |
| Execution `CRTExecutionBridge` | NT → Python | 8766 | `crt_execution_token.txt` |

Tokens are different. Neither is the TradingView webhook secret.

`protocol_version` must be `1`. Other versions → `UNSUPPORTED_PROTOCOL`.

## Commands (closed set)

`ENTER_LONG` `ENTER_SHORT` `PLACE_PROTECTION` `CANCEL_ENTRY` `FLATTEN`  
`QUERY_POSITION` `QUERY_ORDERS` `PING` `RECONCILE`

No shell, no generic broker passthrough, no arbitrary NinjaScript.

Required on mutating commands: `command_id`.  
Carry `event_id` / `signal_id` when they exist.

## Events

`EXECUTION_BRIDGE_READY` `ACCOUNT_STATE` `CONNECTION_STATE`  
`ORDER_RECEIVED` `ORDER_SUBMITTED` `ORDER_ACCEPTED` `ORDER_REJECTED` `ORDER_CANCELLED`  
`PARTIAL_FILL` `FILLED`  
`STOP_WORKING` `TARGET_WORKING` `STOP_FILLED` `TARGET_FILLED`  
`POSITION_UPDATE` `POSITION_FLAT`  
`RECONCILIATION_RESULT` `PROTECTION_FAILURE`  
`DUPLICATE_COMMAND` `PONG` `COMMAND_REJECTED`

## Authority

Submission is not a fill. Acceptance is not a fill.  
Only `FILLED` (NinjaTrader execution) establishes exposure.  
Only `POSITION_FLAT` from NinjaTrader confirms flat.
