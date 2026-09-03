# Auction Event Definitions

Horizons: (1, 3, 6, 12, 24) bars from event close.

## Acceptance / rejection (one-bar rule)
- ACCEPTANCE_ABOVE_VAH: prior bar close > VAH and current bar close > VAH
- ACCEPTANCE_BELOW_VAL: prior bar close < VAL and current bar close < VAL
- REJECTION_ABOVE_VAH: prior bar closed above VAH; current bar closes inside value
- REJECTION_BELOW_VAL: prior bar closed below VAL; current bar closes inside value

## De-duplication
One event per session/type/level until price exits interaction by > 0.5 ATR from level.
