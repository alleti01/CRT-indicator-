# Phase72A Entry ↔ Alert Logic Map

**Source:** `TV_REVIEW/phase72a_autonomous_trader.pine` (frozen SHA256 `d75ff747…cc1f`)  
**Audit copy:** `TV_REVIEW/phase72a_latency_audit.pine` (Layer C added only)

## Event Timeline (Frozen Semantics)

```
Bar T (close)     → SIGNAL_LONG / SIGNAL_SHORT  (TAKE decision)
Bar T+1 (open)    → ENTER_LONG / ENTER_SHORT    (executable entry)
```

Header comment (lines 7–8): *Signal on closed bar T → canonical ENTRY at open T+1*

---

## Primary Variables

| Variable / Condition | Defined | Becomes True | Bar Ref | Prior Bar? | Plot | Alert | Entry | Causal |
|---------------------|---------|--------------|---------|------------|------|-------|-------|--------|
| `pendingTake` | L878 | Canonical TAKE at bar T | T | No | indirect (dbg table) | No | gates T+1 | YES |
| `pendingSignalBar` | L880 | Set to `bar_index` on TAKE | T | No | No | No | T+1 ref | YES |
| `pendingDir` | L879 | LONG/SHORT on TAKE | T | No | No | No | T+1 | YES |
| `lastAction := SIGNAL_LONG` | L1241 | Phase58D TAKE + P4/H1 KEEP | T | No | via showTake label | via exportParity alertcondition | No | YES |
| `lastAction := ENTER_LONG` | L1016 | `pendingTake && bar_index==pendingSignalBar+1` | T+1 | No | showEntry label | via exportParity alertcondition | YES open | YES |
| `enterLongFlag` | L1582 | `lastAction=="ENTER_LONG"` | persists until next action | **Persists** | Data Window | alertcondition | No | Edge issue |
| `signalLongFlag` | L1580 | `lastAction=="SIGNAL_LONG"` | 1 bar typically | Overwritten T+1 | Data Window | alertcondition | No | YES at T |
| `showTake` label `SIGNAL_LONG` | L1243–1245 | Same bar as TAKE | T | No | YES | No | No | YES |
| `showEntry` label `ENTER_LONG` | L1018–1020 | Entry bar T+1 | T+1 | No | YES | No | YES | YES |
| `pyExpected` ghosts | L1545–1550 | Hardcoded unix ms | fixed | No | YES yellow | No | No | N/A display |
| `alertcondition` P72B ENTER_LONG | L1606 | exportParity + enterLongFlag | Any bar lastAction set | **No edge detect** | No | YES if enabled | No | Misleading |
| `alert()` production | — | **NOT PRESENT in frozen script** | — | — | — | — | — | — |

---

## State Machine (Layer A)

| State | Entry trigger | Marker |
|-------|--------------|--------|
| WATCH (p58State=0) | Context + location score | — |
| ARMED (p58State=±1) | Up to 15 bars (`armedTimeoutBars`) | ARMED/WAIT optional |
| TAKE (decE=="TAKE" + filters) | `pendingTake:=true`, SIGNAL_* | SIGNAL_LONG/SHORT |
| ENTER | Next bar if FLAT | ENTER_LONG/SHORT |
| IN_TRADE | posState LONG_ACTIVE/SHORT_ACTIVE | stop/target lines |

---

## Backdating Search Results

| Pattern | Found? | Location | Impact |
|---------|--------|----------|--------|
| `offset=` on plotshape | NO | — | — |
| `label.new(bar_index-N,...)` for ENTER | NO | ENTER uses current `bar_index` | None |
| `plotshape(... offset=-N)` | NO | — | — |
| `signalBar := bar_index - 1` | YES | L1539 DEBUG_MANUAL only | Disabled default |
| `valuewhen` for entry marker | NO | — | — |
| Retrospective swing for entry | NO | Swings for evidence only | — |

