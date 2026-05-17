"""Unit tests for redacted-proxy provider routing."""
import unittest

from main import _resolve_provider


class ResolveProviderTests(unittest.TestCase):
    def test_alias_without_explicit_provider(self):
        self.assertEqual(_resolve_provider("llama-3.3-70b", ""), ("groq", "llama-3.3-70b-versatile"))

    def test_alias_with_x_provider_still_maps_upstream(self):
        # CloudLLMClient always sends X-Provider; upstream id must not stay on alias name.
        self.assertEqual(
            _resolve_provider("llama-3.3-70b", "groq"),
            ("groq", "llama-3.3-70b-versatile"),
        )

    def test_venice_model(self):
        self.assertEqual(_resolve_provider("gemma-4-uncensored", ""), ("venice", "gemma-4-uncensored"))
        self.assertEqual(_resolve_provider("qwen-2-5-vl", "venice"), ("venice", "qwen-2-5-vl"))

    def test_venice_set_without_alias_entry(self):
        self.assertEqual(_resolve_provider("llama-3-3-70b", ""), ("venice", "llama-3-3-70b"))

    def test_grok_prefix(self):
        self.assertEqual(_resolve_provider("grok-4-1-fast", "xai"), ("xai", "grok-4-1-fast"))

    def test_explicit_provider_unknown_model(self):
        self.assertEqual(_resolve_provider("custom-model", "openai"), ("openai", "custom-model"))


if __name__ == "__main__":
    unittest.main()
