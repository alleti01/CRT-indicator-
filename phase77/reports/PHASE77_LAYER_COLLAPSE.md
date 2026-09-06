# Phase77 Layer Collapse Diagnostic

RTH bars: **8,400**

## Bottlenecks (frozen semantics — not tuned)

- ACCEPTANCE_REJECTION: UPPER_REJECTION never observed (blocks O1)
- ACCEPTANCE_REJECTION: LOWER_REJECTION never observed (blocks O2)
- ABSORPTION_PROXY: no BUYING/SELLING_ABSORBED_PROXY events (blocks O1/O2 reversal path)

## Key counts

- CONFIRMED_LONG: 100
- CONFIRMED_SHORT: 161
- UPPER_REJECTION: 0
- LOWER_REJECTION: 0
- BUYING_ABSORBED_PROXY: 0
- SELLING_ABSORBED_PROXY: 0

Only O5/O6 (failed-auction) setups fired in Jan 2024 pilot with current frozen layer rules.