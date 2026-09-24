"""Integration test with real PyQGIS/Qt and a deterministic CLI stand-in."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QMainWindow

ROOT = Path(__file__).resolve().parents[1]

# macOS bundles place processing next to the installed qgis package.
import qgis
sys.path.insert(0, str(Path(qgis.__file__).resolve().parents[1] / "plugins"))
spec = importlib.util.spec_from_file_location("qgis_agent_test", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
app = QgsApplication([], False)
app.initQgis()
sys.path.insert(0, str(Path(QgsApplication.pkgDataPath()) / "python/plugins"))
app.setOrganizationName("QgisAgentTests")
app.setApplicationName("Smoke")
settings_dir = tempfile.TemporaryDirectory()
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, settings_dir.name)
from qgis_agent_test.plugin import QgisAgentPlugin


class Canvas:
    def refresh(self):
        pass


class Iface:
    def __init__(self):
        self.window = QMainWindow()
        self.actions = []

    def mainWindow(self):
        return self.window

    def activeLayer(self):
        return None

    def mapCanvas(self):
        return Canvas()

    def addPluginToMenu(self, menu, action):
        self.actions.append(action)

    def addToolBarIcon(self, action):
        pass

    def addDockWidget(self, area, dock):
        self.window.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        self.window.removeDockWidget(dock)

    def removePluginMenu(self, menu, action):
        self.actions.remove(action)

    def removeToolBarIcon(self, action):
        pass


def wait_until(predicate, seconds=15):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate(), "Timed out waiting for Qt"


iface = Iface()
plugin = QgisAgentPlugin(iface, Path(settings_dir.name) / "sessions.sqlite3")
plugin.initGui()
assert QgsApplication.processingRegistry().algorithmById('qgis_agent:add_tool') is not None
plugin.show()
dock = plugin.dock
# Empty sessions are reused; changing provider must also preserve an unsent draft.
empty_session = dock.session_id
empty_runtime = dock.runtime
empty_records = dock.store.list()
for _ in range(3):
    dock.new_chat()
assert dock.store.list() == empty_records
assert dock.session_id == empty_session and dock.runtime is empty_runtime
assert not dock.transcript.messages
for draft in ('', '未送信の下書き'):
    dock.input.setPlainText(draft)
    for provider in ('codex', 'claude', 'codex', 'claude'):
        dock.provider_selector.setCurrentIndex(dock.provider_selector.findData(provider))
        assert dock.session_id == empty_session and len(dock.store.list()) == 1
        assert dock.options['provider'] == provider
        assert dock.input.toPlainText() == draft
        assert dock.store.load(empty_session)['draft'] == draft
        assert dock.store.load(empty_session)['provider'] == provider
        assert dock.runtime is empty_runtime and not dock.transcript.messages
dock.input.clear()
# Approval gates exercise actual arbitrary Python execution in QGIS.
assert dock.options["approval_mode"] == "ask"
assert [dock.approval_selector.itemText(i) for i in range(3)] == ["Ask", "Auto", "Full auto"]
# Exercise the real consent dialog, including default No, dismissal, and mode-to-mode changes.
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QMessageBox

def choose_mode(mode, answer):
    def respond():
        dialog = app.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        assert dialog.defaultButton() == dialog.button(QMessageBox.No)
        assert "リスクを理解" in dialog.text()
        if answer is None:
            dialog.close()
        else:
            dialog.button(answer).click()
    QTimer.singleShot(0, respond)
    dock.approval_selector.setCurrentIndex(dock.approval_selector.findData(mode))

for mode, answer, expected in (
        ("auto", QMessageBox.No, "ask"), ("full_auto", None, "ask"),
        ("auto", QMessageBox.Yes, "auto"), ("full_auto", QMessageBox.No, "ask"),
        ("full_auto", QMessageBox.Yes, "full_auto"), ("auto", QMessageBox.Yes, "auto")):
    choose_mode(mode, answer)
    assert dock.options["approval_mode"] == expected
    assert dock.approval_selector.currentData() == expected
    assert QSettings().value("qgis-agent/approval_mode") == expected
    assert QSettings().value("qgis-agent/consented_approval_mode") == (expected if expected != "ask" else "")

original_warning = QMessageBox.warning
QMessageBox.warning = lambda *args: QMessageBox.Yes
for mode, assessment, should_run in (
        ("ask", False, False), ("auto", False, True), ("auto", True, False),
        ("auto", None, False), ("full_auto", True, True)):
    dock.new_chat()
    dock.approval_selector.setCurrentIndex(dock.approval_selector.findData(mode))
    assert QSettings().value("qgis-agent/approval_mode") == mode
    dock.runtime.namespace.pop("approval_marker", None)
    dock.set_busy(True)
    assert not dock.approval_selector.isEnabled()
    response = {"message": "提案", "code": "approval_marker = 1", "title": "承認テスト"}
    if assessment is not None:
        response.update(requires_approval=assessment, approval_reason="既存データを変更します" if assessment else "")
    dock.on_response(response)
    assert ("approval_marker" in dock.runtime.namespace) == should_run
    if not should_run:
        assert dock.pending_code and dock.run.isEnabled()
        if assessment:
            assert "既存データを変更します" in dock.transcript.toPlainText()
        if mode == "ask":
            dock.run.click()
            assert dock.runtime.namespace["approval_marker"] == 1
    dock.cancel()
    assert dock.pending_code is None and dock.approval_selector.isEnabled()
dock.new_chat()
dock.approval_selector.setCurrentIndex(dock.approval_selector.findData("full_auto"))
QMessageBox.warning = original_warning

with tempfile.TemporaryDirectory() as directory:
    fake = Path(directory) / "claude"
    fake.write_text('''#!/usr/bin/env python3
import json, sys
p = json.load(sys.stdin)
if not any(x["role"] == "bridge" for x in p["conversation"]):
    code = "from qgis.core import QgsVectorLayer\\nlayer = QgsVectorLayer('Point?crs=EPSG:4326', 'Smoke layer', 'memory')\\nproject.addMapLayer(layer)\\nprint(layer.isValid())"
else:
    assert p["conversation"][-1]["content"]["ok"]
    assert p["qgis_context"]["layers"][0]["name"] == "Smoke layer"
    code = ""
print(json.dumps({"subtype":"success", "structured_output":{"message":"Done", "code":code, "title":"レイヤーの作成" if p["generate_title"] else "変更しないタイトル"}}))
''')
    fake.chmod(0o755)
    dock.options["executable"] = str(fake)
    dock.input.setPlainText("Create a layer")
    dock.submit()
    wait_until(lambda: not dock.running)
    assert len(QgsProject.instance().mapLayers()) == 1, dock.transcript.toPlainText()
    assert len(dock.history) == 4, dock.history
    assert dock.session_title == 'レイヤーの作成'
    assert dock.sessions.currentText() == '[Claude] レイヤーの作成'
    assert dock.store.load(dock.session_id)['title'] == 'レイヤーの作成'
    titled_session = dock.session_id
    assert dock.load_session(titled_session)
    assert dock.session_title == 'レイヤーの作成'
    assert dock.sessions.currentText() == '[Claude] レイヤーの作成' 
    assert dock.history[2]["content"]["output"] == "True\n"
    result = dock.runtime.execute("x = 42\nprint('before failure')\nraise RuntimeError('expected')")
    assert not result["ok"] and "expected" in result["error"]
    assert result["output"] == "before failure\n"
    assert dock.runtime.execute("print(x)")["output"] == "42\n"
    assert not dock.runtime.execute("raise SystemExit(1)")["ok"]
    assert len(dock.runtime.execute("print('x' * 50000)")["output"]) == 20000
    dock.new_chat()
    assert not dock.session_title
    empty_session = dock.session_id
    empty_records = dock.store.list()
    dock.new_chat()
    assert dock.session_id == empty_session and dock.store.list() == empty_records
    dock.options["approval_mode"] = "ask"
    dock.input.setPlainText("Preview only")
    dock.submit()
    wait_until(lambda: dock.pending_code is not None)
    assert len(QgsProject.instance().mapLayers()) == 1, dock.transcript.toPlainText()
    dock.cancel()
    assert not dock.running and dock.pending_code is None
    dock.new_chat()
    dock.options["executable"] = "/nonexistent/claude"
    dock.input.setPlainText("Fail to start")
    dock.submit()
    wait_until(lambda: not dock.running)
    assert "起動できません" in dock.transcript.toPlainText()
    fake.write_text('#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps({"is_error":True,"result":"Not logged in"}))\nsys.exit(1)\n')
    dock.options["executable"] = str(fake)
    dock.input.setPlainText("Auth failure")
    dock.submit()
    wait_until(lambda: not dock.running)
    assert "Not logged in" in dock.transcript.toPlainText()
    assert dock.history[-1]["content"] == "Interaction stopped: Not logged in"
    fake.write_text("#!/bin/sh\nsleep 30\n")
    dock.options["executable"] = str(fake)
    dock.input.setPlainText("Cancel")
    dock.submit()
    wait_until(lambda: dock.agent.process is not None and dock.agent.process.processId() != 0)
    dock.cancel()
    assert dock.agent.process is None and not dock.running
# Stream updates must appear before process exit and must not execute partial code.
with tempfile.TemporaryDirectory() as directory:
    fake = Path(directory) / "stream-claude"
    fake.write_text("#!/usr/bin/env python3\n" + """
