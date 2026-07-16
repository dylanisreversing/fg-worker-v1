from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image


WORKER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_DIR / "src"))

from fg_worker.contract import GenerationRequest  # noqa: E402
from fg_worker.runtime import RuntimeFailure, ZImageRuntime  # noqa: E402


class FakeInferenceMode:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FakeGenerator:
    def __init__(self, device: str):
        self.device = device
        self.seed = None

    def manual_seed(self, seed: int):
        self.seed = seed
        return self


class FakeTorch:
    Generator = FakeGenerator

    @staticmethod
    def inference_mode():
        return FakeInferenceMode()


class FakePipeline:
    def __init__(self, *, images=None):
        self.calls = []
        self.images = images

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(images=self.images)


class RuntimeTests(unittest.TestCase):
    def test_uses_only_fixed_inference_settings(self) -> None:
        image = Image.new("RGB", (1024, 1536))
        pipeline = FakePipeline(images=[image])
        runtime = ZImageRuntime(pipeline=pipeline, torch_module=FakeTorch())
        request = GenerationRequest(
            prompt="test prompt",
            negative_prompt="test negative",
            seed=987,
            width=1024,
            height=1536,
        )
        self.assertIs(runtime.generate(request), image)
        self.assertEqual(len(pipeline.calls), 1)
        call = pipeline.calls[0]
        self.assertEqual(call["prompt"], "test prompt")
        self.assertEqual(call["negative_prompt"], "test negative")
        self.assertEqual((call["width"], call["height"]), (1024, 1536))
        self.assertEqual(call["num_inference_steps"], 40)
        self.assertEqual(call["guidance_scale"], 4.0)
        self.assertFalse(call["cfg_normalization"])
        self.assertEqual(call["generator"].device, "cuda")
        self.assertEqual(call["generator"].seed, 987)
        self.assertNotIn("model", call)
        self.assertNotIn("workflow", call)
        self.assertNotIn("image", call)

    def test_rejects_missing_or_multiple_images(self) -> None:
        request = GenerationRequest("prompt", "", 1, 1024, 1536)
        for images in [None, [], [Image.new("RGB", (1, 1)), Image.new("RGB", (1, 1))]]:
            with self.subTest(images=images), self.assertRaises(RuntimeFailure):
                ZImageRuntime(FakePipeline(images=images), FakeTorch()).generate(request)


if __name__ == "__main__":
    unittest.main()
