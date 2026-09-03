"""Model drift and implementation integrity guards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from phase56.config import FROZEN, MODEL_HASH, PHASE55_FROZEN, PHASE55_IMPLEMENTATION


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_implementation_hash() -> str:
    """Hash frozen Phase55 implementation modules (read-only dependency)."""
    parts: list[str] = []
    impl_files = sorted(PHASE55_IMPLEMENTATION.glob("s54_*.py"))
    for p in impl_files:
        parts.append(f"{p.name}:{file_sha256(p)}")
    spec_files = sorted(PHASE55_FROZEN.glob("*.json"))
    for p in spec_files:
        parts.append(f"{p.name}:{file_sha256(p)}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def verify_model_hash() -> tuple[bool, str]:
    expected = (PHASE55_FROZEN / "model_hash.txt").read_text().strip()
    phase56_copy = (FROZEN / "phase55_model_hash.txt").read_text().strip()
    ok = expected == MODEL_HASH == phase56_copy
    return ok, expected


def write_implementation_hash() -> str:
    h = compute_implementation_hash()
    (FROZEN / "implementation_hash.txt").write_text(h + "\n")
    return h


def load_manifest() -> dict:
    return json.loads((FROZEN / "phase56_forward_manifest.json").read_text())


def drift_status() -> dict:
    model_ok, model_hash = verify_model_hash()
    impl_hash = compute_implementation_hash()
    stored_impl = ""
    impl_path = FROZEN / "implementation_hash.txt"
    if impl_path.exists():
        stored_impl = impl_path.read_text().strip()
    impl_drift = bool(stored_impl) and stored_impl != impl_hash
    return {
        "model_hash": model_hash,
        "model_drift": not model_ok,
        "implementation_hash": impl_hash,
        "implementation_drift": impl_drift,
        "pass": model_ok and not impl_drift,
    }
