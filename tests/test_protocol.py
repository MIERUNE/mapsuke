import json
import unittest
from qtaro.core.protocol import parse_response


class ProtocolTests(unittest.TestCase):
    def test_bundled_skills_are_installed_into_existing_cli_folders(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from qtaro.core.protocol import BUNDLED_SKILLS, install_bundled_skills
        paths = sorted(BUNDLED_SKILLS.glob('*/SKILL.md'))
        self.assertEqual(len(paths), 4)
        with tempfile.TemporaryDirectory() as directory:
            claude, codex = Path(directory) / 'claude', Path(directory) / 'codex'
            claude.mkdir()
            with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(claude), 'CODEX_HOME': str(codex)}):
                self.assertEqual(len(install_bundled_skills()), 4)
                self.assertFalse(codex.exists())
                edited = claude / 'skills' / paths[0].parent.name / 'SKILL.md'
                edited.write_text('Edited', encoding='utf-8')
                (claude / 'skills' / paths[1].parent.name / 'SKILL.md').unlink()
                (claude / 'skills' / paths[1].parent.name).rmdir()
                self.assertEqual(install_bundled_skills(), [claude / 'skills' / paths[1].parent.name])
                self.assertEqual(edited.read_text(encoding='utf-8'), 'Edited')
                codex.mkdir()
                self.assertEqual(len(install_bundled_skills(overwrite=True)), 8)
                for root in (claude, codex):
                    for path in paths:
                        copied = root / 'skills' / path.parent.name / 'SKILL.md'
                        self.assertEqual(copied.read_text(encoding='utf-8'), path.read_text(encoding='utf-8'))

    def test_system_prompt_names_the_provider_skills_folder(self):
        import os
        from unittest.mock import patch
        from qtaro.core.protocol import build_system_prompt, SYSTEM_PROMPT
        with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': '/tmp/claude-home', 'CODEX_HOME': '/tmp/codex-home'}):
            claude, codex = build_system_prompt('claude'), build_system_prompt('codex')
        self.assertTrue(claude.startswith(SYSTEM_PROMPT))
        self.assertIn('/tmp/claude-home/skills', claude)
        self.assertIn('/tmp/codex-home/skills', codex)
        self.assertNotIn('name: qgis-cartography', claude)

    def test_system_prompt_is_written_in_english(self):
        import re
        from qtaro.core.protocol import build_system_prompt
        self.assertIsNone(re.search(r'[\u3000-\u30ff\u4e00-\u9fff\uff00-\uffef]', build_system_prompt()))

    def test_custom_prompt_is_appended_only_when_set(self):
        from qtaro.core.protocol import build_system_prompt
        self.assertNotIn('User custom instructions', build_system_prompt('claude', '  \n'))
        prompt = build_system_prompt('claude', '  Use EPSG:6677 for outputs.\n')
        self.assertIn('User custom instructions', prompt)
        self.assertTrue(prompt.endswith('Use EPSG:6677 for outputs.'))

    def test_claude_stream_input_puts_images_before_text(self):
        import base64
        import tempfile
        from pathlib import Path
        from qtaro.core.protocol import claude_stream_input
        with tempfile.TemporaryDirectory() as directory:
            png, jpeg = Path(directory) / 'map.png', Path(directory) / 'photo.JPG'
            png.write_bytes(b'png-bytes')
            jpeg.write_bytes(b'jpeg-bytes')
            line = claude_stream_input('{"conversation": []}', [str(png), str(jpeg)])
        self.assertTrue(line.endswith('\n') and line.count('\n') == 1)
        message = json.loads(line)
        self.assertEqual(message['type'], 'user')
        content = message['message']['content']
        self.assertEqual([block['type'] for block in content], ['image', 'image', 'text'])
        self.assertEqual([block['source']['media_type'] for block in content[:2]], ['image/png', 'image/jpeg'])
        self.assertEqual(base64.b64decode(content[0]['source']['data']), b'png-bytes')
        self.assertEqual(content[2]['text'], '{"conversation": []}')

    def test_structured_and_legacy_envelopes(self):
        result = {"message": "日本語", "code": "print(1)"}
        for envelope in ({"structured_output": result}, {"result": json.dumps(result)}):
            self.assertEqual(parse_response(json.dumps(envelope)), result)

    def test_title_and_generation_request(self):
        from qtaro.core.protocol import build_prompt, SCHEMA
        result = {"message": "調べます", "code": "", "title": "札幌の人口分布"}
        self.assertIn("title", SCHEMA["required"])
        for envelope in ({"structured_output": result}, {"result": json.dumps(result)}):
            self.assertEqual(parse_response(json.dumps(envelope)), result)
        self.assertTrue(json.loads(build_prompt([], {}, generate_title=True))["generate_title"])
        self.assertFalse(json.loads(build_prompt([], {}))["generate_title"])
        for title in (None, 123, [], {}):
            with self.assertRaises(ValueError):
                parse_response(json.dumps({"structured_output": dict(result, title=title)}))

    def test_approval_assessment(self):
        from qtaro.core.protocol import build_prompt
        result = {"message": "確認", "code": "print(1)", "title": "", "requires_approval": True,
                  "approval_reason": "出力先を上書きします"}
        self.assertEqual(parse_response(json.dumps({"structured_output": result})), result)
        for value in ("false", 0, None):
            with self.assertRaises(ValueError):
                parse_response(json.dumps({"structured_output": dict(result, requires_approval=value)}))
        for patch in ({"approval_reason": ""}, {"approval_reason": 123}):
            with self.assertRaises(ValueError):
                parse_response(json.dumps({"structured_output": dict(result, **patch)}))
        del result["approval_reason"]
        with self.assertRaises(ValueError):
            parse_response(json.dumps({"structured_output": result}))
        self.assertEqual(json.loads(build_prompt([], {}, approval_mode="ask"))["approval_mode"], "ask")

    def test_question_hands_turn_to_user(self):
        from qtaro.core.protocol import SCHEMA
        self.assertTrue({"question", "choices"} <= set(SCHEMA["required"]))
        result = {"message": "対象が2つあります", "code": "", "title": "", "requires_approval": False,
                  "approval_reason": "", "question": "どちらのレイヤーを使いますか？",
                  "choices": ["道路（2021）", "道路（2024）"]}
        self.assertEqual(parse_response(json.dumps({"structured_output": result})), result)
        self.assertEqual(parse_response(json.dumps({"structured_output": dict(result, choices=[])}))["choices"], [])
        for patch in ({"code": "print(1)"}, {"question": "", "choices": ["A"]}, {"choices": "A"},
                      {"choices": [""]}, {"choices": [1]}, {"choices": list("ABCDEF")}, {"question": 1}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                parse_response(json.dumps({"structured_output": dict(result, **patch)}))
        no_question = dict(result, question="", choices=[], code="print(1)")
        self.assertEqual(parse_response(json.dumps({"structured_output": no_question})), no_question)

    def test_path_request_opens_a_picker_only_with_a_question(self):
        from qtaro.core.protocol import SCHEMA
        self.assertTrue({"path_request", "path_suggestion"} <= set(SCHEMA["required"]))
        result = {"message": "結果を保存します", "code": "", "title": "", "requires_approval": False,
                  "approval_reason": "", "question": "保存先は？", "choices": ["/data/out.gpkg"],
                  "path_request": "file", "path_suggestion": "/data/out.gpkg"}
        self.assertEqual(parse_response(json.dumps({"structured_output": result})), result)
        for patch in ({"path_request": "save"}, {"path_request": "file", "question": "", "choices": []},
                      {"path_suggestion": None}):
            with self.assertRaises(ValueError):
                parse_response(json.dumps({"structured_output": dict(result, **patch)}))

    def test_suggestion_is_only_for_a_finished_turn(self):
        from qtaro.core.protocol import SCHEMA
        self.assertIn("suggestion", SCHEMA["required"])
        result = {"message": "完了しました", "code": "", "title": "", "requires_approval": False,
                  "approval_reason": "", "question": "", "choices": [], "path_request": "",
                  "path_suggestion": "", "suggestion": "ツールとして保存"}
        self.assertEqual(parse_response(json.dumps({"structured_output": result})), result)
        for patch in ({"code": "print(1)"}, {"question": "保存しますか？"}, {"suggestion": 1}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                parse_response(json.dumps({"structured_output": dict(result, **patch)}))

    def test_invalid_output_never_becomes_code(self):
        for value in ('[]', 'not json', '{"result":"```python\\nprint(1)```"}',
                      '{"structured_output":{"message":"ok","code":123}}',
                      '{"is_error":true,"result":"login required"}',
                      '{"subtype":"error_max_turns","structured_output":{"message":"x","code":"x"}}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_response(value)


class StreamTests(unittest.TestCase):
    def test_claude_context_uses_latest_request_input_including_cache(self):
        from qtaro.core.protocol import StreamResponse
        stream = StreamResponse()
        for tokens in (100, 250):
            event = {'type': 'stream_event', 'event': {
                'type': 'message_start', 'message': {'model': 'claude-sonnet-5', 'usage': {
                    'input_tokens': tokens, 'cache_creation_input_tokens': 20,
                    'cache_read_input_tokens': 30}}}}
            stream.feed((json.dumps(event) + '\n').encode())
        self.assertEqual(stream.context_usage,
                         {'tokens': 300, 'model': 'claude-sonnet-5', 'source': 'request'})

    def test_fragmented_utf8_and_structured_preview(self):
        from qtaro.core.protocol import StreamResponse
        parser = StreamResponse()
        def event(inner):
            return (json.dumps({"type": "stream_event", "event": inner}, ensure_ascii=False) + "\n").encode()
        data = event({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "調査中"}})
        for byte in data:
            parser.feed(bytes([byte]))
        self.assertEqual(parser.preview["message"], "調査中")
        parser.feed(event({"type": "content_block_start", "index": 1,
                           "content_block": {"type": "tool_use", "name": "StructuredOutput"}}))
        payload = json.dumps({"message": '確認しました。"code"', "code": "print('札幌')\n"})
        for char in payload:
            parser.feed(event({"type": "content_block_delta", "index": 1,
                               "delta": {"type": "input_json_delta", "partial_json": char}}))
        self.assertEqual(parser.preview, json.loads(payload))
        self.assertIsNone(parser.result)
        result = {"type": "result", "structured_output": json.loads(payload)}
        parser.feed(json.dumps(result).encode(), final=True)
        self.assertEqual(parser.result, result)

    def test_structured_restatement_of_text_reply_streams_once(self):
        from qtaro.core.protocol import StreamResponse
        parser = StreamResponse()
        def event(inner):
            return (json.dumps({"type": "stream_event", "event": inner}, ensure_ascii=False) + "\n").encode()
        parser.feed(event({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "こんにちは。"}}))
        parser.feed(event({"type": "content_block_start", "index": 1,
                           "content_block": {"type": "tool_use", "name": "StructuredOutput"}}))
        seen = []
        for char in json.dumps({"message": "こんにちは。準備できました。", "code": ""}, ensure_ascii=False):
            seen.append(parser.feed(event({"type": "content_block_delta", "index": 1,
                                           "delta": {"type": "input_json_delta", "partial_json": char}}))["message"])
        self.assertTrue(all(len(b) >= len(a) for a, b in zip(seen, seen[1:])))
        self.assertEqual(seen[-1], "こんにちは。準備できました。")

    def test_title_does_not_block_or_leak_into_preview(self):
        from qtaro.core.protocol import partial_strings
        for payload in ('{"title":"札幌", "message":"確認", "code":"print(1)"}',
                        '{"message":"確認", "title":"札幌", "code":"print(1)"}'):
            self.assertEqual(partial_strings(payload), {"message": "確認", "code": "print(1)"})
        self.assertEqual(partial_strings('{"title":"途中'), {})

    def test_question_does_not_block_or_leak_into_preview(self):
        from qtaro.core.protocol import partial_strings
        self.assertEqual(partial_strings('{"question":"どれ？", "message":"確認", "code":""}'),
                         {"message": "確認", "code": ""})

    def test_partial_escapes(self):
        from qtaro.core.protocol import partial_strings
        self.assertEqual(partial_strings('{"message":"hello\\'), {"message": "hello"})
        self.assertEqual(partial_strings('{"message":"hello\\u30'), {"message": "hello"})
        self.assertEqual(partial_strings('{"code":"print(1)","message":"ok'),
                         {"code": "print(1)", "message": "ok"})


class CodexStreamTests(unittest.TestCase):
    def test_reasoning_summary_is_preview_only(self):
        from qtaro.core.protocol import CodexStreamResponse
        stream = CodexStreamResponse()
        events = [
            {'type': 'item.updated', 'item': {'id': 'r1', 'type': 'reasoning', 'text': '調査'}},
            {'type': 'item.completed', 'item': {'id': 'r1', 'type': 'reasoning', 'text': '調査しました'}},
            {'type': 'item.completed', 'item': {'id': 'r2', 'type': 'reasoning', 'text': '結果を確認しました'}},
        ]
        for event in events:
            stream.feed((json.dumps(event, ensure_ascii=False) + '\n').encode())
        self.assertEqual(stream.preview['reasoning'], '調査しました\n\n結果を確認しました')
        self.assertEqual(stream.preview['message'], '')
        self.assertIsNone(stream.result)
        payload = {'message': '完了', 'code': ''}
        stream.feed((json.dumps({'type': 'item.completed', 'item': {
            'type': 'agent_message', 'text': json.dumps(payload, ensure_ascii=False)}}) + '\n').encode())
        stream.feed(b'{"type":"turn.completed"}\n')
        self.assertEqual(stream.preview['reasoning'], '調査しました\n\n結果を確認しました')
        self.assertEqual(parse_response(json.dumps(stream.result)), payload)

    def test_codex_turn_input_is_marked_as_turn_total(self):
        from qtaro.core.protocol import CodexStreamResponse
        stream = CodexStreamResponse()
        stream.feed(b'{"type":"turn.completed","usage":{"input_tokens":420,"output_tokens":19}}\n')
        self.assertEqual(stream.context_usage, {'tokens': 420, 'model': '', 'source': 'turn'})

    def test_fragmented_events_and_final_gate(self):
        from qtaro.core.protocol import CodexStreamResponse
        stream = CodexStreamResponse()
        events = [
            {'type': 'thread.started', 'thread_id': 'native-id'},
            {'type': 'item.updated', 'item': {'type': 'agent_message', 'text': '{"message":"札幌'}},
        ]
        for event in events:
            for byte in (json.dumps(event, ensure_ascii=False) + '\n').encode():
                stream.feed(bytes([byte]))
        self.assertEqual(stream.session_id, 'native-id')
        self.assertEqual(stream.preview['message'], '札幌')
        self.assertIsNone(stream.result)
        payload = {'message': '札幌', 'code': 'print(1)'}
        stream.feed((json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps(payload)}}) + '\n').encode())
        self.assertIsNone(stream.result)
        stream.feed(b'{"type":"turn.completed"}', final=True)
        self.assertEqual(parse_response(json.dumps(stream.result)), payload)

    def test_failure_and_malformed_final_never_execute(self):
        from qtaro.core.protocol import CodexStreamResponse
        for events in [
            [{'type': 'turn.failed', 'error': {'message': 'authentication required'}}],
            [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'not JSON'}}, {'type': 'turn.completed'}],
        ]:
            stream = CodexStreamResponse()
            stream.feed(('\n'.join(json.dumps(e) for e in events) + '\n').encode())
            with self.assertRaises(ValueError):
                parse_response(json.dumps(stream.result))
