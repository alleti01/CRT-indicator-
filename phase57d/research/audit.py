"""Audit findings tracker for Phase57D."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from phase57d.config import RESULTS
from phase57d.research.schema import AUDIT_FINDING_COLUMNS


class AuditLog:
    def __init__(self):
        self._findings: list[dict] = []
        self._counter = 0

    def add(
        self,
        severity: str,
        category: str,
        description: str,
        affected_events: int = 0,
        causality_impact: str = "",
        performance_impact: str = "",
        requires_fix: bool = False,
        status: str = "CONFIRMED",
    ) -> None:
        self._counter += 1
        self._findings.append({
            "finding_id": f"F57D-{self._counter:04d}",
            "severity": severity,
            "category": category,
            "description": description,
            "affected_events": affected_events,
            "causality_impact": causality_impact,
            "performance_impact": performance_impact,
            "requires_fix": requires_fix,
            "status": status,
        })

    def to_dataframe(self) -> pd.DataFrame:
        if not self._findings:
            return pd.DataFrame(columns=AUDIT_FINDING_COLUMNS)
        return pd.DataFrame(self._findings)

    def save(self, path: Path | None = None) -> Path:
        path = path or (RESULTS / "audit_findings.csv")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.to_dataframe().to_csv(path, index=False)
        return path
