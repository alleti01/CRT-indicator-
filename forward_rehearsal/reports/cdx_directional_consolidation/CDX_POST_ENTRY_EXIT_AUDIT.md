# CDX post-entry exit audit

Live evaluation order on each completed 1-minute bar while a position is open. Source: `phase74/runtime/live_stack.py` `_on_bar_body`, then `phase74/quality/trail.py`, then `phase73/trader/management.py` `evaluate_exit`.

The entry bar is ignored (`bar.timestamp <= entry_time`).

## 1. WICK_TARGET

Predicate: `_wick_target` is set, and the bar trades through it (long high, short low).

Data: unswept 3-minute wick from `phase74/quality/wick_targets.py`. The stop distance is mirrored around the fill.

When: before the trail, on a completed 1-minute bar.

Causal: yes. The wick is taken from bars already closed.

Before +0.50R: yes.

Currently live on a chart-stop trade: no. `_apply_chart_stop` sets `_wick_target = None`. It did fire on `2026-09-28T11:42:00Z` and the broker flatten was 30633.25, six points under the 30639.25 fill.

## 2. PROFIT_CAP

Predicate, long: `bar.high >= fill + min(3 * risk, 1000 / point_value)`. Short uses the low. `point_value` in the live config is 14, so the dollar cap is about 71.43 points at 7 MNQ.

Data: the completed 1-minute bar and the fill.

When: inside `TrailOverlay._cap_or_reversal`, before the reversal check. This path is active because `profit_cap_dollars` is 1000.

Causal: yes.

Before +0.50R: only if the cap is inside 0.50R, which it is not at these stop distances.

Currently live: yes. It is a profit exit, not a chop exit.

## 3. REVERSAL

Predicate: a prior bar has already traded at least `mgmt.risk` beyond the fill. Then a later bar trades 10 points back from that extreme (long low, short high). The extreme updates only after the pullback check, and only on a bar whose favorable extreme is at least 1R.

After a chart stop is applied, `mgmt.risk` is the distance from the fill to the CDX stop. That is execution R. The rule cannot fire before +1 execution R, and therefore cannot fire before +0.50R.

Data: completed 1-minute high and low. Timeframe of the check is 1 minute. The 10 points are not an overlap, efficiency, or ribbon calculation.

Causal: yes.

Currently live: yes. This is the only live post-entry rule that flattens on a pullback. The paper journal has 2 `REVERSAL` rows. On the broker-fill path of the 5 native trades, the same predicate is reached 4 times, and each of those was after TP1 had already traded.

## 4. M0_STOP

Predicate: the 1-minute bar trades through `mgmt.stop_price`. With a chart stop, that price is the CDX SL. Same-bar stop and target use STOP_FIRST.

When: only if the trail did not already exit.

Causal: yes.

Before +0.50R: yes.

Currently live: yes. This is the initial invalidation, not a chop exit. The 13:51 short exited here.

## 5. M0_TARGET

Predicate: the bar trades through `mgmt.target_price`.

Currently live as a paper flatten: no. The trail calls `hide_m0_target`, which pushes the paper target 100R away. The NinjaTrader resting target is separate and can still fill. That resting target is the dollar cap or the 2.5R price sent with the order, not automatically CDX TP1.

## 6. MAX_HOLD_60M

Predicate: minutes since entry `>= 60`, exit at the bar close.

`max_hold_minutes` is 60 in `phase73/config/default.json`. There is no off switch on this one.

Causal: yes.

Before +0.50R: yes.

Currently live: yes, if the trade is still open. It is a time exit. The native sample did not hit it. V2 research does not use it.

## 7. TIME_PROGRESS_15M_LT_1R

Predicate: `enable_time_progress_exit` and minutes `>= 15` and MFE `< 1R`.

`enable_time_progress_exit` is false.

Currently live: no.

Before +0.50R: it could, if it were turned on.

## 8. SKIP_CHOP and the sideways overlay

Predicate: the prior 20 one-minute bars have a range under `2 * ATR` (`SKIP_CHOP`). The sideways efficiency/overlap score lives in `phase74/quality/sideways.py` and is not called by the live stack.

These run before a fill, or not at all. `quality_gates.filter_signals` is false, so SKIP_CHOP does not even block a new entry.

They cannot flatten an open trade.

## 9. Broker stop and target

`STOP_FILLED` and `TARGET_FILLED` come from NinjaTrader when the working orders fill. They are not a chop calculation. A manual close does not emit either name, which is why a hand flatten leaves no exit price in the audit.

## 10. What is not an exit

Overlapping candles, alternating colors, low efficiency, a slow push, a return toward entry, and a flat stretch of small bars have no live flatten predicate.

No ribbon series is stored, so an entry-plus-ribbon reclaim cannot be measured. It was not invented.
