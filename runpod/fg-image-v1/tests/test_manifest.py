from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


WORKER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_DIR))
sys.path.insert(0, str(WORKER_DIR / "src"))

from download_model import ManifestError, download_layer_paths  # noqa: E402
from fg_worker import MODEL_MANIFEST_SHA256, WORKER_VERSION, WORKFLOW_SHA256  # noqa: E402
from fg_worker.bootstrap import (  # noqa: E402
    VerificationError,
    verify_model_manifest_identity,
    verify_workflow_manifest,
)

SOURCE_GENERATOR_SPEC = importlib.util.spec_from_file_location(
    "fg_source_manifest_generator",
    WORKER_DIR / "scripts" / "generate-source-manifest.py",
)
assert SOURCE_GENERATOR_SPEC is not None and SOURCE_GENERATOR_SPEC.loader is not None
SOURCE_GENERATOR = importlib.util.module_from_spec(SOURCE_GENERATOR_SPEC)
SOURCE_GENERATOR_SPEC.loader.exec_module(SOURCE_GENERATOR)


class ManifestTests(unittest.TestCase):
    def test_source_generator_rejects_unlisted_copied_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(WORKER_DIR / "src", root / "src")
            shutil.copytree(WORKER_DIR / "licenses", root / "licenses")
            SOURCE_GENERATOR.assert_exact_copied_tree(root)
            (root / "src" / "sitecustomize.py").write_text(
                "raise RuntimeError('must never load')\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                SOURCE_GENERATOR.assert_exact_copied_tree(root)

    def test_model_and_runtime_are_immutably_pinned(self) -> None:
        manifest = json.loads((WORKER_DIR / "model-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["model"]["repo_id"], "Tongyi-MAI/Z-Image")
        self.assertEqual(
            manifest["model"]["revision"],
            "04cc4abb7c5069926f75c9bfde9ef43d49423021",
        )
        self.assertEqual(manifest["model"]["license"], "Apache-2.0")
        self.assertEqual(manifest["inference"]["allowed_dimensions"], [[1024, 1536], [1536, 1024]])
        self.assertEqual(
            hashlib.sha256((WORKER_DIR / "model-manifest.json").read_bytes()).hexdigest(),
            MODEL_MANIFEST_SHA256,
        )
        workflow_manifest = json.loads(
            (WORKER_DIR / "workflow-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(workflow_manifest["workflow_id"], "fg_image_v1")
        self.assertEqual(workflow_manifest["workflow_version"], "fg_image_v1.0.0")
        self.assertEqual(workflow_manifest["settings_profile"], "z_image_base_v1")
        self.assertEqual(workflow_manifest["worker_name"], "fg-worker-v1")
        self.assertNotIn("worker_build_id", workflow_manifest)
        self.assertEqual(
            hashlib.sha256((WORKER_DIR / "workflow-manifest.json").read_bytes()).hexdigest(),
            WORKFLOW_SHA256,
        )
        verify_model_manifest_identity(WORKER_DIR / "model-manifest.json")
        verify_workflow_manifest(WORKER_DIR / "workflow-manifest.json")
        files = manifest["model"]["files"]
        self.assertEqual(len(files), 18)
        self.assertTrue(all(record["size"] > 0 for record in files))
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) for record in files))

        dockerfile = (WORKER_DIR / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn(
            f'org.opencontainers.image.version="{WORKER_VERSION}"',
            dockerfile,
        )
        self.assertIn(
            f"fg-worker-v1:{WORKER_VERSION}",
            (WORKER_DIR / "scripts" / "build-local.sh").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "pytorch/pytorch:2.7.1-cuda12.8-cudnn9-runtime@sha256:"
            "c16f4c749e2d9e96878875cdf6cc45cddda1d1a36fddd371dd6f2360f1b6e2a2",
            dockerfile,
        )
        self.assertNotIn("ARG BASE", dockerfile)
        self.assertIn(
            "install -d --owner=10001 --group=10001 --mode=0700 /tmp/fg-worker-runtime",
            dockerfile,
        )
        self.assertIn("WORKDIR /tmp/fg-worker-runtime", dockerfile)
        self.assertLess(
            dockerfile.index("WORKDIR /tmp/fg-worker-runtime"),
            dockerfile.index("USER 10001:10001"),
        )

    def test_model_download_layers_are_bounded_complete_and_exactly_once(self) -> None:
        manifest = json.loads((WORKER_DIR / "model-manifest.json").read_text(encoding="utf-8"))
        records = {record["path"]: record["size"] for record in manifest["model"]["files"]}
        build_download = manifest["build_download"]
        assigned = [path for layer in build_download["layers"] for path in layer["files"]]
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(set(assigned), set(records))
        self.assertEqual(sum(records[path] for path in assigned), 20_538_488_559)
        self.assertEqual(build_download["registry_uncompressed_layer_limit_bytes"], 10_000_000_000)
        self.assertEqual(build_download["reserved_non_model_bytes_per_layer"], 20_000_000)
        for layer in build_download["layers"]:
            with self.subTest(layer=layer["id"]):
                payload_bytes = sum(records[path] for path in layer["files"])
                self.assertLessEqual(payload_bytes, build_download["max_model_bytes_per_layer"])
                self.assertLess(
                    payload_bytes + build_download["reserved_non_model_bytes_per_layer"],
                    build_download["registry_uncompressed_layer_limit_bytes"],
                )
                self.assertEqual(download_layer_paths(manifest, layer["id"]), layer["files"])

        dockerfile = (WORKER_DIR / "Dockerfile").read_text(encoding="utf-8")
        for layer in build_download["layers"]:
            self.assertEqual(dockerfile.count(f"--layer {layer['id']}"), 1)
        self.assertLess(
            dockerfile.index("--layer model-layer-03-runtime-components"),
            dockerfile.index("--full"),
        )
        self.assertNotIn("--squash", (WORKER_DIR / "scripts/build-local.sh").read_text())

    def test_model_download_layer_validator_rejects_duplicate_coverage(self) -> None:
        manifest = json.loads((WORKER_DIR / "model-manifest.json").read_text(encoding="utf-8"))
        manifest["build_download"]["layers"][1]["files"].append(
            manifest["build_download"]["layers"][0]["files"][0]
        )
        with self.assertRaises(ManifestError):
            download_layer_paths(manifest, manifest["build_download"]["layers"][0]["id"])

    def test_manifest_identity_checks_reject_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            model_copy = Path(temporary) / "model-manifest.json"
            model_copy.write_bytes((WORKER_DIR / "model-manifest.json").read_bytes() + b"\n")
            with self.assertRaises(VerificationError):
                verify_model_manifest_identity(model_copy)

            workflow_copy = Path(temporary) / "workflow-manifest.json"
            workflow_copy.write_bytes((WORKER_DIR / "workflow-manifest.json").read_bytes() + b"\n")
            with self.assertRaises(VerificationError):
                verify_workflow_manifest(workflow_copy)

    def test_every_direct_requirement_is_exactly_pinned(self) -> None:
        requirements = [
            line.strip()
            for line in (WORKER_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertGreater(len(requirements), 0)
        for requirement in requirements:
            with self.subTest(requirement=requirement):
                self.assertRegex(requirement, r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9_.+-]+$")

    def test_full_dependency_lock_is_hash_pinned_without_replacing_base_cuda(self) -> None:
        lock = (WORKER_DIR / "requirements.lock").read_text(encoding="utf-8")
        self.assertIn("--python-version 3.11 --python-platform x86_64-manylinux_2_28", lock)
        package_matches = list(re.finditer(r"(?m)^([A-Za-z0-9_.-]+)==([^ \\\n]+) \\$", lock))
        self.assertGreaterEqual(len(package_matches), 100)
        locked = {match.group(1).lower(): match.group(2) for match in package_matches}
        for index, match in enumerate(package_matches):
            end = package_matches[index + 1].start() if index + 1 < len(package_matches) else len(lock)
            self.assertIn("--hash=sha256:", lock[match.end():end], match.group(1))

        for requirement in (WORKER_DIR / "requirements.txt").read_text().splitlines():
            if not requirement or requirement.startswith("#"):
                continue
            direct = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==(.+)", requirement)
            self.assertIsNotNone(direct)
            assert direct is not None
            self.assertEqual(locked[direct.group(1).lower()], direct.group(2))
        for supplied_by_base in ["torch", "triton"]:
            self.assertNotIn(supplied_by_base, locked)
        self.assertFalse(any(package.startswith("nvidia-") for package in locked))

        dockerfile = (WORKER_DIR / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("--require-hashes --no-deps", dockerfile)
        self.assertIn("python -m pip check", dockerfile)

    def test_official_model_license_is_packaged_verbatim_with_notice(self) -> None:
        license_path = WORKER_DIR / "licenses/Tongyi-MAI-Z-Image/LICENSE"
        self.assertEqual(
            hashlib.sha256(license_path.read_bytes()).hexdigest(),
            "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
        )
        notice = (license_path.parent / "NOTICE").read_text(encoding="utf-8")
        self.assertIn("Tongyi-MAI/Z-Image", notice)
        self.assertIn("04cc4abb7c5069926f75c9bfde9ef43d49423021", notice)
        self.assertIn("Apache License, Version 2.0", notice)
        dockerfile = (WORKER_DIR / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY licenses ./licenses", dockerfile)

    def test_deployment_names_are_neutral(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [WORKER_DIR / "README.md", WORKER_DIR / "Dockerfile"]
        ).lower()
        for disallowed in ["porn", "nsfw", "sexual"]:
            self.assertNotIn(disallowed, combined)
        self.assertIn("fg-worker-v1", combined)
        self.assertIn("fg-image-v1", combined)


if __name__ == "__main__":
    unittest.main()
