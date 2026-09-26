# MNQ sizing

Quantity is floor(dollar cap / (stop points × $2)). This does not change any replay result. If the result is under 1, the trade does not fit even at 1 MNQ.

On the median 5-bar stop, 26.1 points, $52 per MNQ:

| Cap | MNQ |
|---|---|
| $100 | 1 |
| $150 | 2 |
| $200 | 3 |
| $250 | 4 |

On the median 10-bar stop, 53.2 points, $106 per MNQ:

| Cap | MNQ |
|---|---|
| $100 | 0 |
| $150 | 1 |
| $200 | 1 |
| $250 | 2 |

Thursday 12:24 is 178.8 points, $358 per MNQ. It does not fit a $100, $150, $200, or $250 cap at 1 MNQ. Friday's 12:24 long is 129.7 points on the 10-bar stop, $259 per MNQ, so it fits only a cap above that, and only at 1 MNQ.

A 1 NQ position cannot carry the median 10-bar stop inside a $250 risk cap. That is sizing. It is not a reason to pull the stop back inside the 5-bar low.
