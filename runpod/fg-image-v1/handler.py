"""RunPod entrypoint for the fixed image worker."""

from __future__ import annotations

from typing import Any

from fg_worker.runtime import RuntimeFailure, get_runtime
from fg_worker.service import handle_job
from fg_worker.telemetry import emit


def handler(job: Any) -> dict[str, Any]:
    return handle_job(job, get_runtime())


def main() -> int:
    emit("worker_bootstrap_started")
    try:
        get_runtime()
    except RuntimeFailure:
        emit("worker_bootstrap_failed", error_code="runtime_unavailable")
        raise SystemExit("worker bootstrap failed") from None

    import runpod

    emit("worker_ready")
    runpod.serverless.start({"handler": handler})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
