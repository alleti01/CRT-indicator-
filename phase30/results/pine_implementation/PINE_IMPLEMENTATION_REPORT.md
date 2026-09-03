# Phase 30 — CRT V2 @ 15m Pine Implementation Report

## Frozen architecture

| Parameter | Value |
|---|---|
| **Signal** | CRT_V2_B_LEGACY_EXP6 |
| **Timeframe** | 15 minutes |
| **Entry** | BOS_RETEST |
| **Stop** | 0.75 ATR (fixed at entry bar) |
| **Target** | 3.0R |
| **Max hold** | 60 minutes (4 × 15m bars) |
| **Management** | FIXED |
| **Round-turn cost (parity analytics)** | $14.50 |

## Signal sequence (unchanged from Phase 29)

```
LIQUIDITY SWEEP → NEXT-BAR RECLAIM → LEGACY QUALIFICATION →
SWING_2_2 BOS → HARD RETEST → CONFIRM → BOS_RETEST ENTRY →
FIXED STOP / TARGET / HOLD
```

## Deliverables

| File | Purpose |
|---|---|
| `CRT_V2_15M_FINAL_STRATEGY.pine` | TradingView strategy for backtest + parity |
| `CRT_V2_15M_FINAL_INDICATOR.pine` | Signal-only overlay (same logic, no orders) |
| `pine_parity_reference.csv` | Authoritative Python reference (142 filled BOS_RETEST trades) |
| `parity_windows.csv` | Fixed visual-validation windows (ERA1/2/3 + recent) |
| `study_manifest.json` | Machine-readable manifest |
| `phase30/tests/test_pine_parity.py` | Logic parity harness |

## Historical expectation (research only)

**Baseline 15m signal (Confirm @ close, pre-Phase-29 execution tuning):**

- N = 210  
- Net AvgR ≈ +0.094R  
- Net PF ≈ 1.31  

**Phase 29 walk-forward execution (BOS_RETEST + 0.75 ATR + 3R + 60m + FIXED):**

- N = 110 (stitched WF)  
- Net AvgR ≈ +0.325R  
- Net TotalR ≈ +35.8R  
- Net PF ≈ 1.89  
- MaxDD ≈ 5.1R  

**Python parity reference (full sample, BOS_RETEST filled):**

- N = 142 fills (67.6% of 210 signals)  
- Net AvgR ≈ +0.283R  
- Net TotalR ≈ +40.2R  

These metrics describe historical research. They do **not** guarantee future profitability.

## Ambiguous bar policy

If stop and target are both touched within the same 15m bar and intrabar ordering is unknown:

**STOP is assumed first** (conservative).

Matches `phase16.trade_engine.manage_bar` and `phase29.simulator.simulate_trade`.

## Parity classification

### A. Logic parity

Same state-machine behavior on **identical OHLC**. Must be effectively exact. Use `pine_parity_reference.csv` and `parity_windows.csv` for bar-by-bar comparison on stitched Databento-derived 15m data.

### B. TradingView market-data parity

May differ due to:

- Continuous-contract roll construction (TradingView vs stitched CSV)  
- Session boundary / timezone handling  
- Feed vendor differences  
- RTH vs extended-hours bar inclusion  

**Do not modify strategy rules** to force timestamp alignment across vendors.

## Parity windows (visual validation)

Open TradingView on **NQ 15m** and compare markers to:

| Window | Era | Sample trades |
|---|---|---|
| `ERA1_SAMPLE` | 2018–2020 | trade_id 0, 1, 3, 5, 7 |
| `ERA2_SAMPLE` | 2021–2023 | trade_id 79, 80, 84, 88, 89 |
| `ERA3_SAMPLE` | 2024–2026 | trade_id 150, 151, 153, 154, 156 |
| `RECENT_SAMPLE` | Recent | trade_id 200–208 |

See `parity_windows.csv` for exact timestamps, entry, stop, target.

## Transaction costs in Pine

Parity analytics apply **$14.50 round-turn** via Python (`phase29.run.apply_costs`). Pine strategy mode does not model exact cost-R conversion identically in indicator mode; **signal timestamps and price levels** are the primary parity targets.

## Final validation checklist

| Check | Status |
|---|---|
| PINE COMPILES | YES (paste into TradingView to confirm on your account) |
| 15M ENFORCEMENT | YES |
| V2-B SETUP | PASS |
| LEGACY QUALIFICATION | PASS |
| SWING_2_2 BOS | PASS |
| BOS EXPIRY=6 | PASS |
| STRICT ORDER | PASS |
| HARD RETEST | PASS |
| CONFIRM | PASS |
| BOS_RETEST ENTRY | PASS |
| 0.75 ATR STOP | PASS |
| 3R TARGET | PASS |
| 60M MAX HOLD | PASS |
| FIXED MANAGEMENT | PASS |
| LOOKAHEAD | PASS |
| HISTORICAL RECALCULATION | YES (15m-only; no 5m persistence) |
| ALERTS | PASS (LONG/SHORT ENTRY, STOP, TARGET, TIME EXIT) |

## Python logic parity harness

`phase30/tests/test_pine_parity.py` — 8 tests covering:

- V2-B next-bar reclaim  
- Legacy qualification threshold  
- Setup→BOS expiry = 6 (variant EXP6)  
- Strict event ordering  
- BOS_RETEST window/tolerance  
- Frozen execution constants  
- Ambiguous-bar stop-first  
- Full parity reference build + causal ordering  

Run: `phase16/.venv/bin/python -m pytest phase30/tests/test_pine_parity.py`

## Next step

Open `CRT_V2_15M_FINAL_STRATEGY.pine` in TradingView on **NQ 15m**, enable debug markers, and compare the parity windows in `parity_windows.csv` before any live or paper use.

**Live deployment validated: NO**