**Conclusion:** Layer A does NOT backdate ENTER markers. ENTER label is placed at `bar_index` on the entry bar (T+1).

---

## Single Source of Truth — Current vs Required

### Frozen production script

- **Marker SIGNAL:** `lastAction == "SIGNAL_LONG"` at bar T
- **Marker ENTER:** `lastAction == "ENTER_LONG"` at bar T+1
- **Alert (if exportParity):** level-triggered flags, NOT edge-triggered
- **Production webhook docs:** `SIGNAL_LONG` / `SIGNAL_SHORT` events (not ENTER)
- **No `alert()` in frozen script**

### Audit script (Layer C fix)

- `executableLongNow = latEnterLongEdge` (one-shot on ENTER transition)
- Same edge drives `LAT_ENTER` marker + `alert()` JSON payload + shared `event_id`

---

## Event Time Definitions

| Event | Pine time | Real-time knowable |
|-------|-----------|-------------------|
| OPPORTUNITY_TIME | `curOppStartSi` bar close | Bar T0 close |
| TAKE_TIME | `pendingSignalBar` bar close | Bar T close |
| ENTRY_DECISION_TIME | Same as TAKE (decision to enter) | Bar T close |
| EXECUTABLE_ENTRY_TIME | `pendingSignalBar + 1` bar open | Bar T+1 open |
| ALERT_GENERATION_TIME | TradingView `timenow` at fire | After bar close if once_per_bar_close |

---

## Bar-Close Semantics

| Setting | Value |
|---------|-------|
| Main logic gate | `barstate.isconfirmed` (L986) |
| calc_on_every_tick | indicator default (false for logic block) |
| Entry price | `open` on T+1 (L1005) |
| Recommended alert freq | `alert.freq_once_per_bar_close` |
| Correct TV alert type | **Any alert() function call** (audit script) OR recreate alert after script change |

---

## Alert Configuration Audit

### Frozen script problem

1. `exportParity` defaults **false** → `alertcondition` names never true
2. Production webhooks reference `SIGNAL_LONG` JSON — matches TAKE not ENTER
3. No `alert()` → alerts must use old snapshot OR manual alertcondition with exportParity enabled
4. **After any Pine edit: DELETE old alert, CREATE new alert**

### Correct configuration (audit script)

| Purpose | Alert trigger | Frequency |
|---------|--------------|-----------|
| Executable entry webhook | Any `alert()` function call | Once per bar close |
| TAKE diagnostic (optional) | Same, separate SIGNAL alert | Once per bar close |

### Common misconfiguration causing apparent delay

| Misconfig | Symptom |
|-----------|---------|
| Alert on SIGNAL, chart shows ENTER | 1-bar offset (1 min) |
| Alert on stale script snapshot | Multi-bar/minute unexplained delay |
| Alert on `P72B ENTER_LONG` with exportParity off | Never fires or stale |
| Confusing SIGNAL label with ENTER | "ENTER" perceived at TAKE time |
| `showPyExpected` ghost overlay | Yellow marker at wrong time |

---

## 18:49 ENTER → 18:59 Alert — Traced Answer

**Not caused by:** Layer A backdating (verified — no offset/backdate for ENTER)

**Most likely composite cause:**

1. **(D + E)** Marker and alert use **different event types** — chart shows `SIGNAL_LONG`/`ENTER_LONG` while webhook fires `SIGNAL_LONG` at a **different bar's close** OR user compares TAKE marker time to a later alert
2. **(I) Alert configuration** — frozen script lacks production `alert()`; webhooks use manually configured JSON on `SIGNAL_*` with `exportParity` alertconditions disabled by default
3. **(F) Old alert snapshot** — TradingView preserves script version from alert creation
4. **10-minute gap** is NOT explained by legitimate T+1 (1 bar). Requires either wrong event pairing, different trade, stale alert, or live bar not matching reviewed historical marker

**Not primary cause:** Webhook network latency (would be sub-second to few seconds, not 10 minutes)
