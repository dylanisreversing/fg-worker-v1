from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


WORKER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_DIR / "src"))

from fg_worker.bootstrap import VerificationError, verify_assets  # noqa: E402
from fg_worker.provenance import (  # noqa: E402
    SourceVerificationError,
    verify_source_manifest,
    worker_build_id,
)


class BootstrapTests(unittest.TestCase):
    def test_source_manifest_derives_build_id_and_detects_runtime_drift(self) -> None:
        source_manifest = WORKER_DIR / "source-manifest.json"
        expected = "fg-worker-v1@sha256:" + hashlib.sha256(source_manifest.read_bytes()).hexdigest()
        self.assertEqual(verify_source_manifest(source_manifest, WORKER_DIR), expected)
        self.assertEqual(worker_build_id(), expected)

        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copied_manifest = root / "source-manifest.json"
            copied_manifest.write_bytes(source_manifest.read_bytes())
            for record in manifest["files"]:
                source = WORKER_DIR / record["path"]
                target = root / record["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            first_source = root / manifest["files"][0]["path"]
            first_source.write_bytes(first_source.read_bytes() + b"\n")
            with self.assertRaises(SourceVerificationError):
                verify_source_manifest(copied_manifest, root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copied_manifest = root / "source-manifest.json"
            copied_manifest.write_bytes(source_manifest.read_bytes())
            for record in manifest["files"]:
                source = WORKER_DIR / record["path"]
                target = root / record["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            extra_source = root / "src" / "sitecustomize.py"
            extra_source.write_text("raise RuntimeError('must never load')\n", encoding="utf-8")
            with self.assertRaises(SourceVerificationError):
                verify_source_manifest(copied_manifest, root)

    def _fixture(self, directory: Path) -> tuple[Path, Path]:
        model_dir = directory / "model"
        model_dir.mkdir()
        artifact = model_dir / "weights.bin"
        artifact.write_bytes(b"pinned bytes")
        manifest = {
            "schema_version": 1,
            "model": {
                "revision": "fixed-revision",
                "files": [
                    {
                        "path": "weights.bin",
                        "size": artifact.stat().st_size,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                ],
            },
        }
        manifest_path = directory / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path, model_dir

    def test_full_verification_writes_stamp_and_quick_verification_reuses_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, model = self._fixture(Path(temporary))
            verify_assets(
                manifest_path=manifest,
                model_dir=model,
                full=True,
                write_stamp=True,
            )
            verify_assets(manifest_path=manifest, model_dir=model, full=False)

    def test_detects_content_size_and_manifest_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, model = self._fixture(Path(temporary))
            verify_assets(
                manifest_path=manifest,
                model_dir=model,
                full=True,
                write_stamp=True,
            )
            (model / "weights.bin").write_bytes(b"pinned bytes changed")
            with self.assertRaises(VerificationError):
                verify_assets(manifest_path=manifest, model_dir=model, full=False)

        with tempfile.TemporaryDirectory() as temporary:
            manifest, model = self._fixture(Path(temporary))
            verify_assets(
                manifest_path=manifest,
                model_dir=model,
                full=True,
                write_stamp=True,
            )
            (model / "weights.bin").write_bytes(b"altered bytes")
            with self.assertRaises(VerificationError):
                verify_assets(manifest_path=manifest, model_dir=model, full=True)

        with tempfile.TemporaryDirectory() as temporary:
            manifest, model = self._fixture(Path(temporary))
            verify_assets(
                manifest_path=manifest,
                model_dir=model,
                full=True,
                write_stamp=True,
            )
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["model"]["revision"] = "tampered"
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(VerificationError):
                verify_assets(manifest_path=manifest, model_dir=model, full=False)

    def test_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, model = self._fixture(Path(temporary))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["model"]["files"][0]["path"] = "../weights.bin"
            manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(VerificationError):
                verify_assets(manifest_path=manifest, model_dir=model, full=True)


if __name__ == "__main__":
    unittest.main()
