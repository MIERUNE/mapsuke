import json
import sys
import unittest
from mapsuke.core.protocol import parse_response


def reply(kind, message="x", title="", **fields):
    """A reply as the CLI returns it; parse_response flattens the action into the record."""
    return {"message": message, "title": title, "action": {"kind": kind, **fields}}


def parsed(wire, **patch):
    """Parse a reply, optionally with fields of its action replaced."""
    return parse_response(json.dumps({"structured_output": dict(wire, action=dict(wire["action"], **patch))}))


class ProtocolTests(unittest.TestCase):
    def test_bundled_skill_sync_updates_existing_and_requires_consent_for_creation(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from mapsuke.core.protocol import BUNDLED_SKILLS, sync_bundled_skills
        paths = sorted(BUNDLED_SKILLS.glob('*/SKILL.md'))
        self.assertEqual(len(paths), 2)
        with tempfile.TemporaryDirectory() as directory:
            claude, codex = Path(directory) / 'claude', Path(directory) / 'codex'
            claude.mkdir()
            with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(claude), 'CODEX_HOME': str(codex)}):
                targets = [claude / 'skills' / path.parent.name for path in paths]
                self.assertEqual(sync_bundled_skills('claude', sys.executable), targets)
                self.assertFalse((claude / 'skills').exists())
                self.assertEqual(sync_bundled_skills('claude', sys.executable, create_missing=True), [])
                self.assertFalse(codex.exists())
                edited = targets[0] / 'SKILL.md'
                edited.write_text('Edited', encoding='utf-8')
                (targets[1] / 'SKILL.md').unlink()
                targets[1].rmdir()
                unrelated = claude / 'skills' / 'personal' / 'SKILL.md'
                unrelated.parent.mkdir()
                unrelated.write_text('Keep', encoding='utf-8')
                self.assertEqual(sync_bundled_skills('claude', sys.executable), [targets[1]])
                self.assertFalse(targets[1].exists())
                self.assertEqual(edited.read_bytes(), paths[0].read_bytes())
                self.assertEqual(unrelated.read_text(), 'Keep')
                self.assertEqual(sync_bundled_skills('claude', sys.executable, create_missing=True), [])
                for path, target in zip(paths, targets):
                    self.assertEqual((target / 'SKILL.md').read_bytes(), path.read_bytes())
                # Every sync refreshes existing copies; syncing Codex leaves Claude alone.
                edited.write_text('Edited again', encoding='utf-8')
                codex.mkdir()
                self.assertEqual(sync_bundled_skills('codex', sys.executable), [codex / 'skills' / path.parent.name for path in paths])
                self.assertFalse((codex / 'skills').exists())
                self.assertEqual(sync_bundled_skills('codex', sys.executable, create_missing=True), [])
                self.assertEqual(edited.read_text(), 'Edited again')
                self.assertEqual(sync_bundled_skills('claude', sys.executable), [])
                self.assertEqual(edited.read_bytes(), paths[0].read_bytes())

    def test_skill_sync_skips_missing_or_nonexecutable_cli_without_updating(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from mapsuke.core.protocol import BUNDLED_SKILLS, sync_bundled_skills
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'claude'
            skill = next(BUNDLED_SKILLS.glob('*/SKILL.md'))
            target = config / 'skills' / skill.parent.name / 'SKILL.md'
            target.parent.mkdir(parents=True)
            target.write_text('Keep', encoding='utf-8')
            nonexecutable = root / 'not-executable'
            nonexecutable.write_text('Not a CLI', encoding='utf-8')
            with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(config)}):
                unavailable = ['', str(root / 'missing-cli')]
                if os.name != 'nt':
                    unavailable.append(str(nonexecutable))
                for executable in unavailable:
                    for consent in (False, True):
                        self.assertEqual(sync_bundled_skills('claude', executable, create_missing=consent), [])
                        self.assertEqual(target.read_text(), 'Keep')
                        self.assertEqual(len(list(target.parents[1].iterdir())), 1)
                # A command name on PATH is accepted, just like a configured full path.
                with patch.dict(os.environ, {'PATH': str(Path(sys.executable).parent)}):
                    missing = sync_bundled_skills('claude', Path(sys.executable).name)
                self.assertEqual(len(missing), 1)
                self.assertEqual(target.read_bytes(), skill.read_bytes())

    def test_skill_sync_requires_an_existing_config_directory_and_valid_skill_destination(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from mapsuke.core.protocol import sync_bundled_skills
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config'
            for provider, variable in (('claude', 'CLAUDE_CONFIG_DIR'), ('codex', 'CODEX_HOME')):
                with patch.dict(os.environ, {variable: str(config)}):
                    self.assertEqual(sync_bundled_skills(provider, sys.executable, create_missing=True), [])
                    self.assertFalse(config.exists())
                    config.write_text('Not a directory', encoding='utf-8')
                    self.assertEqual(sync_bundled_skills(provider, sys.executable), [])
                    config.unlink()
                    config.mkdir()
                    (config / 'skills').write_text('Keep', encoding='utf-8')
                    self.assertEqual(sync_bundled_skills(provider, sys.executable, create_missing=True), [])
                    self.assertEqual((config / 'skills').read_text(), 'Keep')
                    (config / 'skills').unlink()
                    self.assertEqual(len(sync_bundled_skills(provider, sys.executable)), 2)
                    self.assertFalse((config / 'skills').exists())
                    config.rmdir()

    def test_system_prompt_names_the_provider_skills_folder(self):
        import os
        from unittest.mock import patch
        from mapsuke.core.protocol import build_system_prompt, SYSTEM_PROMPT
        with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': '/tmp/claude-home', 'CODEX_HOME': '/tmp/codex-home'}):
            claude, codex = build_system_prompt('claude'), build_system_prompt('codex')
        self.assertTrue(claude.startswith(SYSTEM_PROMPT))
        self.assertIn('/tmp/claude-home/skills', claude)
        self.assertIn('/tmp/codex-home/skills', codex)
        self.assertNotIn('name: mapsuke-cartography', claude)

    def test_system_prompt_is_written_in_english(self):
        import re
        from mapsuke.core.protocol import build_system_prompt
        self.assertIsNone(re.search(r'[\u3000-\u30ff\u4e00-\u9fff\uff00-\uffef]', build_system_prompt()))

    def test_system_prompt_uses_mapsuke_background_downloader(self):
        from mapsuke.core.protocol import build_system_prompt
        prompt = build_system_prompt()
        self.assertIn('mapsuke:download_file', prompt)
        self.assertIn('run_processing_in_background', prompt)
        self.assertIn('QgsProcessing.TEMPORARY_OUTPUT', prompt)
        self.assertIn('Do not use native:filedownloader', prompt)

    def test_custom_prompt_is_appended_only_when_set(self):
        from mapsuke.core.protocol import build_system_prompt
        self.assertNotIn('User custom instructions', build_system_prompt('claude', '  \n'))
        prompt = build_system_prompt('claude', '  Use EPSG:6677 for outputs.\n')
        self.assertIn('User custom instructions', prompt)
        self.assertTrue(prompt.endswith('Use EPSG:6677 for outputs.'))

    def test_claude_stream_input_puts_images_before_text(self):
        import base64
        import tempfile
        from pathlib import Path
        from mapsuke.core.protocol import claude_stream_input
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
        wire = reply("run", message="日本語", code="print(1)", risk="")
        result = {"message": "日本語", "title": "", "code": "print(1)", "risk": ""}
        for envelope in ({"structured_output": wire}, {"result": json.dumps(wire)}):
            self.assertEqual(parse_response(json.dumps(envelope)), result)

    def test_title_and_generation_request(self):
        from mapsuke.core.protocol import build_prompt, SCHEMA
        wire = reply("finish", message="調べます", title="札幌の人口分布", suggestion="")
        result = {"message": "調べます", "code": "", "title": "札幌の人口分布", "suggestion": ""}
        self.assertIn("title", SCHEMA["required"])
        for envelope in ({"structured_output": wire}, {"result": json.dumps(wire)}):
            self.assertEqual(parse_response(json.dumps(envelope)), result)
        self.assertTrue(json.loads(build_prompt([], {}, generate_title=True))["generate_title"])
        self.assertFalse(json.loads(build_prompt([], {}))["generate_title"])
        self.assertEqual(json.loads(build_prompt([], {"versions": {"qgis": "4.0"}}))["versions"], {"qgis": "4.0"})
        self.assertNotIn("versions", json.loads(build_prompt([])))
        for title in (None, 123, [], {}):
            with self.assertRaises(ValueError):
                parse_response(json.dumps({"structured_output": dict(wire, title=title)}))

    def test_python_packages(self):
        from mapsuke.core.environment import python_packages
        from types import SimpleNamespace
        from unittest import mock
        dists = [SimpleNamespace(metadata={"Name": name}, version=version) for name, version in
                 (("foo_bar", "2"), ("numpy", "1"), ("Foo.Bar", "1"), (None, "0"), ("GDAL", "3"))]
        with mock.patch("importlib.metadata.distributions", return_value=dists):
            packages = python_packages()
        self.assertEqual(packages, ["foo_bar 2", "GDAL 3", "numpy 1"])

    def test_approval_assessment(self):
        from mapsuke.core.protocol import build_prompt
        wire = reply("run", message="確認", code="print(1)", risk="出力先を上書きします")
        result = {"message": "確認", "code": "print(1)", "title": "", "risk": "出力先を上書きします"}
        self.assertEqual(parsed(wire), result)
        # An empty risk is the assessment that no approval is needed.
        self.assertEqual(parsed(wire, risk="")["risk"], "")
        # The former pair of fields is no longer part of the contract.
        for patch in ({"risk": 123}, {"risk": True}, {"requires_approval": True}, {"approval_reason": "x"}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                parsed(wire, **patch)
        # A run without an assessment stays readable; the session then asks in Auto.
        del wire["action"]["risk"]
        self.assertNotIn("risk", parsed(wire))
        self.assertEqual(json.loads(build_prompt([], {}, approval_mode="ask"))["approval_mode"], "ask")

    def test_question_hands_turn_to_user(self):
        from mapsuke.core.protocol import ACTIONS
        self.assertTrue({"question", "choices"} <= set(ACTIONS["ask"]["required"]))
        self.assertEqual(ACTIONS["ask"]["properties"]["choices"]["maxItems"], 5)
        wire = reply("ask", message="対象が2つあります", question="どちらのレイヤーを使いますか？",
                     choices=["道路（2021）", "道路（2024）"], path_request="", path_suggestion="")
        result = {"message": "対象が2つあります", "code": "", "title": "", "question": "どちらのレイヤーを使いますか？",
                  "choices": ["道路（2021）", "道路（2024）"], "path_request": "", "path_suggestion": ""}
        self.assertEqual(parsed(wire), result)
        self.assertEqual(parsed(wire, choices=[])["choices"], [])
        # Code is not a field of a question, so it cannot run without waiting for the answer.
        for patch in ({"code": "print(1)"}, {"question": "", "choices": ["A"]}, {"choices": "A"},
                      {"choices": [""]}, {"choices": [1]}, {"choices": list("ABCDEF")}, {"question": 1}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                parsed(wire, **patch)

    def test_only_the_models_own_slips_are_invalid_responses(self):
        from mapsuke.core.protocol import InvalidResponse
        run = reply("run", message="Downloaded", code="print(1)", risk="")
        for slip in (json.dumps({"structured_output": dict(run, action=dict(run["action"], suggestion="Save as a tool"))}),
                     json.dumps({"structured_output": dict(run, unexpected="x")}),
                     json.dumps({"structured_output": dict(run, action=dict(run["action"], kind="execute"))}),
                     json.dumps({"structured_output": dict(run, action="run")}),
                     # The flat reply of earlier versions is no longer the contract.
                     json.dumps({"structured_output": {"message": "Downloaded", "code": "print(1)"}}),
                     json.dumps({"subtype": "success", "result": "Plain text, not JSON"})):
            with self.subTest(slip=slip), self.assertRaises(InvalidResponse):
                parse_response(slip)
        # CLI failures are not the model's to correct, so they must still end the turn.
        for raw in (json.dumps({"is_error": True, "result": "Not logged in"}),
                    json.dumps({"subtype": "error_max_turns"}), json.dumps([])):
            with self.subTest(raw=raw), self.assertRaises(ValueError) as caught:
                parse_response(raw)
            self.assertNotIsInstance(caught.exception, InvalidResponse)

    def test_path_request_opens_a_picker_only_with_a_question(self):
        from mapsuke.core.protocol import ACTIONS
        self.assertTrue({"path_request", "path_suggestion"} <= set(ACTIONS["ask"]["required"]))
        wire = reply("ask", message="結果を保存します", question="保存先は？", choices=["/data/out.gpkg"],
                     path_request="file", path_suggestion="/data/out.gpkg")
        result = {"message": "結果を保存します", "code": "", "title": "", "question": "保存先は？", "choices": ["/data/out.gpkg"],
                  "path_request": "file", "path_suggestion": "/data/out.gpkg"}
        self.assertEqual(parsed(wire), result)
        for patch in ({"path_request": "save"}, {"path_request": "file", "question": "", "choices": []},
                      {"path_suggestion": None}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                parsed(wire, **patch)

    def test_suggestion_is_only_for_a_finished_turn(self):
        from mapsuke.core.protocol import ACTIONS
        self.assertEqual(ACTIONS["finish"]["required"], ["kind", "suggestion"])
        wire = reply("finish", message="完了しました", suggestion="ツールとして保存")
        result = {"message": "完了しました", "code": "", "title": "", "suggestion": "ツールとして保存"}
        self.assertEqual(parsed(wire), result)
        # Code and a question are fields of other actions, so they cannot accompany a suggestion.
        for patch in ({"code": "print(1)"}, {"question": "保存しますか？"}, {"suggestion": 1}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                parsed(wire, **patch)

    def test_invalid_output_never_becomes_code(self):
        for value in ('[]', 'not json', '{"result":"```python\\nprint(1)```"}',
                      '{"structured_output":{"message":"ok","code":"print(1)"}}',
                      '{"structured_output":{"message":"ok","title":"","action":{"kind":"run","code":123,"risk":""}}}',
                      '{"is_error":true,"result":"login required"}',
                      '{"subtype":"error_max_turns","structured_output":'
                      '{"message":"x","title":"","action":{"kind":"run","code":"x","risk":""}}}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_response(value)


class StreamTests(unittest.TestCase):
    def test_claude_context_uses_latest_request_input_including_cache(self):
        from mapsuke.core.protocol import StreamResponse
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
        from mapsuke.core.protocol import StreamResponse
        parser = StreamResponse()
        def event(inner):
            return (json.dumps({"type": "stream_event", "event": inner}, ensure_ascii=False) + "\n").encode()
        data = event({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "調査中"}})
        for byte in data:
            parser.feed(bytes([byte]))
        self.assertEqual(parser.preview["message"], "調査中")
        parser.feed(event({"type": "content_block_start", "index": 1,
                           "content_block": {"type": "tool_use", "name": "StructuredOutput"}}))
        payload = json.dumps(reply("run", message='確認しました。"code"', code="print('札幌')\n", risk=""))
        for char in payload:
            parser.feed(event({"type": "content_block_delta", "index": 1,
                               "delta": {"type": "input_json_delta", "partial_json": char}}))
        self.assertEqual(parser.preview, {"message": '確認しました。"code"', "code": "print('札幌')\n"})
        self.assertIsNone(parser.result)
        result = {"type": "result", "structured_output": json.loads(payload)}
        parser.feed(json.dumps(result).encode(), final=True)
        self.assertEqual(parser.result, result)

    def test_structured_restatement_of_text_reply_streams_once(self):
        from mapsuke.core.protocol import StreamResponse
        parser = StreamResponse()
        def event(inner):
            return (json.dumps({"type": "stream_event", "event": inner}, ensure_ascii=False) + "\n").encode()
        parser.feed(event({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "こんにちは。"}}))
        parser.feed(event({"type": "content_block_start", "index": 1,
                           "content_block": {"type": "tool_use", "name": "StructuredOutput"}}))
        seen = []
        for char in json.dumps(reply("finish", message="こんにちは。準備できました。", suggestion=""), ensure_ascii=False):
            seen.append(parser.feed(event({"type": "content_block_delta", "index": 1,
                                           "delta": {"type": "input_json_delta", "partial_json": char}}))["message"])
        self.assertTrue(all(len(b) >= len(a) for a, b in zip(seen, seen[1:])))
        self.assertEqual(seen[-1], "こんにちは。準備できました。")

    def test_title_does_not_block_or_leak_into_preview(self):
        from mapsuke.core.protocol import partial_strings
        for payload in ('{"title":"札幌", "message":"確認", "action":{"kind":"run", "code":"print(1)"',
                        '{"message":"確認", "title":"札幌", "action": {"kind": "run", "code": "print(1)", "risk": "上書き"}}'):
            self.assertEqual(partial_strings(payload), {"message": "確認", "code": "print(1)"})
        self.assertEqual(partial_strings('{"title":"途中'), {})

    def test_other_actions_do_not_leak_into_preview(self):
        from mapsuke.core.protocol import partial_strings
        for action in ('{"kind":"ask","question":"どれ？","choices":["code"]', '{"kind":"finish","suggestion":"code'):
            self.assertEqual(partial_strings('{"message":"確認","title":"","action":' + action), {"message": "確認"})

    def test_partial_escapes(self):
        from mapsuke.core.protocol import partial_strings
        self.assertEqual(partial_strings('{"message":"hello\\'), {"message": "hello"})
        self.assertEqual(partial_strings('{"message":"hello\\u30'), {"message": "hello"})
        self.assertEqual(partial_strings('{"message":"ok","title":"","action":{"kind":"run","code":"print(1)\\'),
                         {"message": "ok", "code": "print(1)"})


class CodexStreamTests(unittest.TestCase):
    def test_reasoning_summary_is_preview_only(self):
        from mapsuke.core.protocol import CodexStreamResponse
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
        payload = reply('finish', message='完了', suggestion='')
        stream.feed((json.dumps({'type': 'item.completed', 'item': {
            'type': 'agent_message', 'text': json.dumps(payload, ensure_ascii=False)}}) + '\n').encode())
        stream.feed(b'{"type":"turn.completed"}\n')
        self.assertEqual(stream.preview['reasoning'], '調査しました\n\n結果を確認しました')
        self.assertEqual(parse_response(json.dumps(stream.result)),
                         {'message': '完了', 'title': '', 'code': '', 'suggestion': ''})

    def test_codex_turn_input_is_marked_as_turn_total(self):
        from mapsuke.core.protocol import CodexStreamResponse
        stream = CodexStreamResponse()
        stream.feed(b'{"type":"turn.completed","usage":{"input_tokens":420,"output_tokens":19}}\n')
        self.assertEqual(stream.context_usage, {'tokens': 420, 'model': '', 'source': 'turn'})

    def test_fragmented_events_and_final_gate(self):
        from mapsuke.core.protocol import CodexStreamResponse
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
        payload = reply('run', message='札幌', code='print(1)', risk='')
        stream.feed((json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps(payload)}}) + '\n').encode())
        self.assertEqual(stream.preview['code'], 'print(1)')
        self.assertIsNone(stream.result)
        stream.feed(b'{"type":"turn.completed"}', final=True)
        self.assertEqual(parse_response(json.dumps(stream.result)),
                         {'message': '札幌', 'title': '', 'code': 'print(1)', 'risk': ''})

    def test_failure_and_malformed_final_never_execute(self):
        from mapsuke.core.protocol import CodexStreamResponse
        for events in [
            [{'type': 'turn.failed', 'error': {'message': 'authentication required'}}],
            [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'not JSON'}}, {'type': 'turn.completed'}],
        ]:
            stream = CodexStreamResponse()
            stream.feed(('\n'.join(json.dumps(e) for e in events) + '\n').encode())
            with self.assertRaises(ValueError):
                parse_response(json.dumps(stream.result))
