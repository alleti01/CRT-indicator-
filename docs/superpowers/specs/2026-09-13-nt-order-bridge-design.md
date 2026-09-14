# NinjaTrader order bridge — live book beside paper

**Date:** 2026-09-13  
**Status:** Spec only. Do not implement until this file is reviewed.  
**Account:** same Tradovate-backed funded login the user already clicks in NT / Tradovate / TradingView. **$50k**, **$2,000 DD**, 1 NQ, **$20/point**.  
**Why not Tradovate API:** the firm disables developer API on this account. NT / website / TradingView are three windows on **one** position. Live orders must go through NT’s brokerage connection, not `demo.tradovateapi.com` / `live.tradovateapi.com`.

Frozen Pine hash and Phase73 engine files stay unchanged. `CRTBarBridge.cs` stays **bars only**.

---

## 1. Problem

Paper (`LOCAL_SIM`) can journal a TAKE. It cannot protect a real NQ. Client-side stops die with Python (Friday 9:39 AM freeze: opposite TAKE parked `REVERSAL_WATCH`, stop never fired, price ran through 29441.95).

The user needs:

- paper still running (full journal, gates, dollar halt, trail)
- at most **one live trade per NY day** to maintain the funded account
- a **working stop on the NT account** so a Python or webhook failure does not leave a naked contract

Tradovate REST/WebSocket is not available. TradingView’s connected broker must not place orders (same account → second unmanaged entry).

---

## 2. Goal

A Phase74 **live book** that:

1. Shares the same TV webhook and NT 1m bars as paper.
2. Places **only** market entry, one working stop, stop replace (trail), and flatten — through a new NT AddOn.
3. Treats the NT account snapshot as source of truth on restart.
4. Never sends those verbs from the paper journal path.

Success for v1:

- After a live TAKE, NT SuperDOM / Orders tab shows the position **and** a working stop before Python calls the trade `PROTECTED`.
- Disable or kill the Python process: the NT working stop remains.
- Opposite TAKE / `REVERSAL_WATCH` does not cancel or freeze that stop.
- Paper `paper_trades.csv` still records every sim fill; live has its own journal under `phase74/logs/live/`.
- `CRTBarBridge.cs` still fails `TestNinjaTraderSafetyScan` (no order APIs).

---

## 3. Locked decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Venue | NinjaTrader AddOn `CRTOrderBridge` | Only order path the firm allows |
| Tradovate REST/WS | Out of scope | Firm lock |
| TV broker / `strategy.order` | Forbidden | Same account, unmanaged second order |
| Orders inside `CRTBarBridge` | Forbidden | Bars + risk must not share one indicator |
| NT vehicle | **AddOn**, not chart Strategy | Strategy disable typically cancels its orders; `Account.Submit` persists like a SuperDOM click |
| Process layout | **One Python process, two books** | One NT bar socket (8765); live crash must not require a second bar feed. Isolation is code-path, not a second OS process |
| Paper book | `LOCAL_SIM` + current overlays | Unchanged dress rehearsal |
| Live book | Supervisor + NT venue | Only this book may write the order socket |
| Entry | Market, 1 contract | No limits, no scale |
| Protection | One working **StopMarket**, GTC, opposite side | No venue target (trail owns the target) |
| Live frequency | **1 new entry per America/New_York date** | Maintenance, not a second paper firehose |
| Live session | **RTH only** (09:30–16:00 NY) | Overnight paper may still trade; live must not |
| Gates / dollar halt | Same card as paper | ATR > 15 skip; 2 losers / −$400 / 2 wins / +$500 / giveback |
| Default | Live book **off** | `live_account.enabled=false` until the AddOn is installed and reviewed |
| Manual | Still valid | User may click NT instead; bot must not also enter |

Dollars for halt / journal stats: `points * 20` or `net_R * ATR_points * 20`. Do not use `contracts.multiplier` 2.0.

---

## 4. Architecture

```
TradingView Chart A webhook
        │
        ▼
  :8787 SecureWebhookReceiver
        │
        ├─► Paper LiveStack  → SlippageSimRouter → phase74/logs/paper_trades.csv
        │
        └─► Live LiveStack   → ExecutionSupervisor → NT order socket :8766
                                      │
                                      ▼
                               CRTOrderBridge (NT AddOn)
                                      │
                                      ▼
                               Funded account (1 NQ + working stop)

NinjaTrader chart ── CRTBarBridge ──► :8765  (bars only, both books read this)
```

Phase73 `TraderEngine` stays the decision/FSM book for **each** stack (two engine instances, two `trader_state.json` files). Live engine sim-fill still builds `mgmt` (same freeze constraint as paper). The supervisor then places the **real** NT market + stop. Paper’s engine never sees the order socket.

Live `on_bar` trail only `replace_stop`. Price exits are NT stop fills, not `evaluate_exit` M0_STOP. Hide the live engine stop the same way the trail overlay already hides the 2.5R target. Timeout / kill / day-halt-while-flat / emergency still call `supervisor.flatten()`.

