# fg-worker-v1

Immutable, prompt-to-image RunPod worker build for the isolated `fg-image-v1`
serverless lane. The build contains no runtime credentials and accepts only the
versioned request contract in `runpod/fg-image-v1`.

The source identity for this release is:

`fg-worker-v1@sha256:82db57029436a8652c8e80650a0a0fdf85338020501529267529ac499cc3237e`

The container is built by a one-job ephemeral self-hosted runner because the
pinned model artifact is larger than a standard hosted runner's disk. Every
model file is checksum-verified during the build and the final registry digest
is the deployment identity.
