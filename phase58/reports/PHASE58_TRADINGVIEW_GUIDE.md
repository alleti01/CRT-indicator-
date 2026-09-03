# Phase58 TradingView Guide

## Setup

1. Open TradingView and load **NQ1!** (or your NQ continuous contract).
2. Set the chart to **1-minute** timeframe.
3. Open Pine Editor (bottom panel).
4. Paste the contents of `phase58/pine/phase58_trader_v1.pine`.
5. Click **Add to chart**.
6. The indicator will display historical markers on closed bars.

## Understanding the Markers

| Marker | Meaning |
|--------|---------|
| Blue triangle up (ARM) | Trader became ARMED LONG — bullish context + structural location |
| Orange triangle down (ARM) | Trader became ARMED SHORT |
| Teal label up (LONG S:N) | TAKE LONG — score N met threshold |
| Maroon label down (SHORT S:N) | TAKE SHORT |
| Gray X (TO/INV) | Timeout or context invalidation — setup abandoned |
| Purple diamond (MISS) | Missed no chase — opportunity escaped |
| Red circle (STOP) | Exit at stop loss |
| Green circle (TGT) | Exit at target |
| Gray circle (TIME) | Exit at time limit |

## Background Colors
- Subtle green = bullish context
- Subtle red = bearish context
- No color = neutral

## Debug Table
Enable "Show Debug table" in settings to see real-time state at the rightmost bar:
- Current state (WATCH/ARMED/IN_LONG/etc)
- Context direction
- Evidence score
- Pullback depth
- Active reaction evidence

## Bar Replay Review

1. Open `review/review_dates_v1.csv` for the predeclared review dates.
2. Navigate to that date on the chart.
3. Use **TradingView Bar Replay** to step through bars one at a time.
4. Observe: Does ARMED appear BEFORE the move?
5. Does TAKE appear near the beginning?
6. Fill in `review/chart_review.csv` with your observations.

## Review Categories
- **A**: Excellent early entry
- **B**: Correct direction, acceptable timing
- **C**: Correct direction, late
- **D**: Correct opportunity, no entry
- **E**: False positive
- **F**: Wrong direction
- **G**: Chased move
- **H**: Correct pass
- **I**: Missed major move entirely

## Important Rules
- Do NOT change Pine parameters while reviewing.
- Parameters are frozen in `config/phase58_v1_frozen.json`.
- Log observations; do not tune.
