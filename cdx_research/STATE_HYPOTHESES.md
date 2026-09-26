# State / cooldown hypotheses

CDX does **not** look stateless one-bar RSI.

## Observed

1. **Opposite reset is allowed quickly.** s01 and s13 show LONG then SHORT within ~10–20 minutes after the first trade fails or the bounce extends.
2. **Same-direction cooldown is short or absent.** s07, s11, s12 repeat the same side.
3. **Not one-signal-per-session.** s11 has many markers across London/NY.
4. **Arming is plausible.** Many bars look like “near extreme” without a marker. A prior impulse + pullback + rejection trigger would explain suppression. **Not measurable until OHLCV exists for these dates.**
5. **Stop/target reset** is visible in boxes but is **management**, not used as an entry feature.
6. **HTF table** (1m/5m/15m/1h bias) is treated as `UNTRUSTED_FOR_HISTORICAL_LABELING`. Do not arm from the live table when scoring old markers.

## Test plan (when Sep 6–21 1m data exists)

- Min bars between same-direction signals (empirical distribution)
- Min bars after opposite
- Whether a 20/30-bar new extreme is required (arm)
- Whether a rejection wick is the trigger
- Whether RTH vs overnight changes thresholds

## Working hypothesis (not frozen as CDX)

```
armed_long  = near rolling low after a down impulse
trigger     = bullish rejection close
emit LONG
cooldown_same_dir ≈ 8 bars (exploratory)
opposite allowed immediately
```
