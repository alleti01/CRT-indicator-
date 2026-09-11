# Prop dollar risk — $2,000 DD / 50k / 1 NQ

**Date:** 2026-09-11  
**Status:** Implementing in Phase74 paper. Frozen Pine and Phase73 engine stay unchanged.  
**Account:** $50k funded, **$2,000** drawdown, 1 NQ, **$20/point**.

---

## 1. Problem

Quality gates skip chop / late TAKEs, but risk is still **1.0 × live 14-bar ATR**. At the cash open that ATR was **31–38 points** ($620–$760). That is 31–38% of the $2,000 DD on one stop.

Day halt was **3 losers or −2R**. −2R at 8-point ATR is $320; −2R at 38-point ATR is $1,520. R does not protect this account.

Friday 4:14 AM trail **+$1,120** was already a banked day; the bot kept taking trades and later opened a 38-point short.

---

## 2. Rules (locked)

Halt means **no new entries** on the America/New_York date. An open trade still manages (stop / trail / max hold). Halt clears at the next NY date.

| Rule | Setting | Log reason |
|------|---------|------------|
| Max 1R | **15.0 points = $300** | `SKIP_ATR_CAP` if live ATR > 15. Do **not** clamp the stop. |
| Day loss | **2 losers** or **−$400** | `HALT_DAY_LOSERS` / `HALT_DAY_DOLLARS` |
| Day win lock | **2 winners** or **one trade ≥ +$500** | `HALT_DAY_WINS` / `HALT_DAY_BIG_WIN` |
| Give-back | Peak ≥ **+$400** and P&L ≤ peak − **$300** | `HALT_DAY_GIVEBACK` |

Dollars = `net_R * entry_ATR_points * 20`. Do not use `contracts.multiplier` (MNQ-sized) for this card.

Existing `safety.daily_loss_limit` ($500) stays as a backstop.

---

## 3. Gate order

Unchanged chop / false-break / late-move, then:

`SKIP_ATR_CAP` if `live_ATR > max_atr_points` (default 15).

---

## 4. Halt check order

1. `losers >= 2` → `HALT_DAY_LOSERS`  
2. `realized_dollars <= -400` → `HALT_DAY_DOLLARS`  
3. any closed trade `dollars >= 500` → `HALT_DAY_BIG_WIN`  
4. `winners >= 2` → `HALT_DAY_WINS`  
5. `peak >= 400` and `realized <= peak - 300` → `HALT_DAY_GIVEBACK`

---

## 5. Config

`phase74/config/default.json` `quality_gates`:

```json
"max_atr_points": 15.0,
"nq_point_value": 20.0,
"day_max_losers": 2,
"day_max_loss_dollars": 400.0,
"day_max_winners": 2,
"day_big_win_dollars": 500.0,
"day_giveback_arm_dollars": 400.0,
"day_giveback_dollars": 300.0
```

`day_max_loss_r` is removed from the live halt (R is not the authority).

---

## 6. Tests / replay

- Unit: ATR cap skip vs take at 15.00  
- Unit: each halt reason  
- Replay `paper_trades.csv` with gates + this card; print NQ dollars per NY date  

Out of scope: changing Pine stop ATR, 2-lot, RTH-only window, fixing the 9:39 AM `REVERSAL_WATCH` freeze (separate). ATR cap would have skipped that 31-point short.
