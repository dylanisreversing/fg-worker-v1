"""Strict, high-level request contract for the worker."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from . import SETTINGS_PROFILE, WORKFLOW_ID, WORKFLOW_VERSION


MAX_PROMPT_CHARS = 4096
MAX_PROMPT_BYTES = 16384
MAX_NEGATIVE_PROMPT_CHARS = 4096
MAX_NEGATIVE_PROMPT_BYTES = 16384
MAX_SEED = (2**32) - 1
ALLOWED_DIMENSIONS = frozenset({(1024, 1536), (1536, 1024)})
ALLOWED_FIELDS = frozenset(
    {
        "workflow_id",
        "workflow_version",
        "settings_profile",
        "prompt",
        "negative_prompt",
        "seed",
        "width",
        "height",
    }
)
URL_LIKE = re.compile(r"(?i)\b(?:https?|ftp|file|data):(?:/{0,2})")


class ContractError(ValueError):
    """A request error whose message is safe to return to the provider."""

    def __init__(self, code: str, public_message: str = "Invalid generation request."):
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    negative_prompt: str
    seed: int
    width: int
    height: int


def _validate_text(
    value: Any,
    *,
    required: bool,
    max_chars: int,
    max_bytes: int,
) -> str:
    if not isinstance(value, str):
        raise ContractError("invalid_text")

    normalized = value.strip()
    if required and not normalized:
        raise ContractError("empty_prompt")
    if len(normalized) > max_chars or len(normalized.encode("utf-8")) > max_bytes:
        raise ContractError("text_too_long")
    if any(ord(character) < 32 and character not in "\n\t" for character in normalized):
        raise ContractError("invalid_text")
    if URL_LIKE.search(normalized):
        raise ContractError("url_not_allowed")
    return normalized


def parse_generation_request(value: Any) -> GenerationRequest:
    if not isinstance(value, Mapping):
        raise ContractError("invalid_input")

    keys = set(value.keys())
    if not all(isinstance(key, str) for key in keys) or not keys.issubset(ALLOWED_FIELDS):
        raise ContractError("unknown_field")
    if not {
        "workflow_id",
        "workflow_version",
        "settings_profile",
        "prompt",
        "seed",
        "width",
        "height",
    }.issubset(keys):
        raise ContractError("missing_field")
    if (
        value["workflow_id"] != WORKFLOW_ID
        or value["workflow_version"] != WORKFLOW_VERSION
        or value["settings_profile"] != SETTINGS_PROFILE
    ):
        raise ContractError("contract_mismatch")

    prompt = _validate_text(
        value["prompt"],
        required=True,
        max_chars=MAX_PROMPT_CHARS,
        max_bytes=MAX_PROMPT_BYTES,
    )
    negative_prompt = _validate_text(
        value.get("negative_prompt", ""),
        required=False,
        max_chars=MAX_NEGATIVE_PROMPT_CHARS,
        max_bytes=MAX_NEGATIVE_PROMPT_BYTES,
    )

    seed = value["seed"]
    width = value["width"]
    height = value["height"]
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= MAX_SEED:
        raise ContractError("invalid_seed")
    if isinstance(width, bool) or not isinstance(width, int):
        raise ContractError("invalid_dimensions")
    if isinstance(height, bool) or not isinstance(height, int):
        raise ContractError("invalid_dimensions")
    if (width, height) not in ALLOWED_DIMENSIONS:
        raise ContractError("invalid_dimensions")

    return GenerationRequest(
        prompt=prompt,
        negative_prompt=negative_prompt,
        seed=seed,
        width=width,
        height=height,
    )
