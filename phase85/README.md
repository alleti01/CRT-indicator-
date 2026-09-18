# Phase85 — NinjaTrader execution layer

One execution path for **SHADOW / SIM / FUNDED**.

```
Phase72A webhook → Python Phase73/74 → safety gates
        → NinjaTraderExecutionAdapter
        → localhost JSON-lines (port 8766)
        → CRTExecutionBridge.cs
        → explicitly configured NinjaTrader account
```

Market data stays on `CRTBarBridge.cs` (port 8765, read-only).

## Defaults (fail-closed)

| Variable | Default |
|---|---|
| `EXECUTION_MODE` | `SHADOW` |
| `SHADOW_MODE` | `true` |
| `TRADING_ENABLED` | `false` |
| `EXTERNAL_ORDER_ROUTING` | `false` |
| `NT_EXECUTION_BRIDGE_ENABLED` | `false` |

Missing or invalid config **cannot** route an external order.

FUNDED additionally requires the SIM activation gate file, exact funded-account allowlist, and multi-arm switches. The repository does **not** ship a passing SIM gate.

## Do not modify

- `TV_REVIEW/phase72a_autonomous_trader.pine`
- Frozen Phase73 engine / M0
- Phase74 decision behavior
- `CRTBarBridge.cs`

## Tests

```bash
python3 -m unittest discover -s phase85/tests -v
```

## Preflight

```bash
python3 -m phase85.diagnostics.run_phase85
python3 -m phase85.diagnostics.run_phase85 --fake
```

## Windows

See `phase85/reports/WINDOWS_SETUP.md`.

## Current verdict

`PHASE85_UNIT_TEST_PASS`

NinjaTrader SIM checkout and funded routing are **not** claimed. They require the Windows SIM gate in `reports/SIM_ACTIVATION_CHECKLIST.md`.
