# Volatility Event Definitions

Timezone: `America/Chicago`

## Horizons
- short=6, medium=24, long=72 bars
- forward horizons=(1, 3, 6, 12, 24) bars

## Percentile window
- 16800 bars (~60 CME session days)
- LOW <= 0.2, HIGH >= 0.8

## Shock de-duplication
A shock event fires on first bar entering >=80th shock percentile.
No additional shock events until shock percentile falls back below 80th.

## Regime transitions
Events fire only on primary ATR_24 state changes (no repeated events while state persists).
