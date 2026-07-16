#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORKER_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REPO_DIR=$(CDPATH= cd -- "$WORKER_DIR/../.." && pwd)

python3 "$WORKER_DIR/scripts/generate-source-manifest.py" --check
python3 -m unittest discover --start-directory "$WORKER_DIR/tests" --verbose
cd "$REPO_DIR"
node ./scripts/provider-boundary-scan.mjs
