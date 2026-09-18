# M0 execution mapping

Canonical source (frozen, not copied):

`phase73/trader/management.py` → `build_management` / `evaluate_exit`

| Spec | Value |
|---|---|
| STOP | 1.0 × ATR (`stop_atr`) |
| TARGET | 2.5R (`target_r`) |
| MAX HOLD | 60 minutes |
| COLLISION | `STOP_FIRST` |

Phase85 does **not** redesign management. It calls `build_management` with:

- `entry_price` = **actual NinjaTrader fill**
- `signal_atr` from the Phase73 decision context
- frozen `Phase73Config`

Not used as fill authority: TradingView marker, webhook estimate, Python last trade, signal close.

Ledger stores both `expected_entry` and `fill_price`, plus `slippage_points` / `slippage_ticks`.

After fill: `PLACE_PROTECTION` with those stop/target prices.  
OCO: C# submits stop + target with a shared OCO id (`Account.CreateOrder` `oco` argument).  
TARGET fill should cancel STOP; STOP fill should cancel TARGET.

No breakeven, ATM, trail, partials, or runner in Phase85.
