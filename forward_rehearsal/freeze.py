"""Forward rehearsal freeze manifest — record and verify production hashes."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path(__file__).resolve().parent / "FREEZE_MANIFEST.json"

PINE_PATH = ROOT / "TV_REVIEW" / "phase72a_autonomous_trader.pine"
PINE_HASH_REQUIRED = "d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f"

PHASE73_MODULES = [
    "phase73/trader/engine.py",
    "phase73/trader/fsm.py",
    "phase73/trader/entry_quality.py",
    "phase73/trader/management.py",
]

PHASE74_MODULES = [
    "phase74/runtime/live_stack.py",
    "phase74/market_data/live_provider.py",
    "phase74/webhook/secure_receiver.py",
    "phase74/execution/paper_broker.py",
    "phase74/config/loader.py",
    "phase74/config/default.json",
    "phase74/config/PHASE73_ENGINE_FREEZE.json",
]

FORWARD_MODULES = [
    "forward_rehearsal/runtime/forward_session.py",
    "forward_rehearsal/market_data/databento_live.py",
    "forward_rehearsal/freeze.py",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest() -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "manifest_id": "FORWARD_REHEARSAL_FREEZE",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rule": "No silent code changes during an active forward session",
        "pine": {
            "path": str(PINE_PATH.relative_to(ROOT)),
            "sha256": sha256_file(PINE_PATH) if PINE_PATH.exists() else "",
            "required_sha256": PINE_HASH_REQUIRED,
        },
        "phase73_engine": {},
        "phase74_adapters": {},
        "forward_rehearsal": {},
        "paper_execution_adapter": {},
    }
    for rel in PHASE73_MODULES:
        p = ROOT / rel
        if p.exists():
            manifest["phase73_engine"][rel] = sha256_file(p)
    for rel in PHASE74_MODULES:
        p = ROOT / rel
        if p.exists():
            manifest["phase74_adapters"][rel] = sha256_file(p)
    for rel in FORWARD_MODULES:
        p = ROOT / rel
        if p.exists():
            manifest["forward_rehearsal"][rel] = sha256_file(p)
    paper = ROOT / "phase74/execution/paper_broker.py"
    if paper.exists():
        manifest["paper_execution_adapter"]["phase74/execution/paper_broker.py"] = sha256_file(paper)
    return manifest


def write_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest = build_manifest()
    out = path or MANIFEST_PATH
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    p = path or MANIFEST_PATH
    return json.loads(p.read_text())


def verify_manifest(expected: dict[str, Any] | None = None) -> tuple[bool, list[str]]:
    expected = expected or load_manifest()
    errors: list[str] = []
    pine = expected.get("pine", {})
    pine_path = ROOT / pine.get("path", "")
    if not pine_path.exists():
        errors.append(f"missing pine: {pine_path}")
    else:
        actual = sha256_file(pine_path)
        req = pine.get("required_sha256", PINE_HASH_REQUIRED)
        if actual != req:
            errors.append(f"pine hash mismatch: got {actual[:16]} expected {req[:16]}")
        frozen = pine.get("sha256")
        if frozen and actual != frozen:
            errors.append(f"pine drift from manifest: got {actual[:16]} frozen {frozen[:16]}")

    for section in ("phase73_engine", "phase74_adapters", "forward_rehearsal", "paper_execution_adapter"):
        for rel, exp_hash in expected.get(section, {}).items():
            p = ROOT / rel
            if not p.exists():
                errors.append(f"missing {rel}")
                continue
            actual = sha256_file(p)
            if actual != exp_hash:
                errors.append(f"hash mismatch {rel}: expected {exp_hash[:12]} got {actual[:12]}")
    return len(errors) == 0, errors


def manifest_snapshot() -> dict[str, str]:
    """Compact hash map for session log envelope."""
    m = load_manifest()
    snap: dict[str, str] = {"pine": m.get("pine", {}).get("sha256", "")}
    for section in ("phase73_engine", "phase74_adapters", "forward_rehearsal", "paper_execution_adapter"):
        for rel, h in m.get(section, {}).items():
            snap[rel] = h
    return snap
