import tempfile
from pathlib import Path
import unittest
from sessions import SessionStore


class SessionTests(unittest.TestCase):
    def test_recent_page_and_literal_search(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionStore(Path(directory) / 'sessions.sqlite3')
            payload = {'version': 1, 'history': [], 'messages': []}
            ids = [store.save(None, 'map_%' if index == 7 else f'map {index}', payload)
                   for index in range(32)]
            self.assertEqual(len(store.list()), 25)
            self.assertEqual([row[0] for row in store.list(10, 25)], list(reversed(ids[:7])))
            self.assertEqual([row[0] for row in store.list(search='_%')], [ids[7]])
            self.assertEqual(store.latest_id(), ids[-1])
            self.assertTrue(store.exists(ids[0]))
            store.close()

    def test_persistence_update_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sessions.sqlite3'
            store = SessionStore(path)
            payload = {'version': 1, 'history': [{'role': 'user', 'content': '札幌'}],
                       'messages': [], 'model': 'sonnet', 'draft': '下書き', 'interrupted': True}
            first = store.save(None, '札幌', payload)
            second = store.save(None, '別の会話', dict(payload, model='opus'))
            store.close()
            store = SessionStore(path)
            self.assertEqual(store.load(first), payload)
            self.assertEqual(len(store.list()), 2)
            store.save(first, '更新した会話', dict(payload, interrupted=False))
            self.assertEqual(store.list()[0][0], first)
            self.assertFalse(store.load(first)['interrupted'])
            with self.assertRaises(TypeError):
                store.save(first, '失敗', {'object': object()})
            self.assertEqual(store.list()[0][1], '更新した会話')
            store.delete(first)
            self.assertEqual([row[0] for row in store.list()], [second])
            with self.assertRaises(ValueError):
                store.load(first)
            store.close()
