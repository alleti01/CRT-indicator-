# Phase69 Entry Freeze

Hash: `0da41f282174679f`

- pipeline: Phase58D variant E → Phase58F P4 → Phase58H H1 KEEP → M1 entry
- signal_source: phase60/diagnostics/cache/canon_full_phase60.parquet
- pine_reference: TV_REVIEW/phase59_canonical_live.pine
- entry: signal bar close T → entry next 1M open T+1
- direction: direction_m1 from canonical pipeline
- atr: SMA(14) of range on 1M
- m0_stop_atr: 1.0
- m0_target_r: 2.5
- m0_max_hold_min: 60
- collision: STOP_FIRST
- cost: NQ round-turn $14.50 normalized to R
- N trades: 36,174
- Range: 2017-10-01 19:03:00-05:00 → 2026-08-28 14:18:00-05:00