---

## 5. Supervisor (shared with a PaperVenue test double)

States: `IDLE` → `ENTRY_WORKING` → `PROTECT_WORKING` → `PROTECTED` → `EXIT_WORKING` → `IDLE`.  
Anything else is `UNSAFE` → flatten + halt new live entries.

Venue verbs (Python interface; NT is one implementation):

- `submit_market(side, qty, client_id)`
- `submit_stop(side, qty, price, client_id)`
- `replace_stop(order_id_or_client_id, price)`
- `flatten(client_id)`
- `snapshot()` → position + working orders

Rules:

1. A live trade is `PROTECTED` only when NT has acked **both** the entry fill and a working stop.
2. If the stop is not `WORKING` within `stop_ack_timeout_sec` (default **5**), flatten.
3. `client_id = "{signal_id}:{verb}"` (`ENTRY` / `STOP` / `FLAT`). Retry is a no-op.
4. Restart: `snapshot()` first. Short+working stop → attach `PROTECTED`. Short and **no** stop → flatten. Flat while engine thinks it is in a trade → flatten the engine book and halt live.
5. Opposite TAKE does not flatten, reverse, or cancel the stop.
6. Socket drop while `PROTECTED`: do **not** cancel the NT stop. Log `ORDER_BRIDGE_DISCONNECT_ACTIVE`. On reconnect, snapshot. Flatten from Python only after the socket is back, or via the user in NT.

PaperVenue (in-memory) implements the same verbs for unit tests. It does not listen on 8766.

---

## 6. Order-bridge protocol

JSON lines, UTF-8, `\n` delimited. **NT AddOn is the TCP client**; Python live venue is the server on `127.0.0.1:8766`. Same auth style as the bar bridge (`NINJATRADER_ORDER_TOKEN` in `phase74/.env`, distinct from `NINJATRADER_BRIDGE_TOKEN`).

Bind **localhost only**. Reject non-loopback.

### 6.1 NT → Python

**hello** (first message):

```json
{"type":"hello","seq":0,"auth":"<order-token>","account":"<NT account name>","contract":"NQ 09-26"}
```

Python rejects on bad token, account name ≠ config, or contract prefix ≠ `NQ`.

**order** (ack / working / terminal):

```json
{"type":"order","client_id":"sig:ENTRY","nt_order_id":"123","state":"WORKING","side":"SELL","order_type":"MARKET","qty":1,"stop_price":null}
```

`state`: `ACCEPTED` | `WORKING` | `FILLED` | `REJECTED` | `CANCELLED`.

**fill**:

```json
{"type":"fill","client_id":"sig:ENTRY","nt_order_id":"123","price":29410.75,"qty":1,"ts_utc":"2026-09-11T13:39:00Z"}
```

**position** (after fill, flatten, or snapshot):

```json
{"type":"position","side":"SHORT","qty":1,"avg_price":29410.75,"unrealized_points":0}
```

`side`: `LONG` | `SHORT` | `FLAT`.

**reject**:

```json
{"type":"reject","client_id":"sig:STOP","reason":"STOP_REJECTED","detail":"..."}
```

**pong** in reply to heartbeat.

### 6.2 Python → NT

```json
{"type":"ack","ok":true,"detail":"HELLO","seq":0}
```

```json
{"type":"submit_market","client_id":"sig:ENTRY","side":"SELL","qty":1}
{"type":"submit_stop","client_id":"sig:STOP","side":"BUY","qty":1,"stop_price":29441.95}
{"type":"replace_stop","client_id":"sig:STOP","stop_price":29390.00}
{"type":"flatten","client_id":"sig:FLAT"}
{"type":"snapshot"}
{"type":"heartbeat"}
```

`side` is `BUY` / `SELL`. Short entry = `SELL` market + `BUY` stop. Long is the reverse.

Unknown `type` → reject, do not place.

---

## 7. CRTOrderBridge AddOn (NinjaScript)

New file: `phase74/execution/ninjatrader/CRTOrderBridge.cs`  
Install: `Documents\NinjaTrader 8\bin\Custom\AddOns\CRTOrderBridge.cs`  
Compile in NinjaScript Editor. Enable **automated trading** on the funded account.

Behavior:

- On start: TCP connect to configured host/port, send `hello`, wait for ack.
- Map `submit_market` / `submit_stop` to `Account.Submit(...)` (account-level orders, not strategy-managed).
- Map `replace_stop` to `Account.Change(...)` on the working stop with that `client_id` (store NT order id locally).
- Map `flatten` to cancel working orders for this contract **that this AddOn placed**, then market flatten the 1-lot if still open. Do not cancel unrelated user orders on other instruments.
- Map `snapshot` to current account position + working orders for the configured contract.
- On socket drop: **leave working stop and position alone**. Reconnect and send `hello` + unsolicited `position` + working `order` rows.
- On AddOn terminate: same as socket drop — **do not** cancel the protective stop.
- `isAutomated` equivalent: these are bot orders; NT account must have ATM/auto trading enabled. Do not also arm a chart ATM template that places a second stop.

