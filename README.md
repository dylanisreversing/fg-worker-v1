# fg-worker-v1

Immutable, prompt-to-image RunPod worker build for the isolated `fg-image-v1`
serverless lane. The build contains no runtime credentials and accepts only the
versioned request contract in `runpod/fg-image-v1`.

The source identity for this release is:

`fg-worker-v1@sha256:5191183f488b83f2e64441ebd055b0643e2d7b329029c6b761cb1cd4c0098b8a`

The container is built by a one-job ephemeral self-hosted runner because the
pinned model artifact is larger than a standard hosted runner's disk. Every
model file is checksum-verified during the build and the final registry digest
is the deployment identity.
