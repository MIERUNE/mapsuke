import importlib.util
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from mapsuke import i18n


def placeholders(text):
    return sorted(re.findall(r'\{[^{}]*\}|%[0-9A-Za-z]+', text))


class TranslationTests(unittest.TestCase):
    def test_english_source_and_locales(self):
        for locale_name, expected in (('en_US', 'New session'), ('ja_JP', '新しいセッション'),
                                      ('ja', '新しいセッション'), ('tr_TR', 'Yeni oturum'),
                                      ('tr', 'Yeni oturum'), ('TR-tr', 'Yeni oturum'),
                                      ('', 'New session'), ('pt_BR', 'New session'),
                                      ('jam_JM', 'New session'), ('trv_TW', 'New session')):
            with self.subTest(locale=locale_name), patch('mapsuke.i18n.ui_locale', return_value=locale_name):
                self.assertEqual(i18n.tr('New session'), expected)

    def test_untranslated_text_falls_back_to_english(self):
        for locale_name in ('ja_JP', 'tr_TR'):
            with patch('mapsuke.i18n.ui_locale', return_value=locale_name):
                self.assertEqual(i18n.tr('Text without a translation'), 'Text without a translation')
                # update_i18n.py adds new source text with an empty translation.
                with patch.dict(i18n.LANGUAGES[locale_name[:2]], {'New session': ''}):
                    self.assertEqual(i18n.tr('New session'), 'New session')

    def test_languages_map_locale_prefixes_to_dictionaries(self):
        self.assertIs(i18n.LANGUAGES['ja'], i18n.JA)
        self.assertIs(i18n.LANGUAGES['tr'], i18n.TR)

    def test_dictionaries_match_source_text(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('update_i18n', root / 'scripts/update_i18n.py')
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        used = script.used_keys()
        message = 'run python3 scripts/update_i18n.py'
        # Missing translations show English, so only unused keys are an error.
        for prefix, table in i18n.LANGUAGES.items():
            with self.subTest(language=prefix):
                self.assertEqual([key for key in table if key not in used], [], message)

    def test_turkish_keeps_placeholders_and_edges(self):
        for key, value in i18n.TR.items():
            if not value:
                continue
            with self.subTest(key=key[:60]):
                self.assertEqual(placeholders(value), placeholders(key))
                # Strings are joined to other text, so edge spaces and newlines must survive.
                self.assertEqual(value[:1].isspace(), key[:1].isspace())
                self.assertEqual(value[-1:].isspace(), key[-1:].isspace())
                self.assertEqual(value.startswith('\n'), key.startswith('\n'))
                self.assertEqual(value.endswith('\n'), key.endswith('\n'))
                if len(key) < 400:
                    self.assertEqual(value.count('\n'), key.count('\n'))

    def test_turkish_approval_wording_names_the_modes_and_buttons(self):
        tr_ = i18n.TR
        # The mode names are not translated in the selector, so every explanation keeps them.
        for key in ('Ask: confirm each run / Auto: AI assesses risk / Full auto: run without confirmation',
                    'Approve and run, then switch to Full auto without further confirmation',
                    'In Full auto mode, generated Python code runs without prior confirmation.',
                    'Switched to Full auto. Future Python code will run without confirmation.'):
            self.assertIn('Full auto', tr_[key])
        hint = tr_['\nChoose Approve and run, Always approve, or Stop.']
        for button in ('Approve and run', 'Always approve', 'Stop'):
            self.assertIn(tr_[button], hint)
        self.assertIn('onay', tr_['In Full auto mode, generated Python code runs without prior confirmation.'])


if __name__ == '__main__':
    unittest.main()
