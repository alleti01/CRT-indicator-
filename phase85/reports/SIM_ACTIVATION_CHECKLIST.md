# SIM activation checklist

FUNDED stays blocked until this file is completed on a **real** NinjaTrader SIM account (1 MNQ) using this same code path.

Do not rewrite the adapter after SIM. If a bug is found, halt and review.

- [ ] Phase72A hash verified
- [ ] Phase73 freeze verified
- [ ] CRTBarBridge still read-only
- [ ] CRTExecutionBridge compiled in NT8
- [ ] execution auth PASS
- [ ] SIM account exact match PASS
- [ ] MNQ contract verified
- [ ] qty>1 rejected by C#
- [ ] command dedup PASS
- [ ] webhook dedup PASS
- [ ] SIM LONG entry + actual fill
- [ ] SIM SHORT entry + actual fill
- [ ] M0 from actual fill
- [ ] stop working
- [ ] target working
- [ ] OCO: target fill cancels stop
- [ ] OCO: stop fill cancels target
- [ ] flatten → NT FLAT
- [ ] partial-fill handling observed or qty=1 remaining=0
- [ ] protection-failure flatten+halt (forced SIM test)
- [ ] duplicate webhook ×4 → one order
- [ ] duplicate command ×4 → one order
- [ ] restart reconciliation
- [ ] disconnect: new entries blocked, protection left working
- [ ] stale signal blocked
- [ ] data health gate
- [ ] kill switch
- [ ] default fail-closed still cannot route
- [ ] real Phase72A alert → NT SIM (do not fabricate a signal)
- [ ] execution ledger complete
- [ ] latency telemetry recorded
- [ ] production strategy files unchanged

Only after every box is checked, write:

```json
{"pass": true, "verdict": "PHASE85_SIM_EXECUTION_PASS", "date_utc": "YYYY-MM-DD"}
```

to the configured `sim_gate_path` (default `phase85/logs/sim_activation_gate.json`).  
That file is gitignored. Do not commit a passing gate as a default.
