# Phase84 Feature Definitions

All features computed at **signal bar T close** unless noted. No future data.

| NAME | FORMULA | KNOWN_AT | LOOKBACK | DIRECTION NORM | MISSING |
|------|---------|----------|----------|----------------|---------|
| range_position_W | (close_T - roll_low_W) / (roll_high_W - roll_low_W) | close T | W in {10,20,30} | none | 0.5 if span=0 |
| move_Lm_ATR | (close_T - close_T-L) * dir_sign / ATR_T | close T | L in {3,5,10} | LONG +1, SHORT -1 | nan if i<L |
| dist_from_Wm_extreme_ATR | distance to pre-signal rolling extreme / ATR_T | close T | W in {5,10,20} | LONG: below high; SHORT: above low | — |
| signal_bar_range_ATR | (high-low)/ATR_T | close T | 0 | none | — |
| signal_bar_body_ATR | abs(close-open)/ATR_T | close T | 0 | none | — |
| signal_body_frac | abs(close-open)/(high-low) | close T | 0 | none | 0 if range=0 |
| signal_close_loc | (close-low)/(high-low) | close T | 0 | none | 0.5 if range=0 |
| local_high_pre / local_low_pre | rolling max/min on bars [T-W, T-1] | close T | W=20 default | none | shrink window near start |
| break_wick | LONG: high_T > local_high_pre | close T | 20 | direction-specific | false |
| break_close_accept | LONG: close_T > local_high_pre | close T | 20 | direction-specific | false |
| failed_break | wick break without close accept | close T | 20 | direction-specific | false |
| directional_body_ATR | (close-open)*dir_sign/ATR_T | close T | 0 | LONG/SHORT | — |
| close_beyond_prior_high/low | close vs prior bar extreme | close T | 1 | direction-specific | false at i=0 |

**Entry timing:** Phase72A signal at bar T → baseline entry at bar T+1 open (E0).
