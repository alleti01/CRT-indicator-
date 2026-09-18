# Windows setup — Phase85

Designed so the same layout can later run on a Windows VPS. No GUI scraping, no clipboard automation.

## 1. Python

Same environment already used for Phase74 shadow:

```powershell
cd <repo>
python -m unittest discover -s phase85/tests -v
```

All tests must PASS before enabling the execution bridge.

## 2. Environment (no secrets in this file)

Set in the user/system environment or a local `.env` that is **not** committed:

```
EXECUTION_MODE=SHADOW
SHADOW_MODE=true
TRADING_ENABLED=false
EXTERNAL_ORDER_ROUTING=false
NT_EXECUTION_BRIDGE_ENABLED=false

NINJATRADER_EXECUTION_BRIDGE_TOKEN=<generate a new random token>
EXPECTED_ACCOUNT=<exact NT account name>
ALLOWED_FUNDED_ACCOUNT=<exact funded account name when ready>
FUNDED_ACCOUNT_VERIFIED=false
```

Generate the execution token independently of the webhook secret and the market-data token.

Write the **same** execution token to **one** of:

- `%USERPROFILE%\Documents\NinjaTrader 8\bin\crt_execution_token.txt`
- `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\crt_execution_token.txt`

Do not put the market-data token in that file.

## 3. Market-data bridge (unchanged)

Keep `CRTBarBridge` on the 1-minute chart, host `127.0.0.1`, port `8765`, token file `crt_bridge_token.txt`.  
Do not add orders to that indicator.

## 4. Copy and compile the execution AddOn

1. Copy `phase85/ninjatrader/CRTExecutionBridge.cs` to  
   `Documents\NinjaTrader 8\bin\Custom\AddOns\CRTExecutionBridge.cs`
2. In NinjaTrader: New > NinjaScript Editor > compile
3. If compile fails on `CreateOrder` / `Submit` / `Flatten` signatures, **stop**. Verdict is `PHASE85_NINJATRADER_API_BLOCKED`. Do not invent a second path.
4. Enable the AddOn (Control Center). Set:
   - Host `127.0.0.1`
   - Port `8766`
   - ExpectedAccount = exact SIM account name
   - ExpectedContract = exact MNQ contract (example `MNQ 12-26`) — **not** inferred from the GUI selection

## 5. Start order

1. Start Python Phase74 live stack (market data + webhook) as you already do for shadow
2. Start `python -m phase85.diagnostics.run_phase85` or the future SIM runner that constructs `NinjaTraderExecutionAdapter` + `ExecutionBridgeServer`
3. Enable `CRTExecutionBridge` so it connects out to `127.0.0.1:8766`
4. Confirm logs: `EXECUTION_AUTHENTICATED`, `ACCOUNT_VERIFIED`, `CONTRACT_VERIFIED`, `POSITION_RECONCILED`

## 6. SIM mode (after unit tests)

Set, still on the **simulation** account only:

```
EXECUTION_MODE=SIM
SHADOW_MODE=false
TRADING_ENABLED=true
EXTERNAL_ORDER_ROUTING=true
NT_EXECUTION_BRIDGE_ENABLED=true
EXPECTED_ACCOUNT=<exact SIM account>
```

Work the checklist in `SIM_ACTIVATION_CHECKLIST.md`.  
Do not enable FUNDED yet.

## 7. FUNDED mode (only after SIM gate)

```
EXECUTION_MODE=FUNDED
FUNDED_ACCOUNT_VERIFIED=true
EXPECTED_ACCOUNT=<exact funded account>
ALLOWED_FUNDED_ACCOUNT=<same exact name>
```

Plus SIM gate file present. Run funded preflight. If any line is missing, stay closed.

## 8. Current platform rules

Before any funded order, re-read Tradeify / NinjaTrader automation rules **that day**.  
Document in the session log: date checked, account type, automation restrictions, whether this architecture complies.  
Technical SIM success is not authorization.

## 9. VPS later

Same processes, native NT8 + native Python, localhost only.  
No requirement for a home-PC GUI.
