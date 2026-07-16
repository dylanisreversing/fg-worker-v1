from __future__ import annotations

import sys
import unittest
from pathlib import Path


WORKER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_DIR / "src"))

from fg_worker.contract import ContractError, parse_generation_request  # noqa: E402


def valid_input() -> dict[str, object]:
    return {
        "workflow_id": "fg_image_v1",
        "workflow_version": "fg_image_v1.0.0",
        "settings_profile": "z_image_base_v1",
        "prompt": "A detailed studio photograph of fictional adults.",
        "negative_prompt": "text artifacts",
        "seed": 42,
        "width": 1024,
        "height": 1536,
    }


class ContractTests(unittest.TestCase):
    def test_accepts_only_the_two_fixed_shapes(self) -> None:
        portrait = parse_generation_request(valid_input())
        self.assertEqual((portrait.width, portrait.height), (1024, 1536))
        landscape_input = valid_input() | {"width": 1536, "height": 1024}
        landscape = parse_generation_request(landscape_input)
        self.assertEqual((landscape.width, landscape.height), (1536, 1024))

    def test_negative_prompt_is_optional(self) -> None:
        request = valid_input()
        del request["negative_prompt"]
        self.assertEqual(parse_generation_request(request).negative_prompt, "")

    def test_rejects_mismatched_fixed_contract_identity(self) -> None:
        for field in ["workflow_id", "workflow_version", "settings_profile"]:
            with self.subTest(field=field), self.assertRaises(ContractError) as context:
                parse_generation_request(valid_input() | {field: "different"})
            self.assertEqual(context.exception.code, "contract_mismatch")

    def test_rejects_unknown_and_forbidden_fields(self) -> None:
        forbidden = [
            "image",
            "image_url",
            "upload",
            "reference",
            "workflow",
            "model",
            "lora",
            "model_downloads",
            "callback_url",
            "output_url",
        ]
        for field in forbidden:
            with self.subTest(field=field), self.assertRaises(ContractError) as context:
                parse_generation_request(valid_input() | {field: "blocked"})
            self.assertEqual(context.exception.code, "unknown_field")

    def test_rejects_url_like_prompt_values(self) -> None:
        for value in [
            "use https://example.invalid/reference.png",
            "open file:///tmp/source.png",
            "data:image/png;base64,AAAA",
            "studio scene (https://example.invalid/reference.png)",
        ]:
            with self.subTest(value=value), self.assertRaises(ContractError) as context:
                parse_generation_request(valid_input() | {"prompt": value})
            self.assertEqual(context.exception.code, "url_not_allowed")

    def test_rejects_invalid_dimensions(self) -> None:
        for width, height in [(1024, 1024), (768, 1024), (1536, 1536), (True, 1536)]:
            with self.subTest(width=width, height=height), self.assertRaises(ContractError):
                parse_generation_request(valid_input() | {"width": width, "height": height})

    def test_rejects_invalid_seed_types_and_ranges(self) -> None:
        for seed in [True, -1, 2**32, 1.5, "42"]:
            with self.subTest(seed=seed), self.assertRaises(ContractError) as context:
                parse_generation_request(valid_input() | {"seed": seed})
            self.assertEqual(context.exception.code, "invalid_seed")

    def test_rejects_missing_blank_oversized_and_control_character_prompts(self) -> None:
        cases = [
            {},
            {"prompt": "  "},
            {"prompt": "x" * 4097},
            {"prompt": "valid\x00hidden"},
        ]
        for override in cases:
            request = valid_input() | override
            if not override:
                del request["prompt"]
            with self.subTest(override=override), self.assertRaises(ContractError):
                parse_generation_request(request)


if __name__ == "__main__":
    unittest.main()
