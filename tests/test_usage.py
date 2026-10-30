import unittest
from mapsuke.core.models import MODELS, Model
from mapsuke.core.usage import context_meter
from mapsuke.i18n import tr


class UsageTests(unittest.TestCase):
    def test_zero_and_unmeasured_usage_show_zero(self):
        self.assertEqual(context_meter(None, 'claude-opus-5', MODELS), ('0', 0))
        self.assertEqual(context_meter({'tokens': 0, 'model': 'claude-opus-5'}, 'claude-opus-5', MODELS),
                         ('0', 0))

    def test_known_model_percent_and_unknown_limit(self):
        for model in ('claude-opus-5-5', 'claude-fable-5-1', 'claude-haiku-5-5'):
            self.assertEqual(context_meter({'tokens': 100_000, 'model': model}, model, MODELS)[1], 100)
        # Codex windows come from the CLI's catalog as the same Model rows.
        codex = {'gpt-6-sol': Model('GPT-6-Sol', 'gpt-6-sol', 1_050_000, None, None, True)}
        self.assertEqual(context_meter({'tokens': 105_000, 'model': 'gpt-6-sol'}, 'gpt-6-sol', codex),
                         ('10.0% · 105,000 / 1,050,000 token', 100))
        self.assertEqual(context_meter(
            {'tokens': 100_000, 'model': 'claude-opus-5', 'source': 'request'}, 'claude-opus-5', MODELS),
            ('10.0% · 100,000 / 1,000,000 token', 100))
        self.assertIn(tr(' tokens · limit unknown'), context_meter(
            {'tokens': 42, 'model': '', 'source': 'turn'}, '', MODELS)[0])
        self.assertIsNone(context_meter(
            {'tokens': 42, 'model': '', 'source': 'turn'}, '', MODELS)[1])
        self.assertEqual(context_meter(
            {'tokens': 42, 'model': 'gpt-5.5', 'source': 'turn'}, 'gpt-6-astra', MODELS), ('0', 0))
        self.assertEqual(context_meter(
            {'tokens': 100_000, 'model': 'claude-opus-5-20260901', 'source': 'request'},
            'claude-opus-5', MODELS)[1], 100)
