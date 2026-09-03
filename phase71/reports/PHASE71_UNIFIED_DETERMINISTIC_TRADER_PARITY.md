PHASE71 — UNIFIED DETERMINISTIC TRADER
======================================

SIGNAL HASH: 0da41f282174679f
TRADER HASH: b6adfc04e8885a3d

SIGNAL PARITY: PASS
M0 PARITY: PASS
T5 PARITY: PASS
CAUSALITY: PASS
PREFIX: PASS

--------------------------------
FROZEN RULES
--------------------------------
Entry: next bar open after signal
Stop: 1.0 ATR | Target: 2.5R | T5: 15m MFE<1R exit | Max hold: 60m
Collision: STOP_FIRST | Position limit: 1 | Opposite signal: IGNORE

--------------------------------
M0 BASELINE
--------------------------------
N: 36,174  AvgR: 0.0160  PF: 1.023
TotalR: 578.5  DD: 170.2

--------------------------------
T5 RESULT
--------------------------------
T5 exits: 775
Incremental AvgR: +0.0011
Incremental TotalR: +38.7
Validation incremental AvgR: +0.0040
Killed winners: 0.7%
Attribution: {'NO_CHANGE': 35415, 'SAVED_STOP': 468, 'KILLED_WINNER': 243, 'CUT_SMALL_WIN': 34, 'CUT_SMALL_LOSS': 14}

--------------------------------
ONE-POSITION RESULT
--------------------------------
Trades executed: 35,902
Signals skipped: 272
AvgR: 0.0169  TotalR: 605.8

--------------------------------
PYTHON TESTS
--------------------------------
Passed: True

--------------------------------
FINAL VERDICT
--------------------------------
UNIFIED STATE MACHINE: PASS
PYTHON: PASS
PINE: PENDING MANUAL PARITY
T5 IMPLEMENTED: YES
ENTRY LOGIC CHANGED: NO
REJECTED PHASE70 RULES ADDED: NO
READY FOR PHASE72: YES
READY FOR PAPER FORWARD: NO
READY FOR LIVE: NO

NEXT STEP: Phase72 adversarial audit + manual TV review of phase71_unified_trader.pine