import json, sys, time
json.load(sys.stdin)
assert '--include-partial-messages' in sys.argv
assert 'stream-json' in sys.argv
def emit(event):
    print(json.dumps({'type': 'stream_event', 'event': event}), flush=True)
emit({'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': 'ストリーム表示'}})
time.sleep(0.8)
print(json.dumps({'type': 'result', 'structured_output': {'message': 'ストリーム表示 完了', 'code': ''}}), flush=True)
""")
    fake.chmod(0o755)
    dock.new_chat()
    dock.options["executable"] = str(fake)
    dock.input.setPlainText("Streaming test")
    dock.submit()
    wait_until(lambda: "ストリーム表示" in dock.transcript.toPlainText())
    assert dock.running and dock.history[-1]["role"] == "user"
    wait_until(lambda: not dock.running)
    assert dock.transcript.toPlainText().count("ストリーム表示") == 1
    assert dock.transcript.messages[-1].message.text() == "ストリーム表示 完了"

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QInputMethodEvent
from qgis.PyQt.QtTest import QTest
from qgis_agent_test.chat_ui import ChatInput, SettingsDialog
from qgis_agent_test.chat_ui import ChatTranscript

# Markdown must not force the transcript wider, including after resize/update.
transcript = ChatTranscript()
transcript.resize(700, 600)
transcript.show()
long_messages = [
    "# 結果\n\n" + "長い日本語の文章です。" * 40,
    "https://example.com/" + "abcdef" * 100,
    "```python\n" + "some_variable = " * 50 + "\n```",
    "|" + "|".join(["column"] * 15) + "|\n|" + "|".join(["---"] * 15)
    + "|\n|" + "|".join(["value"] * 15) + "|",
]
for text in long_messages:
    transcript.add_message("Codex", text)
for width in (700, 320, 480):
    transcript.resize(width, 600)
    for bubble, text in zip(transcript.messages, long_messages):
        bubble.update_content(text + "\n\n完了")
    for _ in range(20):
        app.processEvents()
    assert transcript.content.width() <= transcript.viewport().width()
    for bubble, text in zip(transcript.messages, long_messages):
        assert bubble.message.text() == text + "\n\n完了"
        assert bubble.message.verticalScrollBar().maximum() == 0
transcript.close()

editor = ChatInput()
submissions = []
editor.submitted.connect(lambda: submissions.append(editor.toPlainText()))
editor.setPlainText("test")
QTest.keyClick(editor, Qt.Key_Return, Qt.ShiftModifier)
assert "\n" in editor.toPlainText() and not submissions
QTest.keyClick(editor, Qt.Key_Return)
assert len(submissions) == 1
editor.inputMethodEvent(QInputMethodEvent("変換中", []))
QTest.keyClick(editor, Qt.Key_Return)
assert len(submissions) == 1
editor.inputMethodEvent(QInputMethodEvent())
dialog = SettingsDialog(dock.options)
dialog.executable.setText("/tmp/cancelled")
dialog.reject()
assert dock.options["executable"] != "/tmp/cancelled"
def accept_settings():
    dialog = app.activeModalWidget()
    dialog.executable.setText("/tmp/saved-claude")
    assert not hasattr(dialog, "model")
    dialog.accept()
dock.model_selector.setCurrentIndex(dock.model_selector.findData("claude-sonnet-5"))
assert not dock.model_selector.isEditable()
QTimer.singleShot(0, accept_settings)
dock.open_settings()
assert {key: dock.options[key] for key in ("executable", "approval_mode", "model", "enable_skills", "enable_connectors")} == {"executable": "/tmp/saved-claude", "approval_mode": "ask", "model": "claude-sonnet-5", "enable_skills": False, "enable_connectors": False}
assert QSettings().value("qgis-agent/executable") == "/tmp/saved-claude"

# Inventory tabs are read-only; connection checks are asynchronous and redact URLs.
with tempfile.TemporaryDirectory() as directory:
    cli = Path(directory) / "inventory-claude"
    cli.write_text("#!/usr/bin/env python3\nimport sys\nassert sys.argv[1:] == ['mcp', 'list']\nprint('test-cloud: https://SECRET - ✓ Connected')\n")
    cli.chmod(0o755)
    inventory_dialog = SettingsDialog({"executable": str(cli), "auto_execute": True})
    inventory_dialog.capabilities.check_connections()
    wait_until(lambda: inventory_dialog.capabilities.process is None)
    rows = inventory_dialog.capabilities.connectors
    assert any(row["name"] == "test-cloud" and row["status"] == "接続済み" for row in rows)
    assert "SECRET" not in str(rows)
    inventory_dialog.executable.setText("/missing/claude")
    inventory_dialog.capabilities.check_connections()
    wait_until(lambda: inventory_dialog.capabilities.process is None)
    assert "起動できません" in inventory_dialog.capabilities.connector_status.text()
    inventory_dialog.reject()

# Settings navigation is independent of the conversation, and edits remain staged until OK.
from unittest.mock import patch
inventory = {'skills': [{'id': '/tmp/example/SKILL.md', 'name': 'Example', 'description': 'Test', 'enabled': True}],
             'connectors': [{'id': 'test_server', 'name': 'test_server', 'description': 'MCP', 'enabled': True}],
             'warnings': []}
with patch('qgis_agent_test.capabilities.read_codex_inventory', return_value=inventory):
    before = dict(dock.options)
    settings_dialog = SettingsDialog(dock.options)
    settings_dialog.provider_tabs.setCurrentWidget(settings_dialog.provider_pages["codex"])
    settings_dialog.codex_capabilities.controls[('connectors', 'test_server')].setCurrentIndex(2)
    settings_dialog.codex_capabilities.controls[('skills', '/tmp/example/SKILL.md')].setCurrentIndex(1)
    choices = settings_dialog.options()['codex_capabilities']
    assert choices == {'skills': {'/tmp/example/SKILL.md': True}, 'connectors': {'test_server': False}}
    settings_dialog.provider_tabs.setCurrentWidget(settings_dialog.provider_pages["claude"])
    assert settings_dialog.options()['codex_capabilities'] == choices
    settings_dialog.reject()
    assert dock.options == before

# The configured model reaches the CLI, including the default (no override).
with tempfile.TemporaryDirectory() as directory:
    cli = Path(directory) / "model-claude"
    cli.write_text("#!/usr/bin/env python3\n" + """
