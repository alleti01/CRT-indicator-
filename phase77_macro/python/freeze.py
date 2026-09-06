"""Verify Phase77 implementation freeze before macro experiment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import CHECKPOINTS, FREEZE_FILES, ROOT


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_freeze(manifest_path: Path | None = None) -> dict:
    manifest_path = manifest_path or (CHECKPOINTS / "00_freeze_manifest.json")
    current = {}
    for rel in FREEZE_FILES:
        p = ROOT / rel
        if not p.exists():
            return {"status": "PHASE77_MACRO_FREEZE_MISMATCH", "missing": rel}
        current[rel] = file_sha256(p)

    if manifest_path.exists():
        stored = json.loads(manifest_path.read_text())
        stored_hashes = stored.get("hashes", {})
        mismatch = {k: {"stored": stored_hashes.get(k), "current": v} for k, v in current.items() if stored_hashes.get(k) != v}
        if mismatch:
            return {"status": "PHASE77_MACRO_FREEZE_MISMATCH", "mismatch": mismatch, "hashes": current}
        return {"status": "PASS", "hashes": current, "verified_against": str(manifest_path)}

    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    manifest = {"status": "PASS", "hashes": current, "note": "Initial freeze recorded at first macro run"}
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest
