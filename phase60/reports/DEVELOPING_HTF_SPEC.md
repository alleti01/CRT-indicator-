# Phase60 — CAUSAL B Developing HTF Specification

## Scope

This document defines **CAUSAL B** semantics for Phase60. At every 1M decision timestamp `t`, the system may use only information from timestamps `<= t`.

## Developing 5M

For bucket beginning at `T` (floor to 5 minutes):

| 1M bar | O5 | H5 | L5 | C5 |
|--------|----|----|----|----|
| T | open[T] | high[T] | low[T] | close[T] |
| T+1 | open[T] | max(high[T:T+1]) | min(low[T:T+1]) | close[T+1] |
| ... | open[T] | max(high[T:T+k]) | min(low[T:T+k]) | close[T+k] |
| T+4 | open[T] | max(high[T:T+4]) | min(low[T:T+4]) | close[T+4] |

At `T+5` the bucket resets.

## Developing 15M

Identical semantics with 15-minute buckets.

## Completed vs developing consumption

| Feature class | Source |
|---------------|--------|
| 5M swing HH/HL/LH/LL | **Completed** 5M bars only (`m5_completed_j`) |
| 5M momentum | **Developing** close vs completed close `[j-lb]` |
| 15M swing structure | **Completed** native 15M bars only |
| 15M momentum / range / impulse | **Developing** current OHLC + completed history |
| 5M location pullback | **Developing** OHLC in current window + completed prior bars |
| 1M reaction | 1M data only (unchanged) |
| HTF ATR normalization | **Completed** bucket ATR (no future bucket ATR) |

## Causality invariant

For every decision at bar index `i`:

```
max_source_timestamp_used <= m1_idx[i]
```

Phase60 tracks `source_ts_ms[i] = m1_idx[i]` for developing OHLC fields.

## Implementation

- `phase60/python/developing_htf.py` — vectorized + sequential builders
- `phase60/python/arrays.py` — MarketArrays / MTFArrays construction
- `phase60/python/context_maps.py` — causal feature evaluation

## Invalid references

- Phase59 ORIGINAL (leaked HTF) — forensic only
- Phase59H (`lookahead_on`) — invalid parity target
- LW-063138 — depended on leaked HTF; not a Phase60 parity target
