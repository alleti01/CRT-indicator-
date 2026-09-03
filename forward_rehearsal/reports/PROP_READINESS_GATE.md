# Prop Readiness Gate

**Not yet satisfied** — forward shadow with real TV alerts pending.

---

## Checklist

| Requirement | Status |
|-------------|--------|
| Forward shadow pass | PENDING — run Stage A |
| Local paper pass | BLOCKED — requires shadow gate |
| External paper pass | NOT STARTED — platform selection required |
| Real TV webhook verified | Infrastructure ready |
| Live market data verified | Databento adapter ready; key required |
| Correct contract mapping | Explicit in config; set `contract_month` for paper |
| Position reconciliation proven | Phase74 tests pass |
| Duplicate protection proven | Phase74 + forward tests pass |
| Restart recovery proven | Infra test + P74-19/20 |
| Reconnect recovery proven | `--disconnect-test` hook |
| Protective order behavior | CLIENT_SIDE_PROTECTION documented |
| Emergency flatten proven | P74-22 |
| Daily loss controls proven | P74-23 |
| Kill switch proven | P74-24 |
| Complete trade logs | Session logger implemented |
| Zero strategy modifications during rehearsal | ENFORCED |

---

## Verdict progression

```
INFRASTRUCTURE_READY
    ↓ (real TV + Databento shadow session)
FORWARD_SHADOW_PASS / FORWARD_SHADOW_FAIL
    ↓
LOCAL_PAPER_PASS / LOCAL_PAPER_FAIL
    ↓ (platform selected + adapter built)
EXTERNAL_PAPER_READY → EXTERNAL_PAPER_PASS
    ↓ (all gates + operational reliability)
PROP_DEPLOYMENT_READY
```

**PROP_DEPLOYMENT_READY requires operational reliability — not profitable trades.**
