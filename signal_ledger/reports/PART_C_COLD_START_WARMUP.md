# Part C — Cold-Start Warmup Guard

**Status:** Implemented + **verified** — see `PART_C_VERIFICATION.md`  
**Layer A signals:** Unchanged — export/instrumentation only (regression confirmed)

---

## Design (per Part B verdict)

Warmup NaN is a **cold-start / script-reload** artifact, not steady-state live failure. Fix is a **bounded grace period** after script init, not a permanent per-bar HTF gate.

---

## Bounded window (documented bound)

```
gldHtfWarmupMinBars = 12 × 15 + swingPeriod
```

| Component | Value | Rationale |
|-----------|-------|-----------|
| Deepest HTF lookback | **12 completed 15M bars** (`m15C12`) | 12 × 15 = **180** 1M bars ≈ 180 minutes |
| Pivot confirmation lag | **`swingPeriod`** (default **5**) | 1M pivot rightbars confirmation |
| **Total (default)** | **185** 1M bars | `12 * 15 + 5` |

Early latch: if `m15C12`, `m15H4`, and `m15L4` are all non-`na` before bar 185, `gldHtfWarmupReady` latches true immediately (data ready before time bound).

After latch: **`gldHtfWarmupReady` stays true** until next script reload (`var` reset on `barstate.isfirst`). No ongoing HTF scan in steady state.

---

## Implementation summary

| Mechanism | Behavior |
|-----------|----------|
| `gldHtfWarmupReady` | Latched `var bool`; false only during cold-start window after reload |
| `gldInColdStartWindow` | `not gldHtfWarmupReady and barsSinceInit < gldHtfWarmupMinBars` |
| `GLD_htf_warmup_ready` | Data-window export (1/0) |
| `GLD_pass_reason_code` | **1** = `PASS_INSUFFICIENT_WARMUP` during cold-start window only; **0** otherwise |
| `GLD_evidence_threshold_*` | **`na` export** during cold-start (not misleading false from init); **unchanged formula** once warm |
| Arm-total three-state export | See below |
| `SCRIPT_INIT` alert + `GLD_script_init_utc_ms` | Once per reload (closes Part B check 2 gap) |

---

## Arm-total three-state export

| `GLD_arm_total_*_prov` | Meaning | `GLD_arm_total_*` value |
|------------------------|---------|-------------------------|
| **0** | Cold-start / not yet warm | **`na`** |
| **1** | Fresh computed this bar (ARMED path) | Layer A `total` |
| **2** | Stale hold (prior bar assignment) | Last assigned `total` |

Init changed from `0.0` to **`na`** for `gldSnapArmTotalLong/Short` — eliminates false “computed zero” during cold-start.

---

## Reload / init event logging

On script reload (`barstate.isfirst`):

- Captures `gldScriptInitBarIndex`, `gldScriptInitTimeUtcMs`
- Resets `gldHtfWarmupReady`, `gldScriptInitLogged`

On first confirmed bar at init index:

- **`GLD_script_init_utc_ms`** plot (single-bar spike)
- **`SCRIPT_INIT` alert** JSON: `script_init_utc_ms`, `script_init_bar_index`, `htf_warmup_min_bars`

Future audits can correlate any signal window to a hard reload timestamp.

---

## Layer D gate behavior outside cold-start window

When `gldInColdStartWindow == false` (steady state after warm latch):

| # | Gate | Pre-Part-C behavior preserved? |
|---|------|-------------------------------|
| 1–2 | `evidence_threshold_long/short` | **Yes** — `p58State==±1 and snap>=takeThreshold` |
| 3–6 | `p4_keep_*`, `h1_keep_*` | **Yes** — snapshot reads unchanged |
| 7 | `gate_open` | **Yes** — `gldSnapGateOpen` |
| 8–9 | `decide_e_long/short` | **Yes** — isNew-gated snapshots |
| + | `armed_*`, `not_in_cooldown`, `take_*` | **Yes** — unchanged |

**Only during cold-start window:** `evidence_threshold_*` exports `na` + `pass_reason_code=1`; arm-total prov=0 / value=na.

---

## Python support

- `signal_ledger/config.py` — provenance/reason constants, `GLD_OPTIONAL_COLS`
- `signal_ledger/gate_export.py` — loads optional Part C columns when present
- **Part D** — ledger NaN handling for three-state distinction (next step)

---

## Hold status

Part C complete. **Hold on real TV export remains ACTIVE** until **Part D** (ledger NaN handling) is confirmed, then reassessed together.
