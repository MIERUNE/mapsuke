import ast
from pathlib import Path
import unittest
from unittest.mock import patch

import i18n


class TranslationTests(unittest.TestCase):
    def test_english_default_and_japanese_locale(self):
        with patch('i18n.is_japanese', return_value=False):
            self.assertEqual(i18n.tr('新しいセッション'), 'New session')
            self.assertEqual(i18n.tr_inventory('plugin · project · 無効設定'),
                             'plugin · project · Disabled in settings')
        with patch('i18n.is_japanese', return_value=True):
            self.assertEqual(i18n.tr('新しいセッション'), '新しいセッション')

    def test_every_marked_literal_has_an_english_translation(self):
        root = Path(__file__).resolve().parents[1]
        for path in root.glob('*.py'):
            if path.name == 'i18n.py':
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and
                        node.func.id == 'tr' and node.args and isinstance(node.args[0], ast.Constant) and
                        isinstance(node.args[0].value, str)):
                    self.assertIn(node.args[0].value, i18n.EN, f'{path.name}:{node.lineno}')


if __name__ == '__main__':
    unittest.main()
