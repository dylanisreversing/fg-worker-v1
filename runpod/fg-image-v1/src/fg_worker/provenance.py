"""Content-derived worker identity and source-integrity verification."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from . import BASE_IMAGE, WORKER_ID


WORKER_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_MANIFEST = WORKER_ROOT / "source-manifest.json"
COPIED_TREE_ROOTS = frozenset({"licenses", "src"})


class SourceVerificationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source_manifest(manifest_path: Path, root: Path) -> str:
    try:
        raw = manifest_path.read_bytes()
        manifest: Any = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        raise SourceVerificationError("Source manifest is unavailable.") from None

    if (
        not isinstance(manifest, Mapping)
        or manifest.get("schema_version") != 1
        or manifest.get("worker_name") != WORKER_ID
        or manifest.get("base_image") != BASE_IMAGE
        or not isinstance(manifest.get("files"), list)
        or not manifest["files"]
    ):
        raise SourceVerificationError("Source manifest is invalid.")

    resolved_root = root.resolve()
    seen: set[str] = set()
    for record in manifest["files"]:
        if not isinstance(record, Mapping):
            raise SourceVerificationError("Source manifest is invalid.")
        relative = record.get("path")
        size = record.get("size")
        expected_sha = record.get("sha256")
        if (
            not isinstance(relative, str)
            or not relative
            or relative == manifest_path.name
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or relative in seen
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or not isinstance(expected_sha, str)
            or len(expected_sha) != 64
        ):
            raise SourceVerificationError("Source manifest is invalid.")
        seen.add(relative)
        target = (resolved_root / relative).resolve()
        if resolved_root not in target.parents:
            raise SourceVerificationError("Source manifest is invalid.")
        try:
            if target.stat().st_size != size or _sha256(target) != expected_sha:
                raise SourceVerificationError("Worker source integrity mismatch.")
        except OSError:
            raise SourceVerificationError("Worker source is unavailable.") from None

    expected_copied_files = {
        relative
        for relative in seen
        if Path(relative).parts[0] in COPIED_TREE_ROOTS
    }
    actual_copied_files: set[str] = set()
    for directory_name in COPIED_TREE_ROOTS:
        directory = resolved_root / directory_name
        for target in directory.rglob("*"):
            if target.is_symlink():
                raise SourceVerificationError("Worker source is invalid.")
            if target.is_file():
                actual_copied_files.add(target.relative_to(resolved_root).as_posix())
    if actual_copied_files != expected_copied_files:
        raise SourceVerificationError("Worker source coverage mismatch.")

    source_digest = hashlib.sha256(raw).hexdigest()
    return f"{WORKER_ID}@sha256:{source_digest}"


@lru_cache(maxsize=1)
def worker_build_id() -> str:
    return verify_source_manifest(DEFAULT_SOURCE_MANIFEST, WORKER_ROOT)