import sys, json
p = json.load(sys.stdin)
expected = p['conversation'][-1]['content']
if expected == 'default':
    assert '--model' not in sys.argv
else:
    assert sys.argv[sys.argv.index('--model') + 1] == expected
print(json.dumps({'type': 'result', 'structured_output': {'message': 'Model OK', 'code': ''}}))
""")
    cli.chmod(0o755)
    for model in ('claude-sonnet-5', 'claude-opus-5', 'claude-haiku-4-5-20251001', ''):
        dock.new_chat()
        dock.options['executable'] = str(cli)
        dock.model_selector.setCurrentIndex(dock.model_selector.findData(model))
        dock.input.setPlainText(model or 'default')
        dock.submit()
        wait_until(lambda: not dock.running)
        assert dock.history[-1]['content']['message'] == 'Model OK'

# Switching/restoring never replays Python or restores live QGIS objects.
dock.new_chat()
dock.options['model'] = 'claude-opus-5'
dock.history = [{'role': 'user', 'content': '保存テスト'},
                {'role': 'assistant', 'content': {'message': '以前のコード', 'code': "raise AssertionError('must not replay')"}}]
dock.log('あなた', '保存テスト')
dock.log('Claude', '以前のコード').update_content('以前のコード', "raise AssertionError('must not replay')")
dock.runtime.execute('transient = 123')
dock.input.setPlainText('下書き')
assert dock.save_session()
first_session = dock.session_id
layer_count = len(QgsProject.instance().mapLayers())
dock.new_chat()
second_session = dock.session_id
assert first_session != second_session and not dock.history
assert dock.load_session(first_session)
assert dock.options['model'] == 'claude-opus-5'
assert dock.input.toPlainText() == '下書き'
assert 'transient' not in dock.runtime.namespace
assert dock.pending_code is None and not dock.running
assert len(QgsProject.instance().mapLayers()) == layer_count
assert '以前のコード' in dock.transcript.toPlainText()
assert 'Python変数はリセット' in dock.history[-1]['content']
# An interrupted execution is reported rather than retried on startup.
payload = dock.store.load(first_session)
payload['interrupted'] = True
dock.store.save(first_session, '保存テスト', payload)
assert dock.load_session(first_session)
assert '途中で終了' in dock.transcript.toPlainText()
# Actual dock destruction and recreation restores the last selected session.
plugin.unload()
plugin.show()
dock = plugin.dock
assert dock.session_id == first_session and dock.options['model'] == 'claude-opus-5'
assert dock.model_selector.currentData() == 'claude-opus-5'
assert dock.input.toPlainText() == '下書き'
from qgis.PyQt.QtWidgets import QMessageBox
original_question = QMessageBox.question
QMessageBox.question = lambda *args: QMessageBox.No
dock.delete_session()
assert dock.session_id == first_session
QMessageBox.question = lambda *args: QMessageBox.Yes
try:
    dock.delete_session()
    assert all(row[0] != first_session for row in dock.store.list())
    assert len(QgsProject.instance().mapLayers()) == layer_count
    for session_id, _, _ in dock.store.list():
        if session_id != dock.session_id:
            dock.store.delete(session_id)
    dock.delete_session()
    assert len(dock.store.list()) == 1 and dock.history == []
finally:
    QMessageBox.question = original_question
# Restore the menu lifecycle after re-opening the dock without initGui.
plugin.initGui()

# Native sessions persist across turns, switching, and a new dock process lifecycle.
with tempfile.TemporaryDirectory() as directory:
    cli = Path(directory) / 'native-claude'
    call_log = Path(directory) / 'calls.jsonl'
    cli.write_text("#!/usr/bin/env python3\n" + r"""
