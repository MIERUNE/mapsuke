import json
import tempfile
import unittest
from pathlib import Path

from qtaro.core.model_compat import _capabilities, listed_codex_models, unavailable_reason


class ModelCompatibilityTests(unittest.TestCase):
    def tearDown(self):
        _capabilities.cache_clear()

    def test_claude_version_blocks_only_models_requiring_newer_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory) / "claude"
            cli.write_text("#!/bin/sh\necho '2.1.238 (Claude Code)'\n")
            cli.chmod(0o755)
            self.assertIn("2.1.280", unavailable_reason("claude", str(cli), "claude-opus-5-5"))
            self.assertIn("2.1.257", unavailable_reason("claude", str(cli), "claude-fable-5-1"))
            self.assertIsNone(unavailable_reason("claude", str(cli), "claude-sonnet-5"))
            self.assertIsNone(unavailable_reason("claude", str(cli), ""))
            cli.write_text("#!/bin/sh\necho '2.1.280 (Claude Code)'\n")
            self.assertIsNone(unavailable_reason("claude", str(cli), "claude-opus-5-5"))
            self.assertIn("2.1.284", unavailable_reason("claude", str(cli), "claude-sonnet-5-5"))
            # A CLI from before Opus 4.6 still offers the 4.5 generation.
            cli.write_text("#!/bin/sh\necho '2.0.60 (Claude Code)'\n")
            self.assertIsNone(unavailable_reason("claude", str(cli), "claude-opus-4-5"))
            self.assertIsNone(unavailable_reason("claude", str(cli), "claude-sonnet-4-5"))
            self.assertIsNone(unavailable_reason("claude", str(cli), "claude-haiku-4-5-20251001"))
            for model, version in (("claude-opus-4-6", "2.1.32"), ("claude-sonnet-4-6", "2.1.45"),
                                   ("claude-opus-4-7", "2.1.111"), ("claude-opus-4-8", "2.1.154")):
                self.assertIn(version, unavailable_reason("claude", str(cli), model))

    def test_codex_uses_bundled_catalog_without_account_request(self):
        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory) / "codex"
            catalog = json.dumps({"models": [
                {"slug": "gpt-5.5", "visibility": "list"},
                {"slug": "gpt-6-astra", "visibility": "hidden"}]})
            cli.write_text("#!/bin/sh\necho '" + catalog + "'\n")
            cli.chmod(0o755)
            self.assertEqual(listed_codex_models(str(cli)), {"gpt-5.5"})
            self.assertIsNone(unavailable_reason("codex", str(cli), "gpt-6-astra"))

    def test_uninspectable_cli_does_not_guess(self):
        self.assertIsNone(unavailable_reason("claude", "/missing/claude", "claude-opus-5-5"))


if __name__ == "__main__":
    unittest.main()
