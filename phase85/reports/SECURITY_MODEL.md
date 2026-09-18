# Security model

## Authentication

- Execution token: env `NINJATRADER_EXECUTION_BRIDGE_TOKEN`
- Compared with `hmac.compare_digest` (Python) / exact file token (C#)
- Distinct from `PHASE74_WEBHOOK_SECRET` and `NINJATRADER_BRIDGE_TOKEN`
- Not hardcoded, not committed, not logged, not placed in URLs

C# reads only these fixed paths:

- `Documents\NinjaTrader 8\bin\crt_execution_token.txt`
- `Documents\NinjaTrader 8\bin\Custom\crt_execution_token.txt`
- OneDrive equivalents

## Bind

Python refuses to listen on a non-loopback host.  
C# refuses to connect to a non-local host.  
Accept loop only allows `127.0.0.1` / `::1`.

## Command surface

Unknown commands are rejected. There is no eval, process spawn, HTTP client, or arbitrary filesystem API in `CRTExecutionBridge.cs` (static-scanned).

Command IDs persist to a **fixed** file `crt_execution_command_ids.txt` so restarts cannot double-submit. That is not a general file API.

## Account / contract

Never “first connected account” or GUI selection.  
`EXPECTED_ACCOUNT` must match exactly.  
FUNDED also requires `ALLOWED_FUNDED_ACCOUNT` exact match and `FUNDED_ACCOUNT_VERIFIED`.  
Instrument root `MNQ` only. `NQ` is rejected. No silent NQ→MNQ map.

## Quantity

`MAX_QUANTITY=1` enforced in Python gates **and** in C# before `Account.Submit`.

## Multi-arm activation

FUNDED needs all of: `EXECUTION_MODE=FUNDED`, `TRADING_ENABLED`, `EXTERNAL_ORDER_ROUTING`, `NT_EXECUTION_BRIDGE_ENABLED`, `FUNDED_ACCOUNT_VERIFIED`, SIM gate pass, kill switch not halted.
