FROM pytorch/pytorch:2.7.1-cuda12.8-cudnn9-runtime@sha256:c16f4c749e2d9e96878875cdf6cc45cddda1d1a36fddd371dd6f2360f1b6e2a2

LABEL org.opencontainers.image.title="fg-worker-v1" \
      org.opencontainers.image.version="1.0.1" \
      org.opencontainers.image.description="Pinned prompt-to-image inference worker"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/tmp/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    HF_XET_HIGH_PERFORMANCE=1 \
    TRANSFORMERS_VERBOSITY=error \
    DIFFUSERS_VERBOSITY=error \
    RUNPOD_DEBUG_LEVEL=WARNING \
    PYTHONPATH=/opt/fg-worker/src

WORKDIR /opt/fg-worker

COPY requirements.txt requirements.lock base-constraints.txt ./
RUN python -m pip install --no-cache-dir --require-hashes --no-deps \
      --requirement requirements.lock \
    && python -m pip check

COPY Dockerfile source-manifest.json model-manifest.json workflow-manifest.json ./
COPY download_model.py handler.py entrypoint.sh ./
COPY licenses ./licenses
COPY scripts/lock-requirements.sh scripts/generate-source-manifest.py ./scripts/
COPY src ./src

RUN mkdir -p /opt/fg-model/Z-Image \
    && python ./download_model.py \
      --manifest /opt/fg-worker/model-manifest.json \
      --target /opt/fg-model/Z-Image \
      --layer model-layer-01-transformer-primary \
    && rm -rf /opt/fg-model/Z-Image/.cache /tmp/huggingface

RUN python ./download_model.py \
      --manifest /opt/fg-worker/model-manifest.json \
      --target /opt/fg-model/Z-Image \
      --layer model-layer-02-text-encoder \
    && rm -rf /opt/fg-model/Z-Image/.cache /tmp/huggingface

RUN python ./download_model.py \
      --manifest /opt/fg-worker/model-manifest.json \
      --target /opt/fg-model/Z-Image \
      --layer model-layer-03-runtime-components \
    && rm -rf /opt/fg-model/Z-Image/.cache /tmp/huggingface

RUN python -m fg_worker.bootstrap \
      --full \
      --write-stamp \
      --manifest /opt/fg-worker/model-manifest.json \
      --model-dir /opt/fg-model/Z-Image

RUN groupadd --gid 10001 worker \
    && useradd --create-home --uid 10001 --gid 10001 worker \
    && install -d --owner=10001 --group=10001 --mode=0700 /tmp/fg-worker-runtime \
    && chown -R root:root /opt/fg-worker /opt/fg-model \
    && chmod -R a-w /opt/fg-worker /opt/fg-model \
    && chmod 0555 /opt/fg-worker/entrypoint.sh

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    DIFFUSERS_OFFLINE=1

WORKDIR /tmp/fg-worker-runtime

USER 10001:10001

HEALTHCHECK --interval=60s --timeout=20s --start-period=180s --retries=3 \
  CMD ["python", "-m", "fg_worker.bootstrap", "--quick", "--runtime"]

ENTRYPOINT ["/opt/fg-worker/entrypoint.sh"]
