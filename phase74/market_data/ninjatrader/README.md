# NinjaTrader 8 → Python read-only bar bridge

Minimal **read-only** feed: closed 1-minute NQ OHLCV bars over localhost TCP. No order APIs.

## Protocol

JSON lines (UTF-8, `\n` delimited):

**hello** (client → server, first message):
```json
{"type":"hello","seq":0,"auth":"<token>","contract":"NQ 09-26","instrument":"NQ","chart_timezone":"UTC"}
```

**bar** (client → server, each closed 1m bar):
```json
{"type":"bar","seq":1,"ts_utc":"2026-09-06T21:29:00Z","open":20000,"high":20010,"low":19995,"close":20005,"volume":1234,"contract":"NQ 09-26"}
```

**ack** (server → client):
```json
{"type":"ack","ok":true,"detail":"BAR","seq":1}
```

Timestamps are **UTC bar open** time. Python deduplicates by sequence and timestamp; auth is fail-closed.

## NinjaScript installation

1. **Copy indicator**
   - Source: `phase74/market_data/ninjatrader/CRTBarBridge.cs`
   - Destination: `Documents\NinjaTrader 8\bin\Custom\Indicators\CRTBarBridge.cs`

2. **Compile in NinjaTrader**
   - Control Center → New → NinjaScript Editor
   - Right-click **Indicators** → Compile (or F5)
   - Confirm **0 errors** in Output window

3. **Set auth token** (must match Python `NINJATRADER_BRIDGE_TOKEN`)
   - Use the same secret in NT indicator parameters and your shell `.env`

4. **Attach to chart**
   - Instrument: **NQ** (front month or Tradeify-connected contract)
   - Interval: **1 minute**
   - Chart time zone: **UTC** (recommended)
   - Indicators → **CRTBarBridge**
   - Parameters: Host `127.0.0.1`, Port `8765`, AuthToken `<your token>`

5. **Verify connection**
   - Start Python bridge first (see `run_live.py --provider ninjatrader`)
   - NT Output window should show: `CRTBarBridge authenticated contract=...`
   - Python logs: `ninjatrader authenticated contract=...`

## Safety

- Indicator uses **TcpClient** and **Indicator** APIs only
- No `EnterLong`, `SubmitOrder`, `Account`, or ATM strategy calls
- Run `python3 -m unittest phase74.tests.test_ninjatrader_live.TestNinjaTraderSafetyScan -v` to verify

## Python launch

```bash
cd "/Users/anishalleti/CRT indicator"
export NINJATRADER_BRIDGE_TOKEN="your-secret"
export SHADOW_MODE=true
export TRADING_ENABLED=false
export EXTERNAL_ORDER_ROUTING=false
python3 phase74/run_live.py --provider ninjatrader --mode shadow --webhook
```

Shadow verification: webhook fires `WOULD_ENTER` in logs; `trader_state.json` stays FLAT; no broker fills.
