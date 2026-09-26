# Final verdict

ADAPTIVE_MULTIPLE_FAILURE_MODES_REMAIN

Giving the same CDX fills a structural stop does not, by itself, rescue the premature stop-outs without creating larger losses. Adding the 3-bar and 6-bar failure rules cuts some of those large losses and also cuts trades that later ran. The ratchet helps only when the favorable move happens before those checkpoints.

Full adaptive 5 is the least-bad realized book on this sample, −3.15 points versus the live −53.50. It is not a solution to both problems. It misses Wednesday's +43 point bounce, it does not save Thursday 7:03 or Thursday 8:21, and it turns Thursday 12:24 from +8 points into −9.25 points. Full adaptive 10 turns Thursday 8:03 from +19 points into −47 points, because 47 points of risk never reaches the first ratchet.

Do not freeze this V1 package for paper trading as a unit. The piece that matched the hypothesis on the one clean premature stop, Thursday 1:51, was the ratchet and then the existing 10-point runner after +2R. The piece that fought the hypothesis was the early-failure cutoff, which acts before a slow move can prove itself when R is large.

Causality checks on 500 truncated MFE and stop calculations: 0 mismatches.

Every management system used the same direction and the same fill. No entry was delayed or dropped.

Production was not modified.
