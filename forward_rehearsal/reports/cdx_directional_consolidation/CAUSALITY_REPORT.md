# Causality

Result: PASS

Each V2 trade was replayed on every prefix of its managed 1-minute bars.
The stop active at each bar, the arm flag, and any exit index had to match the full run.
Mismatches: 0

Arming, pivot confirmation, and stop activation use only bars already closed.
A stop and a target on the same 1-minute bar resolve as the stop.
A +0.50R touch does not activate a new stop on that same bar.
