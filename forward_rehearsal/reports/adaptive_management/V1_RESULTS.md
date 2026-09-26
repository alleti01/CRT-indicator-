# V1 results

Scorecard is the 11 trades with both live prices. Open marks are not included. None of these 11 were still open when the replay exited. Dollars are $20 per point.

| System | Points | Dollars | Wins | Losses | Max DD | Largest loss |
|---|---|---|---|---|---|---|
| Live bot | −53.50 | −$1,070 | 2 | 9 | 53.5 | −14.25 |
| Struct 5 only | −134.86 | −$2,697 | 3 | 8 | 197.6 | −73.78 |
| Struct 10 only | −77.70 | −$1,554 | 3 | 8 | 139.5 | −64.00 |
| Struct 5 + early | −174.97 | −$3,499 | 0 | 11 | 175.0 | −51.42 |
| Struct 10 + early | −219.05 | −$4,381 | 0 | 11 | 219.1 | −53.17 |
| Struct 5 + ratchet | −126.84 | −$2,537 | 3 | 8 | 197.6 | −73.78 |
| Struct 10 + ratchet | −127.96 | −$2,559 | 2 | 8 | 200.3 | −64.00 |
| Full adaptive 5 | −3.15 | −$63 | 2 | 9 | 79.6 | −26.50 |
| Full adaptive 10 | −54.27 | −$1,085 | 1 | 10 | 139.7 | −47.04 |

Struct 5 only and struct 10 only use the live runner once MFE reaches +1R of the structural distance: 3R cap, 10-point trail, from `phase74/quality/trail.py`. Full adaptive hands that same runner the trade only after +2R.

Early failure with no ratchet is the worst book. It exits all 11 trades as losses. Adding the ratchet to the 5-bar stop is what pulls full adaptive 5 back near flat. That near-flat number still includes the damage to Thursday 12:24 and a smaller Thursday 8:03.

Realized totals do not use an 8-hour favorable mark.
