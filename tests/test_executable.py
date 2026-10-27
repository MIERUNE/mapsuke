import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from mapsuke.core.agent import default_executable


class ExecutableTests(unittest.TestCase):
    def test_finds_claude_in_local_bin_when_not_on_path(self):
        with tempfile.TemporaryDirectory() as home:
            binary = Path(home, '.local', 'bin', 'claude.exe' if sys.platform == 'win32' else 'claude')
            binary.parent.mkdir(parents=True)
            binary.touch(mode=0o755)
            with mock.patch.dict(os.environ, {'PATH': '', 'HOME': home, 'USERPROFILE': home}):
                self.assertEqual(os.path.normcase(default_executable()), os.path.normcase(str(binary)))
