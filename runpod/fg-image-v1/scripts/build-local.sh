#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORKER_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
IMAGE_TAG=${1:-fg-worker-v1:1.0.0}

exec docker build --platform linux/amd64 --tag "$IMAGE_TAG" "$WORKER_DIR"
