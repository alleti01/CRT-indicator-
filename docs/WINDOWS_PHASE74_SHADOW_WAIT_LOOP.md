# Windows — Phase74 shadow wait loop (read this on the trading PC)

**As of `main` after `6b740b6`:** the NinjaTrader wait loop in `phase74/run_live.py` is **not** fixed. The last pull only updated the NT bridge (`CRTBarBridge.cs`, `bridge_server.py`, `ninjatrader_live.py`).

This note is so you do not think `--bars 480` means “run shadow for 8 hours.”

---

## What the wait loop does

After webhook start, `--provider ninjatrader` sits in `phase74/run_live.py`:

1. Poll health + bar count every 1 second.
2. When `DATA_HEALTHY` and bootstrap bars are in (`ninjatrader_bootstrap_bars`, default 15):
   - if `--mode shadow`: inject a **fake `SIGNAL_LONG`** via `make_test_signal`
   - if `--bars` is **not** `0`: **`break`** (leave the loop)
3. Process then prints status, disconnects, **exits**. Webhook dies with it.

| `--bars` | Deadline | When NT is healthy |
|----------|----------|--------------------|
| `0` | none (Ctrl+C to stop) | stay up |
| `480` (or any other number) | that many **minutes** max | fake long, then **quit immediately** |

`--bars 480` is “wait up to 8 hours for bootstrap, then quit.” It is not an 8-hour session.

---

## Windows start scripts

### `scripts/start-ninjatrader-shadow.ps1` (normal shadow)

Loads `phase74\.env`, kills Python on ports 8765/8787, then:

```powershell
python phase74\run_live.py --provider ninjatrader --mode shadow --webhook --bars 480
```

**What actually happens:** NT healthy → test LONG → process exits. Bot is not sitting for 480 minutes.

### `scripts/start-ninjatrader-validation.ps1` (validation)

```powershell
python phase74\run_live.py --provider ninjatrader --mode shadow --webhook --validate --pass-chase --pass-late --bars 0
```

`--bars 0` **does** stay up. Use this pattern for a real session.

---

## What to run today (workaround)

Do **not** use `--bars 480` if you want the webhook to stay alive.

From repo root, after `phase74\.env` is loaded:

```powershell
python phase74\run_live.py --provider ninjatrader --mode shadow --webhook --bars 0
```

Or run `.\scripts\start-ninjatrader-validation.ps1` if you also want `--validate` / chase / late.

Until `run_live.py` is patched:

- fake `SIGNAL_LONG` on first healthy still happens in **shadow** mode
- only `--bars 0` keeps the process up after that

---

## After a real code fix (not in this pull)

A proper fix would:

1. Stay in the wait loop for the full deadline (or forever if `--bars 0`).
2. Not inject `make_test_signal` unless an explicit flag is on (e.g. `--inject-test-signal`).
3. Change `start-ninjatrader-shadow.ps1` to `--bars 0`.

Until you see those three in `git log` / `run_live.py`, assume the loop is still the old smoke-test behavior.
