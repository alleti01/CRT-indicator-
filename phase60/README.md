# Phase60 — Causal Developing-HTF Canonicalization

**Status:** Research baseline (not production).

## Lineage

| Phase | Role |
|-------|------|
| Phase59 ORIGINAL | Historical **contaminated** benchmark (HTF future leakage) |
| Phase59H | Invalid lookahead parity experiment |
| Phase59I | Leakage discovery + CAUSAL A/B audit |
| **Phase60** | **Causal developing-HTF candidate** (CAUSAL B semantics, cleaned) |

## Architecture

```
1M market data
    ↓
Developing 5M / 15M state (incremental, strictly causal)
    ↓
Phase58D → P4 → H1 → Entry → M1 management (frozen, unchanged)
```

## Key rules

- No strategy optimization in Phase60
- No parameter changes
- HTF construction/consumption is the ONLY allowed correction
- Completed HTF history for swings/structure; developing bucket for current OHLC/momentum

## Layout

- `python/` — developing HTF engine, arrays, context maps, pipeline
- `tools/` — tests, baseline runner, parity export
- `pine/` — Pine developing-HTF implementation
- `reports/` — audit outputs
- `diagnostics/` — cached trades, parity datasets