import json, sys
from pathlib import Path
p = json.load(sys.stdin)
mode = '--resume' if '--resume' in sys.argv else '--session-id'
sid = sys.argv[sys.argv.index(mode) + 1]
assert '--no-session-persistence' not in sys.argv
with Path(__file__).with_name('calls.jsonl').open('a') as f:
    f.write(json.dumps({'mode': mode, 'id': sid, 'prompt': p, 'cwd': str(Path.cwd())}) + '\n')
print(json.dumps({'type': 'system', 'subtype': 'init', 'session_id': sid}), flush=True)
print(json.dumps({'type': 'result', 'session_id': sid,
                  'structured_output': {'message': 'Native OK', 'code': ''}}), flush=True)
""")
    cli.chmod(0o755)
    dock.new_chat()
    first = dock.session_id
    dock.options['executable'] = str(cli)
    for text in ['first', 'second']:
        dock.input.setPlainText(text)
        dock.submit()
        wait_until(lambda: not dock.running)
    calls = [json.loads(line) for line in call_log.read_text().splitlines()]
    assert [call['mode'] for call in calls] == ['--session-id', '--resume']
    assert all(call['id'] == first for call in calls)
    assert calls[-1]['prompt']['conversation'] == [{'role': 'user', 'content': 'second'}]
    dock.new_chat()
    second = dock.session_id
    dock.options['executable'] = str(cli)
    dock.input.setPlainText('other')
    dock.submit()
    wait_until(lambda: not dock.running)
    dock.sessions.setCurrentIndex(dock.sessions.findData(first))
    assert dock.session_id == first and dock.agent_started
    plugin.unload()
    plugin.show()
    dock = plugin.dock
    assert dock.session_id == first and dock.agent_started
    dock.options['executable'] = str(cli)
    dock.input.setPlainText('third')
    dock.submit()
    wait_until(lambda: not dock.running)
    calls = [json.loads(line) for line in call_log.read_text().splitlines()]
    assert calls[-2]['id'] == second and calls[-2]['mode'] == '--session-id'
    assert calls[-1]['id'] == first and calls[-1]['mode'] == '--resume'
    assert len({call['cwd'] for call in calls}) == 1
    assert all(entry['content'] not in ('first', 'second') for entry in calls[-1]['prompt']['conversation'])
    # Missing native history must remain an error, never silently create a new session.
    cli.write_text("#!/usr/bin/env python3\nimport sys\nassert '--resume' in sys.argv\nprint('No conversation found', file=sys.stderr)\nsys.exit(1)\n")
    dock.input.setPlainText('missing history')
    dock.submit()
    wait_until(lambda: not dock.running)
    assert dock.session_id == first and dock.agent_started
    assert 'No conversation found' in dock.transcript.toPlainText()
    assert not hasattr(dock, 'save_button')
    dock.input.setPlainText('自動保存される下書き')
    wait_until(lambda: dock.store.load(first)['draft'] == '自動保存される下書き')
    plugin.initGui()

# Capability switches change real CLI flags, including when resuming a session.
with tempfile.TemporaryDirectory() as directory:
    cli = Path(directory) / 'capability-claude'
    cli.write_text("#!/usr/bin/env python3\n" + r"""
