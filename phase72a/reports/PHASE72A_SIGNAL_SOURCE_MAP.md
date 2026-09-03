# Phase72A Signal Source Map

## Hash authority

- **Signal hash:** `0da41f282174679f`
- **Trader hash:** `b6adfc04e8885a3d`
- Computed by `phase69/python/entry_freeze.py::config_hash()`

## Authoritative signal stream

- **File:** `phase60/diagnostics/cache/canon_full_phase60.parquet`
- **Filter:** `h1_status == 'KEEP'` → **36,174** signals
- **Pipeline:** Phase58D variant E → Phase58F P4 → Phase58H H1 → M1 entry

## Python generation stack

| Stage | Module |
|-------|--------|
| Raw 1M ARMED/TAKE | `phase58/research/trader_engine.py` |
| Opportunity memory + variant E | `phase58d/research/engine.py` |
| Evidence | `phase58d/research/evidence.py` (Phase60 patch via `phase60/python/evidence.py`) |
| Confidence + P4 | `phase58f/research/confidence.py`, `policies.py` |
| H1 filter | `phase58h/research/filters.py` |
| Causal HTF | `phase60/python/developing_htf.py`, `context_maps.py` |

## Pine implementation (Phase72A)

- **File:** `TV_REVIEW/phase72a_autonomous_trader.pine`
- Built from Phase59 signal stack with **Phase60 causal HTF** (no `lookahead_on`)
- Phase59 Pine is **reference only** — NOT authoritative for hash `0da41f282174679f`

## Entry scheduling

- Signal on closed bar **T** (`barstate.isconfirmed`)
- Entry at **T+1 open**
- States: FLAT → PENDING_* → *_ACTIVE

## HTF dependencies

- Developing 5M/15M buckets from 1M chart
- Completed 5M/15M via `request.security(..., lookahead_off)` for pivots and m15H4/L4/C12

## ATR

- `ta.sma(high - low, 14)` — NOT `ta.atr()` RMA
- Frozen at entry for stop/target/T5 denominator

## Session

- 24h continuous; timezone America/Chicago in Python source