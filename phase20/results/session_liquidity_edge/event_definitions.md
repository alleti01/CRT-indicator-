# Session Liquidity Event Definitions

## Timezone
All timestamps use `America/Chicago` (CME/CBOT equity index convention).

## Levels (causal)
- **PDH/PDL:** prior completed CME session high/low
- **ONH/ONL:** overnight window high/low from session start through 09:30, then locked
- **ORH/ORL:** RTH opening range 09:30–10:00 high/low, then locked
- **PRIOR_RTH_CLOSE:** prior session last RTH close (09:30–16:00)
- **SESSION_OPEN:** current session first RTH bar open (known after 09:30 bar)

## Interaction events
- **APPROACH:** distance to level ≤ 0.25 ATR after being farther on prior bar
- **TOUCH:** first bar where range spans the level
- **SWEEP:** pierce through level and close back on originating side
- **BREAK:** close crosses level vs prior close
- **BREAK_HOLD:** bar after break remains on breakout side
- **BREAK_FAILURE:** bar after break closes back through level

## De-duplication
After an event fires for `(session_date, level, event_type)`, suppress repeats until price moves **>0.5 ATR** away from the level or a new session resets the level.

## Forward returns
Measured from event bar close over horizons 1/3/6/12/24 five-minute bars.

## Time buckets
- **OVERNIGHT:** minutes 1080–240 (Chicago local)
- **PREMARKET:** minutes 240–570 (Chicago local)
- **RTH_OPEN:** minutes 570–630 (Chicago local)
- **RTH_MID_MORNING:** minutes 630–720 (Chicago local)
- **MIDDAY:** minutes 720–840 (Chicago local)
- **RTH_AFTERNOON:** minutes 840–960 (Chicago local)
