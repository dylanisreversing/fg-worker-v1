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
COPIED_TREE_ROOTS = ("licenses", "src")


def _record(root: Path, relative: str) -> dict[str, object]:
    target = root / relative
    raw = target.read_bytes()
    return {
        "path": relative,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def assert_exact_copied_tree(root: Path = WORKER_ROOT) -> None:
    expected = {
        relative
        for relative in SOURCE_FILES
        if Path(relative).parts[0] in COPIED_TREE_ROOTS
    }
    actual: set[str] = set()
    for directory_name in COPIED_TREE_ROOTS:
        directory = root / directory_name
        for target in directory.rglob("*"):
            if target.is_symlink():
                raise ValueError("copied runtime trees may not contain symlinks")
            if target.is_file():
                actual.add(target.relative_to(root).as_posix())
    if actual != expected:
        raise ValueError("copied runtime tree does not match the source manifest allowlist")


def rendered_manifest(root: Path = WORKER_ROOT) -> bytes:
    assert_exact_copied_tree(root)
    manifest = {
        "schema_version": 1,
        "worker_name": "fg-worker-v1",
        "base_image": BASE_IMAGE,
        "files": [_record(root, relative) for relative in sorted(SOURCE_FILES)],
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
