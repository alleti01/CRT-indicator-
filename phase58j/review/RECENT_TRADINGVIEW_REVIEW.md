# Recent TradingView Review Checklist

**VISUAL_DIAGNOSTIC_ONLY** — not for parameter selection or performance claims.

Exchange timezone: **America/Chicago**

## Group selection rules

- **A — M0 STOP → M1 TARGET**: exit_reason_m0=STOP AND exit_reason_m1=TARGET; most recent 10 by entry_ts desc
- **B — M1 worse than M0**: delta_r_m1_minus_m0 < 0; most recent 5 by entry_ts desc; prefers TARGET→STOP/TIME transitions
- **C — Normal M1 winners**: exit_reason_m1=TARGET excluding Group A trade_ids; most recent 5
- **D — M1 losers**: exit_reason_m1=STOP; most recent 5

--------------------------------------------------
REVIEW #01
Group: A — M0 STOP → M1 TARGET
Trade ID: E-061818
TradingView time: 2026-06-19 09:53:00 America/Chicago
Direction: LONG
Entry: 30686.25
M0 stop: 30681.415178571428
M1 stop: 30679.803571428572
M0 target: 30698.337053571428
M1 target: 30702.366071428572
M0 result: STOP (-1.15R)
M1 result: TARGET (2.50R)
ΔR: 3.65R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #02
Group: A — M0 STOP → M1 TARGET
Trade ID: E-061845
TradingView time: 2026-06-22 17:37:00 America/Chicago
Direction: SHORT
Entry: 30588.75
M0 stop: 30597.28125
M1 stop: 30600.125
M0 target: 30567.421875
M1 target: 30560.3125
M0 result: STOP (-1.08R)
M1 result: TARGET (2.50R)
ΔR: 3.58R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #03
Group: A — M0 STOP → M1 TARGET
Trade ID: E-061850
TradingView time: 2026-06-22 20:10:00 America/Chicago
Direction: SHORT
Entry: 30602.25
M0 stop: 30613.633928571428
M1 stop: 30617.428571428572
M0 target: 30573.790178571428
M1 target: 30564.303571428572
M0 result: STOP (-1.06R)
M1 result: TARGET (2.50R)
ΔR: 3.56R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #04
Group: A — M0 STOP → M1 TARGET
Trade ID: E-061873
TradingView time: 2026-06-23 19:55:00 America/Chicago
Direction: SHORT
Entry: 29839.25
M0 stop: 29851.397321428572
M1 stop: 29855.446428571428
M0 target: 29808.881696428572
M1 target: 29798.758928571428
M0 result: STOP (-1.06R)
M1 result: TARGET (2.50R)
ΔR: 3.56R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #05
Group: A — M0 STOP → M1 TARGET
Trade ID: E-061888
TradingView time: 2026-06-24 05:14:00 America/Chicago
Direction: LONG
Entry: 29805.0
M0 stop: 29796.602678571428
M1 stop: 29793.803571428572
M0 target: 29825.993303571428
M1 target: 29832.991071428572
M0 result: STOP (-1.09R)
M1 result: TARGET (2.50R)
ΔR: 3.59R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #06
Group: A — M0 STOP → M1 TARGET
Trade ID: E-061893
TradingView time: 2026-06-24 09:31:00 America/Chicago
Direction: LONG
Entry: 29752.75
M0 stop: 29719.75
M1 stop: 29708.75
M0 target: 29835.25
M1 target: 29862.75
M0 result: STOP (-1.02R)
M1 result: TARGET (2.50R)
ΔR: 3.52R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #07
Group: B — M1 worse than M0
Trade ID: E-061903
TradingView time: 2026-06-24 21:13:00 America/Chicago
Direction: SHORT
Entry: 29953.5
M0 stop: 29963.772321428572
M1 stop: 29967.196428571428
M0 target: 29927.819196428572
M1 target: 29919.258928571428
M0 result: TARGET (2.43R)
M1 result: STOP (-1.00R)
ΔR: -3.43R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #08
Group: B — M1 worse than M0
Trade ID: E-061914
TradingView time: 2026-06-25 04:33:00 America/Chicago
Direction: LONG
Entry: 30138.0
M0 stop: 30131.23660714286
M1 stop: 30128.98214285714
M0 target: 30154.90848214286
M1 target: 30160.54464285714
M0 result: TARGET (2.39R)
M1 result: STOP (-1.00R)
ΔR: -3.39R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #09
Group: A — M0 STOP → M1 TARGET
Trade ID: E-061924
TradingView time: 2026-06-25 11:33:00 America/Chicago
Direction: SHORT
Entry: 29707.5
M0 stop: 29731.29910714286
M1 stop: 29739.23214285714
M0 target: 29648.00223214286
M1 target: 29628.16964285714
M0 result: STOP (-1.03R)
M1 result: TARGET (2.50R)
ΔR: 3.53R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #10
Group: B — M1 worse than M0
Trade ID: E-061927
TradingView time: 2026-06-25 13:24:00 America/Chicago
Direction: LONG
Entry: 29823.25
M0 stop: 29800.17410714286
M1 stop: 29792.48214285714
M0 target: 29880.93973214286
M1 target: 29900.16964285714
M0 result: TARGET (2.47R)
M1 result: STOP (-1.00R)
ΔR: -3.47R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #11
Group: C — Normal M1 winner
Trade ID: E-061935
TradingView time: 2026-06-26 00:40:00 America/Chicago
Direction: SHORT
Entry: 29362.5
M0 stop: 29374.995535714286
M1 stop: 29379.160714285714
M0 target: 29331.261160714286
M1 target: 29320.848214285714
M0 result: TARGET (2.44R)
M1 result: TARGET (2.50R)
ΔR: 0.06R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #12
Group: A — M0 STOP → M1 TARGET
Trade ID: E-061938
TradingView time: 2026-06-26 01:24:00 America/Chicago
Direction: LONG
Entry: 29366.75
M0 stop: 29354.254464285714
M1 stop: 29350.089285714286
M0 target: 29397.988839285714
M1 target: 29408.401785714286
M0 result: STOP (-1.06R)
M1 result: TARGET (2.50R)
ΔR: 3.56R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #13
Group: C — Normal M1 winner
Trade ID: E-061940
TradingView time: 2026-06-26 03:43:00 America/Chicago
Direction: SHORT
Entry: 29472.5
M0 stop: 29482.852678571428
M1 stop: 29486.303571428572
M0 target: 29446.618303571428
M1 target: 29437.991071428572
M0 result: TARGET (2.43R)
M1 result: TARGET (2.50R)
ΔR: 0.07R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #14
Group: A — M0 STOP → M1 TARGET
Trade ID: E-061941
TradingView time: 2026-06-26 04:58:00 America/Chicago
Direction: SHORT
Entry: 29370.75
M0 stop: 29380.339285714286
M1 stop: 29383.535714285714
M0 target: 29346.776785714286
M1 target: 29338.785714285714
M0 result: STOP (-1.08R)
M1 result: TARGET (2.50R)
ΔR: 3.58R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #15
Group: B — M1 worse than M0
Trade ID: E-061942
TradingView time: 2026-06-26 06:07:00 America/Chicago
Direction: LONG
Entry: 29393.75
M0 stop: 29382.727678571428
M1 stop: 29379.053571428572
M0 target: 29421.305803571428
M1 target: 29430.491071428572
M0 result: TARGET (2.43R)
M1 result: STOP (-1.00R)
ΔR: -3.43R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #16
Group: D — M1 loser
Trade ID: E-061945
TradingView time: 2026-06-26 09:38:00 America/Chicago
Direction: SHORT
Entry: 29509.0
M0 stop: 29539.17410714286
M1 stop: 29549.23214285714
M0 target: 29433.56473214286
M1 target: 29408.41964285714
M0 result: STOP (-1.02R)
M1 result: STOP (-1.00R)
ΔR: 0.02R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #17
Group: C — Normal M1 winner
Trade ID: E-061946
TradingView time: 2026-06-26 10:23:00 America/Chicago
Direction: LONG
Entry: 29514.0
M0 stop: 29486.866071428572
M1 stop: 29477.821428571428
M0 target: 29581.834821428572
M1 target: 29604.446428571428
M0 result: TARGET (2.47R)
M1 result: TARGET (2.50R)
ΔR: 0.03R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #18
Group: D — M1 loser
Trade ID: E-061947
TradingView time: 2026-06-26 10:58:00 America/Chicago
Direction: LONG
Entry: 29635.0
M0 stop: 29606.60714285714
M1 stop: 29597.14285714286
M0 target: 29705.98214285714
M1 target: 29729.64285714286
M0 result: STOP (-1.03R)
M1 result: STOP (-1.00R)
ΔR: 0.03R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #19
Group: C — Normal M1 winner
Trade ID: E-061948
TradingView time: 2026-06-26 11:08:00 America/Chicago
Direction: SHORT
Entry: 29579.25
M0 stop: 29602.23214285714
M1 stop: 29609.89285714286
M0 target: 29521.79464285714
M1 target: 29502.64285714286
M0 result: TARGET (2.47R)
M1 result: TARGET (2.50R)
ΔR: 0.03R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #20
Group: D — M1 loser
Trade ID: E-061949
TradingView time: 2026-06-26 11:35:00 America/Chicago
Direction: LONG
Entry: 29634.75
M0 stop: 29614.071428571428
M1 stop: 29607.178571428572
M0 target: 29686.446428571428
M1 target: 29703.678571428572
M0 result: STOP (-1.04R)
M1 result: STOP (-1.00R)
ΔR: 0.04R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #21
Group: A — M0 STOP → M1 TARGET
Trade ID: E-061950
TradingView time: 2026-06-26 12:39:00 America/Chicago
Direction: SHORT
Entry: 29587.25
M0 stop: 29606.415178571428
M1 stop: 29612.803571428572
M0 target: 29539.337053571428
M1 target: 29523.366071428572
M0 result: STOP (-1.04R)
M1 result: TARGET (2.50R)
ΔR: 3.54R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #22
Group: D — M1 loser
Trade ID: E-061951
TradingView time: 2026-06-26 14:15:00 America/Chicago
Direction: LONG
Entry: 29501.5
M0 stop: 29483.01785714286
M1 stop: 29476.85714285714
M0 target: 29547.70535714286
M1 target: 29563.10714285714
M0 result: STOP (-1.04R)
M1 result: STOP (-1.00R)
ΔR: 0.04R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #23
Group: B — M1 worse than M0
Trade ID: E-061952
TradingView time: 2026-06-26 14:22:00 America/Chicago
Direction: SHORT
Entry: 29473.25
M0 stop: 29490.459821428572
M1 stop: 29496.196428571428
M0 target: 29430.225446428572
M1 target: 29415.883928571428
M0 result: TARGET (2.46R)
M1 result: STOP (-1.00R)
ΔR: -3.46R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #24
Group: D — M1 loser
Trade ID: E-061952
TradingView time: 2026-06-26 14:22:00 America/Chicago
Direction: SHORT
Entry: 29473.25
M0 stop: 29490.459821428572
M1 stop: 29496.196428571428
M0 target: 29430.225446428572
M1 target: 29415.883928571428
M0 result: TARGET (2.46R)
M1 result: STOP (-1.00R)
ΔR: -3.46R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:

--------------------------------------------------
REVIEW #25
Group: C — Normal M1 winner
Trade ID: E-061953
TradingView time: 2026-06-26 14:41:00 America/Chicago
Direction: LONG
Entry: 29476.5
M0 stop: 29458.98214285714
M1 stop: 29453.14285714286
M0 target: 29520.29464285714
M1 target: 29534.89285714286
M0 result: TARGET (2.46R)
M1 result: TARGET (2.50R)
ΔR: 0.04R

CHECK:
[ ] Entry is at a legitimate market location
[ ] M0 stop appears to be normal adverse movement
[ ] Thesis is still intact when M0 is stopped
[ ] M1 stop is beyond normal noise
[ ] M1 survives for a structurally defensible reason
[ ] M1 target is reached as part of the expected move
[ ] Trade appears suspicious / needs investigation

Notes:
