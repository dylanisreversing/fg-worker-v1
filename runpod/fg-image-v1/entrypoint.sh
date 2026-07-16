#!/bin/sh
set -eu

python -m fg_worker.bootstrap --quick --runtime
exec python /opt/fg-worker/handler.py
