"""Fixed-contract image worker."""

WORKER_ID = "fg-worker-v1"
WORKER_VERSION = "1.0.1"
BASE_IMAGE = (
    "pytorch/pytorch:2.7.1-cuda12.8-cudnn9-runtime@sha256:"
    "c16f4c749e2d9e96878875cdf6cc45cddda1d1a36fddd371dd6f2360f1b6e2a2"
)
MODEL_REPO_ID = "Tongyi-MAI/Z-Image"
MODEL_REVISION = "04cc4abb7c5069926f75c9bfde9ef43d49423021"
MODEL_MANIFEST_SHA256 = "1308e63d14f7c607e032b84f8fe3ecffff94797b5b4c4a13484e8922fca61adb"
MODEL_DIR = "/opt/fg-model/Z-Image"
WORKFLOW_ID = "fg_image_v1"
WORKFLOW_VERSION = "fg_image_v1.0.0"
SETTINGS_PROFILE = "z_image_base_v1"
WORKFLOW_SHA256 = "9ac558d9616edbd6794cf0fd3399923d5c94669f870ea3f92f7609a35886a41f"
