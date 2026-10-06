import unittest
from geotaro.core.usage import context_meter
from geotaro.i18n import tr


class UsageTests(unittest.TestCase):
    def test_zero_and_unmeasured_usage_show_zero(self):
        self.assertEqual(context_meter(None, 'claude-opus-5'), ('0', 0))
        self.assertEqual(context_meter({'tokens': 0, 'model': 'claude-opus-5'}, 'claude-opus-5'),
                         ('0', 0))

    def test_known_model_percent_and_unknown_limit(self):
        for model in ('claude-opus-5-5', 'claude-fable-5-1'):
            self.assertEqual(context_meter({'tokens': 100_000, 'model': model}, model)[1], 100)
        self.assertEqual(context_meter(
            {'tokens': 100_000, 'model': 'claude-opus-5', 'source': 'request'}, 'claude-opus-5'),
            ('10.0% · 100,000 / 1,000,000 token', 100))
        self.assertIn(tr(' tokens · limit unknown'), context_meter(
            {'tokens': 42, 'model': '', 'source': 'turn'}, '')[0])
        self.assertIsNone(context_meter(
            {'tokens': 42, 'model': '', 'source': 'turn'}, '')[1])
        self.assertEqual(context_meter(
            {'tokens': 42, 'model': 'gpt-5.5', 'source': 'turn'}, 'gpt-6-astra'), ('0', 0))
        self.assertEqual(context_meter(
            {'tokens': 100_000, 'model': 'claude-opus-5-20260901', 'source': 'request'},
            'claude-opus-5')[1], 100)
