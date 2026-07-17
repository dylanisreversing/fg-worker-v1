# `fg-image-v1` worker

This directory is the reproducible source for one fixed prompt-to-image
serverless worker. It is deliberately independent from every pre-existing
endpoint, template, storage path, and application backend.

## Immutable runtime

- Base image:
  `pytorch/pytorch:2.7.1-cuda12.8-cudnn9-runtime@sha256:c16f4c749e2d9e96878875cdf6cc45cddda1d1a36fddd371dd6f2360f1b6e2a2`
- Model: `Tongyi-MAI/Z-Image`, Apache-2.0 metadata at immutable revision
  `04cc4abb7c5069926f75c9bfde9ef43d49423021`
- Inference: BF16 CUDA, 40 steps, guidance 4.0, CFG normalization disabled
- Shapes: exactly `1024x1536` or `1536x1024`
- Output: metadata-free WebP, quality 92, returned inline as base64 with a
  7 MiB raw-byte hard limit so the base64 JSON stays below 10 MB

`model-manifest.json` pins every required snapshot file by path, byte size, and
SHA-256. `workflow-manifest.json` separately pins the request, inference, and
output contract. `requirements.lock` pins the complete Python 3.11 Linux
dependency graph with distribution hashes; PyTorch 2.7.1 and its matching CUDA
packages remain supplied by the immutable base and cannot be replaced by pip.
The build downloads only the model allowlist, verifies every checksum, and
writes a deterministic verification stamp. The verbatim upstream Apache-2.0
license and the snapshot provenance notice are packaged under `licenses/`.
The model and worker trees are made read-only.

`source-manifest.json` covers the Dockerfile, dependency inputs, build-time
downloader, runtime source, entrypoint, manifests, and license files by byte
size and SHA-256. Its own raw SHA-256 is deliberately not embedded in any
covered file: the reported worker build identity is derived as
`fg-worker-v1@sha256:<source-manifest-sha256>`. This avoids self-reference while
making runtime drift fail bootstrap and local verification.

The adapter provenance values for this source revision are:

- worker build:
  `fg-worker-v1@sha256:20a02903ea033edd90e2d764f7ac97477dfce06dfe0be8066ac6b0adf14c51d7`
- source-manifest SHA-256:
  `20a02903ea033edd90e2d764f7ac97477dfce06dfe0be8066ac6b0adf14c51d7`
- workflow SHA-256:
  `5e145012ace3367db33fe34706894e12a495c3580b303052820693445edc215e`
- model revision: `04cc4abb7c5069926f75c9bfde9ef43d49423021`
- model-manifest SHA-256:
  `2f464e78877760b887c1bdef3a2c8386920c6d37903cdaf198c2cd4284a27a92`
Container startup checks the stamp, every file size, CUDA, and the exact
pipeline import before the worker is marked ready. A full checksum recheck is
available with:

```sh
python -m fg_worker.bootstrap --full
```

The pinned model files total 20,538,488,559 bytes. The Dockerfile downloads
three manifest-defined groups in three distinct image layers: 9,973,727,144,
8,060,896,856, and 2,503,864,559 bytes. The largest transformer shard is alone.
Every group stays within a 9,980,000,000-byte model payload cap, with another
20,000,000 bytes reserved below the 10,000,000,000-byte uncompressed registry
layer limit. Tests prove complete exactly-once coverage, bounded groups, and
that the final full verification follows all three downloads. Building the
image still requires substantial local disk and network capacity; no model
artifact is downloaded by the application at request time.

## Request contract

RunPod supplies the outer job object. Its `input` may contain only:

```json
{
  "workflow_id": "fg_image_v1",
  "workflow_version": "fg_image_v1.0.0",
  "settings_profile": "z_image_base_v1",
  "prompt": "A detailed studio photograph of clearly mature fictional adults.",
  "negative_prompt": "text artifacts, malformed hands",
  "seed": 123456,
  "width": 1024,
  "height": 1536
}
```

The three identity fields are mandatory fixed assertions, not runtime workflow
selection. `negative_prompt` is the only optional field. Unknown fields are
rejected. In particular there is no upload, image URL,
reference image, raw workflow, runtime model, LoRA, download, file, callback,
or output destination input. URL-like prompt values are also rejected. The
worker never fetches request-controlled network content.

The outer job envelope is owned by RunPod. The worker requires a non-empty
string `id` and the strict `input` object above, but ignores unused platform
metadata fields that RunPod may add to that envelope. No outer field can alter
the model, workflow, prompt, output destination, or storage behavior.

Successful output has exactly two top-level keys:

```json
{
  "image": {
    "base64": "<raw WebP base64>",
    "media_type": "image/webp"
  },
  "model_metadata": {
    "workflow_id": "fg_image_v1",
    "workflow_version": "fg_image_v1.0.0",
    "settings_profile": "z_image_base_v1"
  }
}
```

The actual metadata object also contains the pinned build/workflow/model
digests and fixed inference measurements required by the application adapter.
There is no data URI and no provider URL. The application must still decode,
validate, re-encode, privately store, moderate, and authorize the result before
delivery or settlement.

Logs contain only a one-way 12-character job reference, event name, controlled
error code, timing, dimensions, and byte count. Prompt text, negative prompt,
raw job IDs, base64 bytes, credentials, filesystem paths, and exceptions are
never logged.

## Local verification

The unit suite uses a fake model runtime and never downloads weights or runs a
generation:

```sh
./scripts/verify-local.sh
```

Regenerate the dependency lock only with uv 0.11.29; the script fixes CPython
3.11, x86_64 manylinux 2.28, the resolution cutoff, and the base-image package
exclusions:

```sh
./scripts/lock-requirements.sh
python3 ./scripts/generate-source-manifest.py --write
```

Build explicitly (this downloads and verifies the pinned public model snapshot):

```sh
./scripts/build-local.sh fg-worker-v1:1.0.1
```

Do not deploy a mutable tag. Push once, record the registry-reported OCI digest,
and configure the serverless template with `repository@sha256:<digest>`.

## Deployment and rollback contract

Use a new template named `fg-worker-v1` and a new endpoint named
`fg-image-v1`, with zero minimum workers and one maximum worker. Do not attach
credentials or storage owned by another service. The result is inline, so the
provider worker needs no object-storage credential and cannot create a public
object URL.

Rollback means changing the isolated template to the last recorded, verified
OCI digest and then restoring the endpoint to that template. Never rebuild an
old mutable tag. Keep the previous digest and its matching model manifest in
the operator record, and stop new submissions while a rollback is in progress.
