#!/usr/bin/env python3
"""Generate or check the deterministic worker source manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


WORKER_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = WORKER_ROOT / "source-manifest.json"
BASE_IMAGE = (
    "pytorch/pytorch:2.7.1-cuda12.8-cudnn9-runtime@sha256:"
    "c16f4c749e2d9e96878875cdf6cc45cddda1d1a36fddd371dd6f2360f1b6e2a2"
)
SOURCE_FILES = (
    "Dockerfile",
    "base-constraints.txt",
    "download_model.py",
    "entrypoint.sh",
    "handler.py",
    "licenses/Tongyi-MAI-Z-Image/LICENSE",
    "licenses/Tongyi-MAI-Z-Image/NOTICE",
    "model-manifest.json",
    "requirements.lock",
    "requirements.txt",
    "scripts/generate-source-manifest.py",
    "scripts/lock-requirements.sh",
    "src/fg_worker/__init__.py",
    "src/fg_worker/bootstrap.py",
    "src/fg_worker/contract.py",
    "src/fg_worker/provenance.py",
    "src/fg_worker/runtime.py",
    "src/fg_worker/service.py",
    "src/fg_worker/telemetry.py",
    "workflow-manifest.json",
)


def _record(relative: str) -> dict[str, object]:
    target = WORKER_ROOT / relative
    raw = target.read_bytes()
    return {
        "path": relative,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def rendered_manifest() -> bytes:
    manifest = {
        "schema_version": 1,
        "worker_name": "fg-worker-v1",
        "base_image": BASE_IMAGE,
        "files": [_record(relative) for relative in sorted(SOURCE_FILES)],
    }
    return (json.dumps(manifest, indent=2) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    expected = rendered_manifest()
    if arguments.write:
        OUTPUT.write_bytes(expected)
        return 0
    try:
        current = OUTPUT.read_bytes()
    except OSError:
        parser.exit(1, "source manifest is missing\n")
    if current != expected:
        parser.exit(1, "source manifest is stale\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
