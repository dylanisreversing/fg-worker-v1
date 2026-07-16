"""Request execution and private inline result encoding."""

from __future__ import annotations

import base64
import io
import time
from typing import Any, Mapping

from PIL import Image

from . import (
    MODEL_MANIFEST_SHA256,
    MODEL_REVISION,
    SETTINGS_PROFILE,
    WORKFLOW_ID,
    WORKFLOW_SHA256,
    WORKFLOW_VERSION,
)
from .contract import ContractError, parse_generation_request
from .provenance import worker_build_id
from .runtime import GUIDANCE_SCALE, INFERENCE_STEPS, RuntimeFailure
from .telemetry import emit, request_reference


OUTPUT_MIME_TYPE = "image/webp"
OUTPUT_QUALITY = 92
MAX_OUTPUT_BYTES = 7 * 1024 * 1024
SAMPLER = "flow_match_euler"
SCHEDULER = "shift_6"


class WorkerFailure(RuntimeError):
    """An intentionally generic error safe for provider serialization."""


def _encode_webp(image: Any, expected_width: int, expected_height: int) -> bytes:
    if not isinstance(image, Image.Image) or image.size != (expected_width, expected_height):
        raise RuntimeFailure("Model returned an invalid result.")

    # Reconstruct pixel data into a new image so no EXIF, XMP, ICC profile, or
    # other source metadata can survive the boundary.
    rgb = image.convert("RGB")
    clean = Image.new("RGB", rgb.size)
    clean.paste(rgb)
    output = io.BytesIO()
    clean.save(
        output,
        format="WEBP",
        quality=OUTPUT_QUALITY,
        method=6,
        lossless=False,
    )
    encoded = output.getvalue()
    if not encoded or len(encoded) > MAX_OUTPUT_BYTES:
        raise RuntimeFailure("Encoded result is outside the allowed size.")
    return encoded


def handle_job(job: Any, runtime: Any) -> dict[str, Any]:
    started_at = time.monotonic()
    job_mapping: Mapping[str, Any] = job if isinstance(job, Mapping) else {}
    request_ref = request_reference(job_mapping.get("id"))
    emit("request_received", request_ref=request_ref)

    try:
        if not isinstance(job, Mapping) or set(job.keys()) - {"id", "input"}:
            raise ContractError("invalid_job")
        request = parse_generation_request(job.get("input"))
        build_id = worker_build_id()
        image = runtime.generate(request)
        encoded = _encode_webp(image, request.width, request.height)
    except ContractError as error:
        emit("request_rejected", request_ref=request_ref, error_code=error.code)
        raise WorkerFailure(error.public_message) from None
    except RuntimeFailure:
        emit("request_failed", request_ref=request_ref, error_code="generation_failed")
        raise WorkerFailure("Generation failed.") from None
    except Exception:
        emit("request_failed", request_ref=request_ref, error_code="generation_failed")
        raise WorkerFailure("Generation failed.") from None

    duration_ms = round((time.monotonic() - started_at) * 1000)
    emit(
        "request_succeeded",
        request_ref=request_ref,
        duration_ms=duration_ms,
        width=request.width,
        height=request.height,
        output_bytes=len(encoded),
    )
    model_metadata = {
        "workflow_id": WORKFLOW_ID,
        "workflow_version": WORKFLOW_VERSION,
        "settings_profile": SETTINGS_PROFILE,
        "worker_build_id": build_id,
        "workflow_sha256": WORKFLOW_SHA256,
        "model_revision": MODEL_REVISION,
        "model_manifest_sha256": MODEL_MANIFEST_SHA256,
        "seed": request.seed,
        "width": request.width,
        "height": request.height,
        "sampler": SAMPLER,
        "scheduler": SCHEDULER,
        "steps": INFERENCE_STEPS,
        "cfg": GUIDANCE_SCALE,
    }
    return {
        "image": {
            "base64": base64.b64encode(encoded).decode("ascii"),
            "media_type": OUTPUT_MIME_TYPE,
        },
        "model_metadata": model_metadata,
    }
