import ast
from pathlib import Path
import unittest
from unittest.mock import patch

from core import i18n


class TranslationTests(unittest.TestCase):
    def test_english_source_and_japanese_locale(self):
        with patch('core.i18n.is_japanese', return_value=False):
            self.assertEqual(i18n.tr('New session'), 'New session')
            self.assertEqual(i18n.tr_inventory('plugin · project · Disabled in settings'),
                             'plugin · project · Disabled in settings')
        with patch('core.i18n.is_japanese', return_value=True):
            self.assertEqual(i18n.tr('New session'), '新しいセッション')
            self.assertEqual(i18n.tr_inventory('plugin · project · Disabled in settings'),
                             'plugin · project · 無効設定')
            self.assertEqual(i18n.tr_inventory('/tmp/x.json: could not be read'), '/tmp/x.json: 読み取れませんでした')
            self.assertEqual(i18n.tr_label('Claude · Response interrupted (not run)'), 'Claude · 応答中断（未実行）')

    def test_legacy_japanese_labels_map_to_english_source(self):
        self.assertEqual(i18n.from_legacy('あなた'), 'You')
        self.assertEqual(i18n.from_legacy('QGIS · 実行成功'), 'QGIS · Run succeeded')
        self.assertEqual(i18n.from_legacy('Claude · 応答中断（未実行）'), 'Claude · Response interrupted (not run)')
        self.assertEqual(i18n.from_legacy('QGIS · Run error'), 'QGIS · Run error')

    def test_every_marked_literal_has_a_japanese_translation(self):
        root = Path(__file__).resolve().parents[1]
        for path in [root / 'plugin.py', *(root / 'core').rglob('*.py')]:
            if path.name == 'i18n.py':
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and
                        node.func.id == 'tr' and node.args and isinstance(node.args[0], ast.Constant) and
                        isinstance(node.args[0].value, str)):
                    self.assertIn(node.args[0].value, i18n.JA, f'{path.name}:{node.lineno}')

    def test_persisted_role_labels_have_japanese_translations(self):
        for label in ('You', 'Error', 'Confirm execution', 'Run succeeded', 'Run error', 'Error / stopped',
                      'Save error', 'Load error', 'Response interrupted (not run)'):
            self.assertIn(label, i18n.JA)


if __name__ == '__main__':
    unittest.main()
