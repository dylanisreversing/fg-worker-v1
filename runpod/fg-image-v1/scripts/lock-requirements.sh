#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORKER_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
UV_BIN=${UV_BIN:-uv}
EXPECTED_UV_VERSION="uv 0.11.29"

case "$($UV_BIN --version)" in
  "$EXPECTED_UV_VERSION"|"$EXPECTED_UV_VERSION "*) ;;
  *)
  echo "requirements lock requires $EXPECTED_UV_VERSION" >&2
  exit 1
  ;;
esac

cd "$WORKER_DIR"
export UV_CUSTOM_COMPILE_COMMAND="uv pip compile requirements.txt --constraint base-constraints.txt --generate-hashes --python-version 3.11 --python-platform x86_64-manylinux_2_28 --no-build --exclude-newer 2026-07-16T15:00:00Z"

"$UV_BIN" pip compile requirements.txt \
  --constraint base-constraints.txt \
  --generate-hashes \
  --python-version 3.11 \
  --python-platform x86_64-manylinux_2_28 \
  --no-build \
  --exclude-newer 2026-07-16T15:00:00Z \
  --no-emit-package torch \
  --no-emit-package triton \
  --no-emit-package nvidia-cublas-cu12 \
  --no-emit-package nvidia-cuda-cupti-cu12 \
  --no-emit-package nvidia-cuda-nvrtc-cu12 \
  --no-emit-package nvidia-cuda-runtime-cu12 \
  --no-emit-package nvidia-cudnn-cu12 \
  --no-emit-package nvidia-cufft-cu12 \
  --no-emit-package nvidia-cufile-cu12 \
  --no-emit-package nvidia-curand-cu12 \
  --no-emit-package nvidia-cusolver-cu12 \
  --no-emit-package nvidia-cusparse-cu12 \
  --no-emit-package nvidia-cusparselt-cu12 \
  --no-emit-package nvidia-nccl-cu12 \
  --no-emit-package nvidia-nvjitlink-cu12 \
  --no-emit-package nvidia-nvtx-cu12 \
  --output-file requirements.lock