Parameters: Host `127.0.0.1`, Port `8766`, AuthToken, Account name, Contract `NQ 09-26`.

`CRTBarBridge` safety scan stays file-scoped to the indicator. A **new** scan asserts `CRTOrderBridge.cs` exists as an AddOn (not under `Indicators`) and that `CRTBarBridge.cs` still has zero order APIs.

---

## 8. Live book policy (Python)

Applied only to the live stack, after the shared quality gates:

1. `live_account.enabled` must be true and the order socket must be authenticated.
2. `max_trades_per_day` (default 1): count **live fills** on the NY date, not paper fills.
3. `require_rth` (default true): skip live entry outside 09:30–16:00 America/New_York.
4. Live has its **own** `PropDayHalt`, seeded only from `phase74/logs/live/` closes. A paper loser must not lock the funded window; a live loser must.
5. Kill switch: `PHASE74_LIVE_KILL_SWITCH=1` blocks live entries and flattens live if in a trade. Paper kill stays `PHASE74_KILL_SWITCH`.
6. If NT position is already non-flat at enable (user clicked), do **not** add a second contract. Snapshot-attach or halt.

Live journal: `phase74/logs/live/paper_trades.csv` (same columns) plus `orders.jsonl` with every protocol message.

---

## 9. Config

`phase74/config/default.json` (live off by default):

```json
"live_account": {
  "enabled": false,
  "venue": "NINJATRADER_ORDER_BRIDGE",
  "host": "127.0.0.1",
  "port": 8766,
  "auth_env_var": "NINJATRADER_ORDER_TOKEN",
  "account_name": "",
  "contract": "NQ 09-26",
  "quantity": 1,
  "max_trades_per_day": 1,
  "require_rth": true,
  "rth_start": "09:30",
  "rth_end": "16:00",
  "rth_timezone": "America/New_York",
  "stop_ack_timeout_sec": 5,
  "logs_dir": "phase74/logs/live"
}
```

`broker.adapter` for the paper book stays `LOCAL_SIM`.  
`mode.external_order_routing` stays false until live is enabled **and** the order socket is up; `run_live.py` must not flip it globally for the paper book.

Empty `account_name` → live stack refuses to enable (fail closed).

---

## 10. Ops

1. Paper as today: `scripts/start-ninjatrader-paper.ps1`, toggle `CRTBarBridge`.
2. Compile and enable `CRTOrderBridge` AddOn. Confirm NT Output: authenticated, account name matches.
3. Set `live_account.account_name`, put `NINJATRADER_ORDER_TOKEN` in `.env`, set `live_account.enabled` true, restart Python, **toggle both** the bar indicator and the AddOn (neither auto-reconnects today; AddOn must implement reconnect, bar indicator still needs a toggle unless already connected).
4. Confirm 8765 (bars) and 8766 (orders) listening. Confirm SuperDOM is flat before the first live day.
5. First live day: one RTH TAKE that passed gates, ATR ≤ 15. Watch NT for the working stop within 5 seconds. If it does not appear, flatten in NT by hand.

Do not click Tradovate or TradingView on that trade.

---

## 11. Tests

TDD order (no NT required for these):

1. PaperVenue + supervisor: protect, reject-stop→flatten, replace_stop, idempotent `client_id`, restart attach, naked short→flatten.
2. Protocol encode/decode + auth reject + non-loopback reject.
3. LiveStack glue with a mock socket: TAKE → `submit_market` then `submit_stop`; fill+working stop → `PROTECTED`; opposite TAKE → no flatten; bar through stop → live journal close; paper journal still has its own row if paper also took.
4. Live RTH + `max_trades_per_day=1` + live halt isolated from paper halt.
5. `CRTBarBridge.cs` still has no order APIs.
6. `CRTOrderBridge.cs` is not imported by the bar indicator.

Existing Phase74 integration / quality / reversal-watch tests stay green with `live_account.enabled=false`.

---

## 12. Out of scope

- Tradovate REST/WebSocket adapter
- TradingView broker / Pine `strategy.order`
- Venue profit target / OCO / ATM template with a target
- Scale-in, reverse, 2-lot, MNQ
- Editing Phase73 or the frozen Pine hash
- Putting `SubmitOrder` in `CRTBarBridge.cs`
- Enabling live by default
- Two OS processes / second public webhook
- Tick-level NT data (1m bars remain the decision clock; the **stop** is the real-time protection)

---

## 13. Implementation order (after spec approval)

1. Supervisor + PaperVenue tests (no NT).
2. Protocol + mock order server tests.
3. Live stack wiring behind `live_account.enabled` (default off).
4. `CRTOrderBridge.cs` + install notes in `phase74/execution/ninjatrader/README.md`.
5. Safety scans + ops checklist.
6. Manual NT replay on **demo/sim account in NT** if the user has one; otherwise first live day is 1 RTH contract with hand-flatten backup.

No live enable in config as part of the code PR. The user flips the flag after the AddOn is compiled and the account name is set.
