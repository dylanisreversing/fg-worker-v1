"""Build-time download of one immutable, allowlisted model snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

class ManifestError(RuntimeError):
    """The checked-in build download plan is internally inconsistent."""


def download_layer_paths(manifest: Mapping[str, Any], layer_id: str) -> list[str]:
    model = manifest.get("model")
    build_download = manifest.get("build_download")
    if (
        not isinstance(model, Mapping)
        or not isinstance(model.get("files"), list)
        or not isinstance(build_download, Mapping)
        or not isinstance(build_download.get("layers"), list)
        or isinstance(build_download.get("registry_uncompressed_layer_limit_bytes"), bool)
        or not isinstance(build_download.get("registry_uncompressed_layer_limit_bytes"), int)
        or isinstance(build_download.get("reserved_non_model_bytes_per_layer"), bool)
        or not isinstance(build_download.get("reserved_non_model_bytes_per_layer"), int)
        or isinstance(build_download.get("max_model_bytes_per_layer"), bool)
        or not isinstance(build_download.get("max_model_bytes_per_layer"), int)
    ):
        raise ManifestError("Model download manifest is invalid.")

    records: dict[str, int] = {}
    for record in model["files"]:
        if (
            not isinstance(record, Mapping)
            or not isinstance(record.get("path"), str)
            or isinstance(record.get("size"), bool)
            or not isinstance(record.get("size"), int)
            or record["path"] in records
        ):
            raise ManifestError("Model download manifest is invalid.")
        records[record["path"]] = record["size"]

    selected: list[str] | None = None
    assigned: list[str] = []
    layer_ids: set[str] = set()
    byte_limit = build_download["max_model_bytes_per_layer"]
    if (
        byte_limit <= 0
        or build_download["reserved_non_model_bytes_per_layer"] < 0
        or byte_limit + build_download["reserved_non_model_bytes_per_layer"]
        > build_download["registry_uncompressed_layer_limit_bytes"]
    ):
        raise ManifestError("Model download manifest is invalid.")
    for layer in build_download["layers"]:
        if (
            not isinstance(layer, Mapping)
            or not isinstance(layer.get("id"), str)
            or not layer["id"]
            or layer["id"] in layer_ids
            or not isinstance(layer.get("files"), list)
            or not layer["files"]
            or not all(isinstance(path, str) and path in records for path in layer["files"])
            or len(set(layer["files"])) != len(layer["files"])
            or sum(records[path] for path in layer["files"]) > byte_limit
        ):
            raise ManifestError("Model download manifest is invalid.")
        layer_ids.add(layer["id"])
        assigned.extend(layer["files"])
        if layer["id"] == layer_id:
            selected = list(layer["files"])

    if len(assigned) != len(set(assigned)) or set(assigned) != set(records):
        raise ManifestError("Model download manifest is invalid.")
    if selected is None:
        raise ManifestError("Requested model download layer is unavailable.")
    return selected


def main() -> int:
    from huggingface_hub import snapshot_download

    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--layer", required=True)
    arguments = parser.parse_args()

    manifest = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    model = manifest["model"]
    allow_patterns = download_layer_paths(manifest, arguments.layer)
    arguments.target.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=model["repo_id"],
        revision=model["revision"],
        local_dir=arguments.target,
        allow_patterns=allow_patterns,
        local_dir_use_symlinks=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
