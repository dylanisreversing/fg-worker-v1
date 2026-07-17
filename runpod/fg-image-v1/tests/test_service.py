from __future__ import annotations

import base64
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

from PIL import Image


WORKER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_DIR / "src"))

from fg_worker.runtime import RuntimeFailure  # noqa: E402
from fg_worker.provenance import worker_build_id  # noqa: E402
from fg_worker.service import WorkerFailure, handle_job  # noqa: E402


class FakeRuntime:
    def __init__(self, *, fail: bool = False, wrong_size: bool = False):
        self.fail = fail
        self.wrong_size = wrong_size
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        if self.fail:
            raise RuntimeFailure("private upstream detail")
        size = (64, 64) if self.wrong_size else (request.width, request.height)
        image = Image.new("RGB", size, (40, 80, 120))
        image.getexif()[270] = "private metadata"
        return image


def job(prompt: str = "A neutral test image of fictional adults.") -> dict[str, object]:
    return {
        "id": "provider-job-id-that-must-not-be-logged",
        "input": {
            "workflow_id": "fg_image_v1",
            "workflow_version": "fg_image_v1.0.0",
            "settings_profile": "z_image_base_v1",
            "prompt": prompt,
            "negative_prompt": "text artifacts",
            "seed": 123,
            "width": 1024,
            "height": 1536,
        },
    }


class ServiceTests(unittest.TestCase):
    def test_returns_metadata_free_inline_webp_with_fixed_provenance(self) -> None:
        runtime = FakeRuntime()
        with contextlib.redirect_stdout(io.StringIO()):
            output = handle_job(job(), runtime)
        self.assertEqual(set(output), {"image", "model_metadata"})
        self.assertEqual(set(output["image"]), {"base64", "media_type"})
        self.assertEqual(output["image"]["media_type"], "image/webp")
        encoded = base64.b64decode(output["image"]["base64"], validate=True)
        with Image.open(io.BytesIO(encoded)) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, (1024, 1536))
            self.assertEqual(dict(image.getexif()), {})
            self.assertNotIn("icc_profile", image.info)
            self.assertNotIn("xmp", image.info)
        self.assertEqual(
            output["model_metadata"],
            {
                "workflow_id": "fg_image_v1",
                "workflow_version": "fg_image_v1.0.0",
                "settings_profile": "z_image_base_v1",
                "worker_build_id": worker_build_id(),
                "workflow_sha256": "5e145012ace3367db33fe34706894e12a495c3580b303052820693445edc215e",
                "model_revision": "04cc4abb7c5069926f75c9bfde9ef43d49423021",
                "model_manifest_sha256": "2f464e78877760b887c1bdef3a2c8386920c6d37903cdaf198c2cd4284a27a92",
                "seed": 123,
                "width": 1024,
                "height": 1536,
                "sampler": "flow_match_euler",
                "scheduler": "shift_6",
                "steps": 40,
                "cfg": 4.0,
            },
        )

    def test_logs_never_contain_prompt_raw_job_id_or_image_bytes(self) -> None:
        secret_prompt = "UNIQUE_PROMPT_MUST_NEVER_APPEAR"
        logs = io.StringIO()
        with contextlib.redirect_stdout(logs):
            output = handle_job(job(secret_prompt), FakeRuntime())
        logged = logs.getvalue()
        self.assertNotIn(secret_prompt, logged)
        self.assertNotIn("provider-job-id-that-must-not-be-logged", logged)
        self.assertNotIn(output["image"]["base64"], logged)
        for line in logged.splitlines():
            record = json.loads(line)
            self.assertIn(record["event"], {"request_received", "request_succeeded"})

    def test_sanitizes_runtime_failures(self) -> None:
        logs = io.StringIO()
        with contextlib.redirect_stdout(logs), self.assertRaises(WorkerFailure) as context:
            handle_job(job("SENSITIVE_PROMPT"), FakeRuntime(fail=True))
        self.assertEqual(str(context.exception), "Generation failed.")
        self.assertNotIn("private upstream detail", logs.getvalue())
        self.assertNotIn("SENSITIVE_PROMPT", logs.getvalue())

    def test_accepts_platform_envelope_fields_but_rejects_invalid_jobs(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            output = handle_job(
                job()
                | {
                    "webhook": None,
                    "policy": {"executionTimeout": 600000},
                    "platform_trace": "unused-platform-metadata",
                },
                FakeRuntime(),
            )
            self.assertEqual(output["image"]["media_type"], "image/webp")
            with self.assertRaises(WorkerFailure):
                handle_job({"input": job()["input"]}, FakeRuntime())
            with self.assertRaises(WorkerFailure):
                handle_job({"id": 42, "input": job()["input"]}, FakeRuntime())

    def test_rejects_wrong_sized_results(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(WorkerFailure):
                handle_job(job(), FakeRuntime(wrong_size=True))


if __name__ == "__main__":
    unittest.main()
