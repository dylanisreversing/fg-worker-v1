"""Pinned local model runtime. No caller-controlled model or workflow selection."""

from __future__ import annotations

import threading
from typing import Any

from . import MODEL_DIR
from .contract import GenerationRequest


INFERENCE_STEPS = 40
GUIDANCE_SCALE = 4.0
CFG_NORMALIZATION = False


class RuntimeFailure(RuntimeError):
    """A sanitized runtime failure."""


class ZImageRuntime:
    def __init__(self, pipeline: Any, torch_module: Any):
        self._pipeline = pipeline
        self._torch = torch_module
        self._inference_lock = threading.Lock()

    @classmethod
    def load(cls) -> "ZImageRuntime":
        try:
            import torch
            from diffusers import ZImagePipeline

            if not torch.cuda.is_available():
                raise RuntimeFailure("GPU runtime unavailable.")
            pipeline = ZImagePipeline.from_pretrained(
                MODEL_DIR,
                torch_dtype=torch.bfloat16,
                low_cpu_mem_usage=False,
                local_files_only=True,
            )
            pipeline.to("cuda")
            pipeline.set_progress_bar_config(disable=True)
            return cls(pipeline=pipeline, torch_module=torch)
        except RuntimeFailure:
            raise
        except Exception:
            raise RuntimeFailure("Model runtime failed to initialize.") from None

    def generate(self, request: GenerationRequest) -> Any:
        try:
            generator = self._torch.Generator(device="cuda").manual_seed(request.seed)
            with self._inference_lock, self._torch.inference_mode():
                result = self._pipeline(
                    prompt=request.prompt,
                    negative_prompt=request.negative_prompt,
                    height=request.height,
                    width=request.width,
                    cfg_normalization=CFG_NORMALIZATION,
                    num_inference_steps=INFERENCE_STEPS,
                    guidance_scale=GUIDANCE_SCALE,
                    generator=generator,
                )
            images = getattr(result, "images", None)
            if not isinstance(images, list) or len(images) != 1:
                raise RuntimeFailure("Model returned an invalid result.")
            return images[0]
        except RuntimeFailure:
            raise
        except Exception:
            raise RuntimeFailure("Generation failed.") from None


_runtime: ZImageRuntime | None = None
_runtime_lock = threading.Lock()


def get_runtime() -> ZImageRuntime:
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:
                _runtime = ZImageRuntime.load()
    return _runtime

