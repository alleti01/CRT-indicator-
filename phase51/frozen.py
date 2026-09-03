"""Frozen model snapshot, hash verification, and drift detection."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from phase51.config import (
    FROZEN_B1_RULE,
    FROZEN_B1_WINDOW_MIN,
    FROZEN_MODEL_DIR,
    M0_VERSION,
    MODEL_VERSION,
    PHASE44_VERSION,
    PHASE45_VERSION,
    PINE_PATH,
    ROOT,
)

PINE_HASH_MARKER = "P51_MODEL_HASH"


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


def extract_frozen_pine_logic(pine_path: Path | None = None) -> str:
    """Extract strategy logic from Pine (constants + Phase44 bundle + B1/M0)."""
    path = pine_path or PINE_PATH
    text = path.read_text(encoding="utf-8")
    start = text.find("// ═══ FROZEN CONSTANTS")
    end = text.find("// ═══ VISUALS")
    if start < 0 or end < 0 or end <= start:
        raise ValueError(f"Could not extract frozen logic from {path}")
    logic = text[start:end]
    # Strip Phase51 display-only inputs/groups from hash scope if present later.
    logic = re.sub(r"string GRP51 = .*?\n", "", logic)
    logic = re.sub(r"bool p51Show.*?group = GRP51\)\n", "", logic)
    logic = re.sub(r"int p51ForwardStartMs = input\.time\(.*?\n", "", logic)
    logic = re.sub(r'const string P51_MODEL_HASH = ".*?"\n', "", logic)
    return logic


def model_config_payload(forward_start_ct: str | None = None) -> dict[str, Any]:
    p50_pine = ROOT / "phase50" / "pine" / "phase50_nq_indicator.pine"
    key_files = [
        ROOT / "phase45" / "execution" / "confirm.py",
        ROOT / "phase45" / "execution" / "simulate.py",
        ROOT / "phase45" / "execution" / "config.py",
        ROOT / "phase45" / "frozen.py",
        ROOT / "phase48" / "simulate_mgmt.py",
        p50_pine,
        PINE_PATH,
    ]
    payload: dict[str, Any] = {
        "model_version": MODEL_VERSION,
        "phase44_version": PHASE44_VERSION,
        "phase45_version": PHASE45_VERSION,
        "m0_version": M0_VERSION,
        "b1_rule": FROZEN_B1_RULE,
        "b1_window_min": FROZEN_B1_WINDOW_MIN,
        "symbol": "NQ1!",
        "chart_timeframe": "1m",
        "context_timeframe": "15m",
        "timezone": "America/Chicago",
        "transaction_cost_assumption": "signals_only_no_auto_execution",
        "git_commit": _git_hash(),
        "file_hashes": {str(p.relative_to(ROOT)): _file_hash(p) for p in key_files},
        "pine_frozen_logic_sha256": hashlib.sha256(
            extract_frozen_pine_logic(p50_pine).encode()
        ).hexdigest(),
    }
    if forward_start_ct:
        payload["forward_start_ct"] = forward_start_ct
        payload["forward_start_note"] = (
            "Must match Pine input 'Forward start (CT)'. Do not move backward."
        )
    return payload


def compute_model_hash(payload: dict | None = None) -> str:
    data = payload or model_config_payload()
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def write_frozen_snapshot(
    output_dir: Path | None = None, forward_start_ct: str | None = None
) -> tuple[dict, str]:
    out = output_dir or FROZEN_MODEL_DIR
    out.mkdir(parents=True, exist_ok=True)
    payload = model_config_payload(forward_start_ct=forward_start_ct)
    model_hash = compute_model_hash(payload)
    manifest = {**payload, "model_hash": model_hash}
    (out / "model_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "model_hash.txt").write_text(model_hash + "\n")
    return manifest, model_hash


def embed_hash_in_pine(model_hash: str, pine_path: Path | None = None) -> None:
    path = pine_path or PINE_PATH
    text = path.read_text(encoding="utf-8")
    pattern = rf'(const string {PINE_HASH_MARKER} = ")[^"]*(")'
    if not re.search(pattern, text):
        raise ValueError(f"{PINE_HASH_MARKER} constant not found in {path}")
    path.write_text(re.sub(pattern, rf"\g<1>{model_hash}\2", text), encoding="utf-8")


def verify_model_drift(forward_start_ct: str | None = None) -> tuple[bool, str, dict]:
    manifest_path = FROZEN_MODEL_DIR / "model_manifest.json"
    if not manifest_path.exists():
        return False, "missing manifest", {}
    stored = json.loads(manifest_path.read_text())
    current = model_config_payload(forward_start_ct=forward_start_ct)
    # forward_start_ct is operational metadata — exclude from drift hash
    for k in ("forward_start_ct", "forward_start_note"):
        stored.pop(k, None)
        current.pop(k, None)
    stored_hash = stored.pop("model_hash", "")
    current_hash = compute_model_hash({**current, "model_hash": ""})
    # Recompute without model_hash key
    stored_core = {k: v for k, v in stored.items()}
    current_core = {k: v for k, v in current.items()}
    ok = stored_core == current_core and stored_hash == compute_model_hash(stored_core)
    return ok, current_hash, stored
