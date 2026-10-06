import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from geotaro import i18n


class TranslationTests(unittest.TestCase):
    def test_english_source_and_japanese_locale(self):
        with patch('geotaro.i18n.is_japanese', return_value=False):
            self.assertEqual(i18n.tr('New session'), 'New session')
        with patch('geotaro.i18n.is_japanese', return_value=True):
            self.assertEqual(i18n.tr('New session'), '新しいセッション')

    def test_dictionary_matches_source_text(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('update_i18n', root / 'scripts/update_i18n.py')
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        used = script.used_keys()
        message = 'run python3 scripts/update_i18n.py'
        self.assertEqual({key: used[key] for key in used if key not in i18n.JA}, {}, message)
        self.assertEqual([key for key in i18n.JA if key not in used], [], message)
        self.assertEqual([key for key, value in i18n.JA.items() if not value], [], 'fill in empty translations')

    def test_persisted_role_labels_have_japanese_translations(self):
        for label in ('You', 'Error', 'Confirm execution', 'Run succeeded', 'Run error', 'Error / stopped',
                      'Save error', 'Load error', 'Response interrupted (not run)'):
            self.assertIn(label, i18n.JA)


if __name__ == '__main__':
    unittest.main()
