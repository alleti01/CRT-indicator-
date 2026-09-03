"""Frozen model snapshot and drift detection."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .config import (
    FROZEN_B1_RULE,
    FROZEN_B1_WINDOW_MIN,
    FROZEN_MODEL_DIR,
    M0_VERSION,
    MODEL_VERSION,
    PHASE44_VERSION,
    PHASE45_VERSION,
    ROOT,
)


def _git_hash() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL, text=True
        )
        return out.strip()
    except Exception:
        return "unknown"


def _file_hash(path: Path) -> str:
    if not path.exists():
        return "missing"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def model_config_payload() -> dict[str, Any]:
    key_files = [
        ROOT / "phase45" / "execution" / "confirm.py",
        ROOT / "phase45" / "execution" / "simulate.py",
        ROOT / "phase45" / "execution" / "config.py",
        ROOT / "phase45" / "frozen.py",
        ROOT / "phase48" / "simulate_mgmt.py",
        ROOT / "phase49" / "config.py",
    ]
    return {
        "model_version": MODEL_VERSION,
        "phase44_version": PHASE44_VERSION,
        "phase45_version": PHASE45_VERSION,
        "m0_version": M0_VERSION,
        "b1_rule": FROZEN_B1_RULE,
        "b1_window_min": FROZEN_B1_WINDOW_MIN,
        "git_commit": _git_hash(),
        "file_hashes": {str(p.relative_to(ROOT)): _file_hash(p) for p in key_files},
    }


def compute_model_hash(payload: dict | None = None) -> str:
    data = payload or model_config_payload()
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def write_frozen_snapshot(output_dir: Path | None = None) -> tuple[dict, str]:
    out = output_dir or FROZEN_MODEL_DIR
    out.mkdir(parents=True, exist_ok=True)
    payload = model_config_payload()
    model_hash = compute_model_hash(payload)
    manifest = {**payload, "model_hash": model_hash}
    (out / "frozen_model_manifest.json").write_text(json.dumps(manifest, indent=2))
    (out / "config_snapshot.json").write_text(json.dumps(payload, indent=2))
    return manifest, model_hash


def load_frozen_manifest() -> dict:
    path = FROZEN_MODEL_DIR / "frozen_model_manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def verify_model_hash(expected: str | None = None) -> tuple[bool, str, str]:
    manifest = load_frozen_manifest()
    current = compute_model_hash()
    ref = expected or manifest.get("model_hash", "")
    if not ref:
        return True, current, ref  # first run — no prior snapshot
    return current == ref, current, ref
