# Final report

Verdict: INSUFFICIENT_NATIVE_CDX_COVERAGE

The management rule needs each trade's real CDX Entry, SL, and TP1. Last week's 15 fills do not have those prices. The earlier replay left the native stop blank on every row, and no alert stored it.

The readable sets that do exist are Sep 27 and Sep 28. They are not assigned to Sep 22–26.

No stop was guessed from a 5-bar, 10-bar, or dollar rule. No P&L was produced for C0, H1, H2, or H3.

The 11 trades that have both an entry and an exit lost 53.50 points, or $1,070, under the bot's actual stops. That is the live baseline for context only. It is not a CDX-stop result.

Production was not modified.
