import json
import tempfile
import threading
import unittest
from pathlib import Path

from mapsuke.core import model_compat
from mapsuke.core.model_compat import _capabilities, hidden_reason, listed_codex_models, unavailable_reason


class ModelCompatibilityTests(unittest.TestCase):
    def tearDown(self):
        _capabilities.cache_clear()
        model_compat._inspected.clear()
        model_compat._pending.clear()

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
            cli.write_text("#!/bin/sh\necho '2.1.292 (Claude Code)'\n")
            self.assertIn("2.1.293", unavailable_reason("claude", str(cli), "claude-haiku-5-5"))
            cli.write_text("#!/bin/sh\necho '2.1.293 (Claude Code)'\n")
            self.assertIsNone(unavailable_reason("claude", str(cli), "claude-haiku-5-5"))
            # A CLI from before Opus 4.6 still offers the 4.5 generation.
            cli.write_text("#!/bin/sh\necho '2.0.60 (Claude Code)'\n")
            self.assertIsNone(unavailable_reason("claude", str(cli), "claude-opus-4-5"))
            self.assertIsNone(unavailable_reason("claude", str(cli), "claude-sonnet-4-5"))
            self.assertIsNone(unavailable_reason("claude", str(cli), "claude-haiku-4-5-20251001"))
            for model, version in (("claude-opus-4-6", "2.1.32"), ("claude-sonnet-4-6", "2.1.45"),
                                   ("claude-opus-4-7", "2.1.111"), ("claude-opus-4-8", "2.1.154")):
                self.assertIn(version, unavailable_reason("claude", str(cli), model))

    def test_codex_uses_account_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory) / "codex"
            catalog = json.dumps({"models": [
                {"slug": "gpt-5.5", "visibility": "list"},
                {"slug": "gpt-6-astra", "visibility": "hidden"}]})
            # --bundled would hide models the account catalog already serves.
            cli.write_text("#!/bin/sh\n[ \"$*\" = 'debug models' ] || exit 1\necho '" + catalog + "'\n")
            cli.chmod(0o755)
            self.assertEqual(listed_codex_models(str(cli)), {"gpt-5.5"})
            self.assertIsNone(unavailable_reason("codex", str(cli), "gpt-6-astra"))
            # The catalog only filters the default service's picker.
            self.assertIn("gpt-6-astra", hidden_reason("codex", str(cli), "default", "gpt-6-astra"))
            self.assertIsNone(hidden_reason("codex", str(cli), "default", "gpt-5.5"))
            self.assertIsNone(hidden_reason("codex", str(cli), "default", ""))
            self.assertIsNone(hidden_reason("codex", str(cli), "amazon-bedrock", "gpt-6-astra"))

    def test_codex_inspection_with_callback_does_not_block(self):
        with tempfile.TemporaryDirectory() as directory:
            cli = Path(directory) / "codex"
            cli.write_text("#!/bin/sh\nsleep 0.2\necho '{\"models\": [{\"slug\": \"gpt-5.5\", \"visibility\": \"list\"}]}'\n")
            cli.chmod(0o755)
            done = threading.Event()
            self.assertIsNone(listed_codex_models(str(cli), done.set))
            # A second request while inspecting starts no other process.
            self.assertIsNone(hidden_reason("codex", str(cli), "default", "gpt-6-astra", done.set))
            self.assertTrue(done.wait(5))
            self.assertEqual(listed_codex_models(str(cli), done.set), {"gpt-5.5"})
            self.assertEqual(_capabilities.cache_info().misses, 1)

    def test_uninspectable_cli_does_not_guess(self):
        self.assertIsNone(unavailable_reason("claude", "/missing/claude", "claude-opus-5-5"))


if __name__ == "__main__":
    unittest.main()
