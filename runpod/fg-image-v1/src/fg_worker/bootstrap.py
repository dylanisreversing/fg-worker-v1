"""Model-integrity and runtime bootstrap checks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import (
    MODEL_DIR,
    MODEL_MANIFEST_SHA256,
    MODEL_REPO_ID,
    MODEL_REVISION,
    SETTINGS_PROFILE,
    WORKER_ID,
    WORKER_VERSION,
    WORKFLOW_ID,
    WORKFLOW_SHA256,
    WORKFLOW_VERSION,
)
from .provenance import (
    DEFAULT_SOURCE_MANIFEST,
    SourceVerificationError,
    WORKER_ROOT,
    verify_source_manifest,
)


DEFAULT_MANIFEST = Path("/opt/fg-worker/model-manifest.json")
DEFAULT_WORKFLOW_MANIFEST = Path("/opt/fg-worker/workflow-manifest.json")
STAMP_NAME = ".fg-image-v1-verified.json"


class VerificationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise VerificationError("Model manifest is unavailable.") from None
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise VerificationError("Model manifest is invalid.")
    return value


def _manifest_digest(path: Path) -> str:
    return _sha256(path)


def verify_model_manifest_identity(path: Path) -> None:
    manifest = load_manifest(path)
    worker = manifest.get("worker")
    model = manifest.get("model")
    if (
        _manifest_digest(path) != MODEL_MANIFEST_SHA256
        or not isinstance(worker, dict)
        or worker.get("id") != WORKER_ID
        or worker.get("version") != WORKER_VERSION
        or not isinstance(model, dict)
        or model.get("repo_id") != MODEL_REPO_ID
        or model.get("revision") != MODEL_REVISION
    ):
        raise VerificationError("Model manifest identity mismatch.")


def verify_workflow_manifest(path: Path) -> None:
    try:
        raw = path.read_bytes()
        manifest = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        raise VerificationError("Workflow manifest is unavailable.") from None
    if hashlib.sha256(raw).hexdigest() != WORKFLOW_SHA256:
        raise VerificationError("Workflow manifest checksum mismatch.")
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or manifest.get("workflow_id") != WORKFLOW_ID
        or manifest.get("workflow_version") != WORKFLOW_VERSION
        or manifest.get("settings_profile") != SETTINGS_PROFILE
        or manifest.get("worker_name") != WORKER_ID
    ):
        raise VerificationError("Workflow manifest is invalid.")


def verify_assets(
    *,
    manifest_path: Path,
    model_dir: Path,
    full: bool,
    write_stamp: bool = False,
) -> None:
    manifest = load_manifest(manifest_path)
    model = manifest.get("model")
    if not isinstance(model, dict) or not isinstance(model.get("files"), list):
        raise VerificationError("Model manifest is invalid.")

    root = model_dir.resolve()
    for record in model["files"]:
        if not isinstance(record, dict):
            raise VerificationError("Model manifest is invalid.")
        relative = record.get("path")
        size = record.get("size")
        expected_sha = record.get("sha256")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or not isinstance(expected_sha, str)
            or len(expected_sha) != 64
        ):
            raise VerificationError("Model manifest is invalid.")
        target = (root / relative).resolve()
        if root not in target.parents:
            raise VerificationError("Model manifest is invalid.")
        try:
            actual_size = target.stat().st_size
        except OSError:
            raise VerificationError("Model artifact is unavailable.") from None
        if actual_size != size:
            raise VerificationError("Model artifact size mismatch.")
        if full and _sha256(target) != expected_sha:
            raise VerificationError("Model artifact checksum mismatch.")

    stamp = root / STAMP_NAME
    stamp_value = {
        "manifest_sha256": _manifest_digest(manifest_path),
        "model_revision": model.get("revision"),
        "schema_version": 1,
    }
    if write_stamp:
        stamp.write_text(
            json.dumps(stamp_value, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    elif not full:
        try:
            current_stamp = json.loads(stamp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise VerificationError("Model verification stamp is unavailable.") from None
        if current_stamp != stamp_value:
            raise VerificationError("Model verification stamp mismatch.")


def verify_runtime() -> None:
    try:
        import torch
        from diffusers import ZImagePipeline

        if ZImagePipeline is None or not torch.cuda.is_available():
            raise VerificationError("GPU runtime is unavailable.")
    except VerificationError:
        raise
    except Exception:
        raise VerificationError("Required runtime dependency is unavailable.") from None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the pinned model snapshot.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--full", action="store_true", help="Hash every model artifact.")
    mode.add_argument("--quick", action="store_true", help="Verify sizes and the build stamp.")
    parser.add_argument("--runtime", action="store_true", help="Also verify CUDA and pipeline imports.")
    parser.add_argument("--write-stamp", action="store_true", help="Write the deterministic build stamp.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument(
        "--workflow-manifest",
        type=Path,
        default=DEFAULT_WORKFLOW_MANIFEST,
    )
    parser.add_argument("--model-dir", type=Path, default=Path(MODEL_DIR))
    arguments = parser.parse_args(argv)
    try:
        verify_source_manifest(arguments.source_manifest, WORKER_ROOT)
        verify_model_manifest_identity(arguments.manifest)
        verify_assets(
            manifest_path=arguments.manifest,
            model_dir=arguments.model_dir,
            full=arguments.full,
            write_stamp=arguments.write_stamp,
        )
        verify_workflow_manifest(arguments.workflow_manifest)
        if arguments.runtime:
            verify_runtime()
    except (VerificationError, SourceVerificationError) as error:
        parser.exit(1, f"bootstrap verification failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
