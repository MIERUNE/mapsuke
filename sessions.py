"""Atomic, local session persistence. Python objects and QGIS state are never serialized."""
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4


class SessionStore:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path))
        self.connection.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, title TEXT NOT NULL, updated TEXT NOT NULL, payload TEXT NOT NULL)')
        self.connection.commit()

    def save(self, session_id, title, payload):
        session_id = session_id or str(uuid4())
        serialized = json.dumps(payload, ensure_ascii=False)
        with self.connection:
            self.connection.execute('INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?)',
                                    (session_id, title, datetime.now(timezone.utc).isoformat(), serialized))
        return session_id

    def list(self):
        return self.connection.execute('SELECT id, title, updated FROM sessions ORDER BY updated DESC').fetchall()

    def load(self, session_id):
        row = self.connection.execute('SELECT payload FROM sessions WHERE id = ?', (session_id,)).fetchone()
        if row is None:
            raise ValueError('セッションが見つかりません')
        payload = json.loads(row[0])
        if not isinstance(payload, dict) or payload.get('version') != 1:
            raise ValueError('未対応のセッション形式です')
        if not isinstance(payload.get('history'), list) or not isinstance(payload.get('messages'), list):
            raise ValueError('セッションの履歴を読み取れません')
        if not all(isinstance(payload.get(key, ""), str) for key in ("model", "draft", "title")):
            raise ValueError('セッション設定の形式が不正です')
        if not isinstance(payload.get('claude_started', False), bool):
            raise ValueError('セッション継続状態が不正です')
        for key in ('enable_skills', 'enable_connectors'):
            if not isinstance(payload.get(key, False), bool):
                raise ValueError('スキル・コネクタ設定の形式が不正です')
        if payload.get('provider', 'claude') not in ('claude', 'codex'):
            raise ValueError('未対応のエージェントです')
        if not isinstance(payload.get('agent_started', False), bool):
            raise ValueError('セッション継続状態が不正です')
        if payload.get('native_session_id') is not None and not isinstance(payload['native_session_id'], str):
            raise ValueError('エージェントのセッションIDが不正です')
        overrides = payload.get('codex_capabilities', {})
        if (not isinstance(overrides, dict) or set(overrides) - {'skills', 'connectors'} or
                any(not isinstance(rows, dict) or any(not isinstance(key, str) or type(value) is not bool
                    for key, value in rows.items()) for rows in overrides.values())):
            raise ValueError('Codexのスキル・コネクタ設定の形式が不正です')
        cursor = payload.get('sent_history', 0)
        if type(cursor) is not int or not 0 <= cursor <= len(payload['history']):
            raise ValueError('セッション継続位置が不正です')
        for message in payload['messages']:
            if not isinstance(message, dict) or not all(isinstance(message.get(key), str) for key in ('role', 'text', 'code')):
                raise ValueError('保存メッセージの形式が不正です')
        for entry in payload['history']:
            if not isinstance(entry, dict) or entry.get('role') not in ('user', 'assistant', 'bridge') or 'content' not in entry:
                raise ValueError('保存履歴の形式が不正です')
            if entry['role'] == 'user' and not isinstance(entry['content'], str):
                raise ValueError('保存履歴の形式が不正です')
        return payload

    def delete(self, session_id):
        with self.connection:
            self.connection.execute('DELETE FROM sessions WHERE id = ?', (session_id,))

    def close(self):
        self.connection.close()
