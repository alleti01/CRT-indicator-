# Phase85 verification report — 2026-09-18

Current verdict: **PHASE85_NINJATRADER_API_BLOCKED**.

These are results for the implementation already present at the start of this task. No execution source or strategy source was changed. Passing fake tests does not establish a working NinjaTrader execution path.

## Results

- Phase73: **26 passed**, zero failures.
- Phase74: **74 passed, 3 failed**, 77 total after allowing synthetic loopback tests.
- Existing Phase85: **69 passed**, zero failures.
- Combined: **169 passed, 3 failed**, 172 tests total.

Commands, run in `/Users/anishalleti/CRT indicator` using the installed Python 3.9:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s phase73/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s phase74/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s phase85/tests -v
```

The initial restricted Phase74 run had nine PermissionError failures on loopback bind. The approved rerun passed those nine cases. The final result has no socket-permission errors. ResourceWarnings about test cleanup were also emitted.

## Pre-existing Phase74 failures

- `test_one_globex_loss_does_not_halt_rth`: expected losers = 0; actual = 1, line 238.
- `test_overnight_wins_do_not_halt_rth`: expected no RTH halt; actual halt, line 217.
- `test_rth_wins_do_not_halt_after_hours`: expected no after-hours halt; actual halt, line 228.

All are in `phase74/tests/test_quality_gates.py`. `phase74/quality/day_halt.py` resets on calendar-date changes, whereas these cases expect intraday session resets. Neither the tests nor the strategy behavior were changed.

## Limits of the 69 Phase85 tests

They exercise the fake bridge and static text checks; they do not compile or execute CRTExecutionBridge. Lifecycle tests manually call protection, leaving the missing automatic FILLED-to-protection path undetected. Static presence of order API names does not validate C# signatures, asynchronous acknowledgements, ownership filtering, or durable recovery.

The inspected C# path does not match the documented CreateOrder signature and relies on an unverified Order.CustomText member. See API_VERIFICATION_BLOCKERS.md for evidence and further integration defects.

## Not run

Target Windows/NinjaTrader compile; actual SIM LONG/SHORT; real stop/target/OCO/flatten; real Phase72A-to-NinjaTrader lifecycle; empirical disconnect protection; funded preflight; funded orders. No real latency samples were collected. No SIM gate was created.

## Freeze verification

Phase72A hash matched the required value. Existing Phase73 freeze verification passed all 16 critical modules. CRTBarBridge hash matched its recorded reference, and read-only checks passed. These checks are repeated after the reporting-only changes; the machine-readable evidence is in FREEZE_VERIFICATION.json.