import json, sys
p = json.load(sys.stdin)
skills, connectors = json.loads(p['conversation'][-1]['content'])
instructions = sys.argv[sys.argv.index('--system-prompt') + 1]
assert 'name: qgis-create-report' in instructions
assert 'name: qgis-save-processing-script' in instructions
assert ('--disable-slash-commands' not in sys.argv) == skills
assert ('--strict-mcp-config' not in sys.argv) == connectors
assert ('--mcp-config' not in sys.argv) == connectors
assert sys.argv[sys.argv.index('--tools') + 1] == ('default' if skills or connectors else '')
assert '--dangerously-skip-permissions' not in sys.argv
if skills or connectors:
    assert sys.argv[sys.argv.index('--permission-mode') + 1] == 'dontAsk'
    assert 'You cannot run tools yourself' not in sys.argv[sys.argv.index('--system-prompt') + 1]
if skills:
    assert sys.argv[sys.argv.index('--allowedTools') + 1] == 'Skill'
mode = '--resume' if '--resume' in sys.argv else '--session-id'
sid = sys.argv[sys.argv.index(mode) + 1]
print(json.dumps({'type': 'result', 'session_id': sid,
                  'structured_output': {'message': 'Capabilities OK', 'code': ''}}))
""")
    cli.chmod(0o755)
    dock.new_chat()
    dock.options['executable'] = str(cli)
    for skills, connectors in [(False, False), (True, False), (False, True), (True, True)]:
        dialog = SettingsDialog(dock.options)
        dialog.capabilities.toggles['enable_skills'].setChecked(skills)
        dialog.capabilities.toggles['enable_connectors'].setChecked(connectors)
        options = dialog.options()
        assert options['enable_skills'] == skills and options['enable_connectors'] == connectors
        dialog.accept()
        dock.options.update(options)
        dock.input.setPlainText(json.dumps([skills, connectors]))
        dock.submit()
        wait_until(lambda: not dock.running)
        assert dock.history[-1]['content']['message'] == 'Capabilities OK', dock.transcript.toPlainText()
    enabled_session = dock.session_id
    assert dock.store.load(enabled_session)['enable_skills']
    assert dock.store.load(enabled_session)['enable_connectors']
    dock.new_chat()
    assert not dock.options['enable_skills'] and not dock.options['enable_connectors']
    dock.load_session(enabled_session)
    assert dock.options['enable_skills'] and dock.options['enable_connectors']
    dialog = SettingsDialog(dock.options)
    dialog.capabilities.toggles['enable_skills'].setChecked(False)
    dialog.reject()
    assert dock.options['enable_skills']

# Codex emits its own native ID, then resumes it for execution feedback and new turns.
with tempfile.TemporaryDirectory() as directory:
    cli = Path(directory) / 'codex'
    cli.write_text("#!/usr/bin/env python3\n" + r"""
