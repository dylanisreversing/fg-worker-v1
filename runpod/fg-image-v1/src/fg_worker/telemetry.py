"""Small structured logger that never accepts request bodies or prompt text."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from . import WORKER_ID, WORKER_VERSION


def request_reference(job_id: Any) -> str:
    if not isinstance(job_id, str) or not job_id:
        return "none"
    return hashlib.sha256(job_id.encode("utf-8")).hexdigest()[:12]


def emit(
    event: str,
    *,
    request_ref: str | None = None,
    error_code: str | None = None,
    duration_ms: int | None = None,
    width: int | None = None,
    height: int | None = None,
    output_bytes: int | None = None,
) -> None:
    record: dict[str, Any] = {
        "event": event,
        "worker_id": WORKER_ID,
        "worker_version": WORKER_VERSION,
    }
    if request_ref is not None:
        record["request_ref"] = request_ref
    if error_code is not None:
        record["error_code"] = error_code
    if duration_ms is not None:
        record["duration_ms"] = max(0, int(duration_ms))
    if width is not None:
        record["width"] = int(width)
    if height is not None:
        record["height"] = int(height)
    if output_bytes is not None:
        record["output_bytes"] = int(output_bytes)
    print(json.dumps(record, sort_keys=True, separators=(",", ":")), flush=True)

