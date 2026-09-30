# Forward shadow spec

Live orders stay as they are. This log is research.

Turn it on only by calling `append_shadow_record`. It writes one JSON line and returns the order unchanged. Nothing in the order path calls it today.

## Batch

Next 20 vision-confirmed MNQ signals with Entry, SL, and TP1.

During that batch, do not add a skip threshold and do not change F1 or F2. They stay observations. `SHADOW_DECISION` stays `WOULD_TAKE`.

## Fields written at signal time

- signal_id, timestamp, direction
- CDX entry, planned entry (the CDX entry), CDX SL, CDX TP1
- native_R
- flips_3, flips_6, flips_10, opposite_signal_bars_ago
- efficiency_6, efficiency_10, overlap_6, overlap_10
- atr_14, range_6_atr, range_10_atr, native_R_atr
- tp1_native_R
- F1_RECENT_WHIPSAW, F2_ADVERSE_FILL, F3_RIBBON_CONFLICT (null until a ribbon number exists)
- SHADOW_DECISION = WOULD_TAKE
- stop distance from the CDX entry
- risk per 1 MNQ at $2 per point
- max quantity at $50, $75, and $100
- configured cap, if one is set later, and RISK_ACCEPT or RISK_REJECT
- shadow quantity

Do not write MFE, MAE, or any bar from after the signal into the decision.

## After the trade resolves

Append the outcome beside the original row. Do not edit the signal-time decision.

- TP1_BEFORE_SL
- SL_BEFORE_TP1
- unresolved

Also store the fill when it exists, execution_R, and the adverse displacement. Those are descriptions of the fill, not inputs that change the earlier decision.

## Counts to keep

- would-take winners
- would-take losers
- would-skip winners
- would-skip losers

Winners wrongly skipped is the number that matters. With no frozen skip, that count stays 0 until a later batch freezes a predicate.

## Not enabled

`EVAL_SURVIVAL_MODE` is not turned on. Dollar caps are reported at $50, $75, and $100. They do not change contract quantity.