import json, sys, time
from pathlib import Path
p = json.load(sys.stdin)
assert sys.argv[1] == 'exec'
assert '--json' in sys.argv and '--output-schema' in sys.argv
assert 'sandbox_mode="read-only"' in sys.argv
assert 'forced_login_method="chatgpt"' in sys.argv
instructions = json.loads(next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('developer_instructions=')))
assert 'name: qgis-create-report' in instructions
assert 'name: qgis-save-processing-script' in instructions
assert 'mcp_servers.test_server.enabled=false' in sys.argv
assert '--dangerously-bypass-approvals-and-sandbox' not in sys.argv
assert json.loads(Path(sys.argv[sys.argv.index('--output-schema') + 1]).read_text())['required'] == ['message', 'code', 'title', 'requires_approval', 'approval_reason']
resumed = sys.argv[2] == 'resume'
sid = '0199a213-81c0-7800-8aa1-bbab2a035a53'
if resumed:
    assert sys.argv[-2] == sid
with Path(__file__).with_name('calls.jsonl').open('a') as f:
    f.write(json.dumps({'resume': resumed, 'prompt': p}) + '\n')
print(json.dumps({'type': 'thread.started', 'thread_id': sid}), flush=True)
print(json.dumps({'type': 'item.updated', 'item': {'type': 'agent_message', 'text': 'Codexで処理中'}}), flush=True)
time.sleep(0.1)
code = '' if resumed else "from qgis.core import QgsVectorLayer\nproject.addMapLayer(QgsVectorLayer('Point?crs=EPSG:4326', 'Codex smoke', 'memory'))\nprint('created')"
print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps({'message': 'Codex OK', 'code': code, 'title': 'Codexでレイヤー作成' if p['generate_title'] else '変更しないタイトル'})}}), flush=True)
print(json.dumps({'type': 'turn.completed'}), flush=True)
""")
    cli.chmod(0o755)
    claude_session = dock.session_id
    dock.provider_selector.setCurrentIndex(dock.provider_selector.findData('codex'))
    codex_session = dock.session_id
    assert codex_session != claude_session and dock.options['provider'] == 'codex'
    assert dock.model_selector.findData('gpt-6-astra') >= 0
    assert dock.model_selector.findData('claude-opus-5') < 0
    dock.options['codex_capabilities'] = {'connectors': {'test_server': False}}
    dock.options['codex_executable'] = str(cli)
    dock.options["approval_mode"] = "full_auto"
    count = len(QgsProject.instance().mapLayers())
    dock.input.setPlainText('Create a layer with Codex')
    dock.submit()
    wait_until(lambda: not dock.running)
    assert len(QgsProject.instance().mapLayers()) == count + 1, dock.transcript.toPlainText()
    assert dock.native_session_id == '0199a213-81c0-7800-8aa1-bbab2a035a53'
    assert dock.session_title == 'Codexでレイヤー作成'
    assert dock.sessions.currentText() == '[Codex] Codexでレイヤー作成'
    native_id = dock.native_session_id
    assert dock.history[-1]['content']['message'] == 'Codex OK'
    calls = [json.loads(line) for line in cli.with_name('calls.jsonl').read_text().splitlines()]
    assert [call['resume'] for call in calls] == [False, True]
    assert calls[-1]['prompt']['conversation'][-1]['content']['output'] == 'created\n'
    dialog = SettingsDialog(dock.options)
    assert dialog.capabilities is not None
    assert [dialog.provider_tabs.tabText(i) for i in range(2)] == ['Codex', 'Claude']
    for page in dialog.provider_pages.values():
        assert [page.tabText(i) for i in range(3)] == ['一般', 'スキル', 'コネクタ']
    assert dialog.provider_tabs.currentIndex() == 0
    dialog.provider_tabs.setCurrentWidget(dialog.provider_pages["claude"])
    assert dock.options['provider'] == 'codex' and dock.session_id == codex_session
    assert dialog.codex_executable.text() == str(cli)
    dialog.reject()
    dock.sessions.setCurrentIndex(dock.sessions.findData(claude_session))
    assert dock.options['provider'] == 'claude'
    assert dock.model_selector.findData('gpt-6-astra') < 0
    dock.sessions.setCurrentIndex(dock.sessions.findData(codex_session))
    plugin.unload()
    plugin.show()
    dock = plugin.dock
    assert dock.options['provider'] == 'codex' and dock.native_session_id == native_id
    assert dock.options['codex_capabilities'] == {'connectors': {'test_server': False}}
    dock.options['codex_executable'] = str(cli)
    dock.input.setPlainText('Continue Codex')
    dock.submit()
    wait_until(lambda: not dock.running)
    calls = [json.loads(line) for line in cli.with_name('calls.jsonl').read_text().splitlines()]
    assert calls[-1]['resume']
    assert not calls[-1]['prompt']['generate_title']
    assert dock.session_title == 'Codexでレイヤー作成'
    assert len(QgsProject.instance().mapLayers()) == count + 1
    plugin.initGui()
    # Failed startup and malformed final response must leave QGIS untouched.
    dock.options['codex_executable'] = '/missing/codex'
    dock.input.setPlainText('Failed startup')
    dock.submit()
    wait_until(lambda: not dock.running)
    assert 'Codexを起動できません' in dock.transcript.toPlainText()
    dock.provider_selector.setCurrentIndex(dock.provider_selector.findData('claude'))

if "--inventory-screenshot" in sys.argv:
    from qgis.PyQt.QtWidgets import QTabWidget
    inventory_dialog = SettingsDialog(dock.options)
    inventory_dialog.show()
    inventory_dialog.provider_tabs.setCurrentWidget(inventory_dialog.provider_pages["claude"])
    inventory_dialog.provider_pages["claude"].setCurrentIndex(1)
    app.processEvents()
    inventory_dialog.grab().save("/tmp/qgis-agent-skills.png")
    inventory_dialog.provider_pages["claude"].setCurrentIndex(2)
    app.processEvents()
    inventory_dialog.grab().save("/tmp/qgis-agent-connectors.png")
    inventory_dialog.provider_tabs.setCurrentWidget(inventory_dialog.provider_pages["codex"])
    inventory_dialog.provider_pages["codex"].setCurrentIndex(1)
    app.processEvents()
    inventory_dialog.grab().save("/tmp/qgis-agent-codex-skills.png")
    inventory_dialog.reject()

if "--screenshot" in sys.argv or "--codex-screenshot" in sys.argv:
    dock.new_chat()
    if "--codex-screenshot" in sys.argv:
        dock.provider_selector.setCurrentIndex(dock.provider_selector.findData("codex"))
        dock.model_selector.setCurrentIndex(dock.model_selector.findData("gpt-6-astra"))
    dock.log("あなた", "札幌の点を地図に追加してください。")
    bubble = dock.log(dock.agent_label, "札幌の位置にポイントを追加します。メモリレイヤーを作成し、地図の表示範囲を合わせます。")
    bubble.update_content(bubble.message.text(), "from qgis.core import QgsVectorLayer\nlayer = QgsVectorLayer('Point?crs=EPSG:4326', '札幌', 'memory')")
    dock.log("QGIS · 実行成功", "ポイントを1件追加しました。")
    dock.log(dock.agent_label, "札幌のポイントを追加しました。次にどのような分析を行いますか？")
    iface.window.resize(540, 780)
    iface.window.show()
    app.processEvents()
    iface.window.grab().save("/tmp/qgis-agent-chat.png")

if "--live" in sys.argv or "--live-codex" in sys.argv:
    from qgis_agent_test.agent import default_executable, default_codex_executable
    QgsProject.instance().clear()
    dock.new_chat()
    dock.options["approval_mode"] = "full_auto"
    dock.options["executable"] = default_executable()
    if "--live-codex" in sys.argv:
        dock.provider_selector.setCurrentIndex(dock.provider_selector.findData("codex"))
        dock.options["codex_executable"] = default_codex_executable()
        dock.options["model"] = ""
    dock.input.setPlainText("動作検証です。EPSG:4326のメモリポイントレイヤーを1つ作り、名前をAgent live smokeにして、札幌(141.3545, 43.0618)の点を1つ追加してください。ファイルは保存せず、他の操作は不要です。実行結果を確認したら短く完了してください。")
    dock.submit()
    wait_until(lambda: not dock.running, 300)
    print(dock.transcript.toPlainText(), flush=True)
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1 and layers[0].name() == "Agent live smoke"
    assert layers[0].featureCount() == 1
    point = next(layers[0].getFeatures()).geometry().asPoint()
    assert abs(point.x() - 141.3545) < 1e-6 and abs(point.y() - 43.0618) < 1e-6
    assert dock.history[-1]["role"] == "assistant" and not dock.history[-1]["content"]["code"]
    print("PASS: live " + dock.agent_label + " subscription -> generated Python -> QGIS point -> final response", flush=True)
plugin.unload()
assert not iface.actions
assert QgsApplication.processingRegistry().algorithmById('qgis_agent:add_tool') is None
QgsProject.instance().clear()
print("PASS: plugin lifecycle, CLI round-trip, live QGIS layer, feedback, errors, persistence, output limit, preview, failed start, cancellation")
# Avoid macOS QGIS teardown ordering issues at interpreter shutdown.
os._exit(0)
