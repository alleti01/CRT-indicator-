# Phase72 HTF Causality Audit

## Scope split

| Layer | HTF usage | Phase72 verdict |
|-------|-----------|-----------------|
| **Phase71 frozen trader** | None — 1M OHLC only for stop/target/MFE/T5 | **PASS** (no HTF in management path) |
| **Phase60 frozen signals** | Precomputed developing HTF buckets in parquet | Audited at freeze time; not re-mutated in Phase71/72 |
| **Phase59 Pine (signals)** | `request.security` on 5M/15M with `lookahead_on` | Documented alignment with Python developing HTF |

## Phase71 unified trader Pine

File: `TV_REVIEW/phase71_unified_trader.pine`

- **`request.security` calls: 0**
- ATR: `ta.sma(high - low, 14)` on chart timeframe (1M)
- Management gated on `barstate.isconfirmed`

No HTF leak possible in management overlay.

## Phase59 signal Pine — security inventory

File: `TV_REVIEW/phase59_canonical_live.pine`

| Call | Timeframe | Expression | Lookahead |
|------|-----------|------------|-----------|
| 1 | 15 | close, close[1], high, low, open | `barmerge.lookahead_on` |
| 2 | 5 | close, open, high, low, close[1], high[1], low[1] | `lookahead_on` |
| 3 | 5 | ta.sma(high-low, 14) | `lookahead_on` |
| 4 | 15 | ta.sma(high-low, 14) | `lookahead_on` |
| 5 | 5 | time | `lookahead_on` |
| 6 | 15 | time | `lookahead_on` |
| 7 | 5 | ta.pivothigh / pivotlow | `lookahead_on` |
| 8 | 15 | high[4], low[4], close[12] | `lookahead_on` |

### Causal justification (documented in Pine)

Pine comment block (lines 102–105) states:

> Frozen Python ffills the current-period HTF label at period start with precomputed bucket OHLC; TV `lookahead_off` lags ~5 bars (confirmed bar only).

`lookahead_on` is used **deliberately** to match Python `developing_htf.py` bucket semantics where the current incomplete HTF candle is visible from the first 1M bar of that period — not final-period ffill of the **completed** candle.

### What would FAIL

- Using final HTF high/low/close before the HTF period completes without developing-bucket logic
- Period-start ffill of **completed** prior candle labeled as current
- Any HTF value with `known_at` after the 1M timestamp where it is consumed

Phase59/60 alignment was validated in prior phases; Phase72 confirms **trader management does not reintroduce HTF**.

## Python resampling (signal path)

Signal generation uses frozen Phase60 parquet — not live resample in Phase71 trader.

See `phase72/reports/PHASE72_RESAMPLING_AUDIT.md` for grep inventory of `merge_asof`, `ffill`, `resample` in research code paths.

## Verdict

**HTF CAUSALITY (trader path): PASS**

**HTF CAUSALITY (full TV stack): APPROXIMATE** — requires Phase59+Phase71 wired end-to-end manual verification on TradingView.
