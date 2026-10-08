"""Integration test with real PyQGIS/Qt and a deterministic CLI stand-in."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Keep bundled skill installation out of the real CLI folders.
cli_homes = tempfile.TemporaryDirectory()
os.environ["CLAUDE_CONFIG_DIR"] = str(Path(cli_homes.name) / "claude")
os.environ["CODEX_HOME"] = str(Path(cli_homes.name) / "codex")
(Path(cli_homes.name) / "claude").mkdir()
from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QLabel, QMainWindow, QMessageBox
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

# macOS bundles place processing next to the installed qgis package.
import qgis
sys.path.insert(0, str(Path(qgis.__file__).resolve().parents[1] / "plugins"))
spec = importlib.util.spec_from_file_location("geotaro_test", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
app = QgsApplication([], False)
app.initQgis()
sys.path.insert(0, str(Path(QgsApplication.pkgDataPath()) / "python/plugins"))
app.setOrganizationName("GeotaroTests")
app.setApplicationName("Smoke")
settings_dir = tempfile.TemporaryDirectory()
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, settings_dir.name)
# Existing assertions below exercise the Japanese UI.
QSettings().setValue("locale/overrideFlag", True)
QSettings().setValue("locale/userLocale", "ja_JP")
from geotaro_test.i18n import tr
from geotaro_test.plugin import GeotaroPlugin
from geotaro_test.core.session import default_effort


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

    def addTabifiedDockWidget(self, area, dock, tabify_with, raise_tab):
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
plugin = GeotaroPlugin(iface, Path(settings_dir.name) / "sessions.sqlite3")
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as first_prompt:
    plugin.initGui()
assert first_prompt.call_count == 1
assert QSettings().value("geotaro/bundled_skills_prompted", False, type=bool)
bundled = sorted(path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md"))
assert sorted(path.name for path in (Path(cli_homes.name) / "claude/skills").iterdir()) == bundled
assert not (Path(cli_homes.name) / "codex").exists()
assert QgsApplication.processingRegistry().algorithmById('geotaro:add_tool') is not None
dock = plugin.dock
assert dock is not None and not dock.isHidden()
# Dock hide events need a visible main window, which would disturb the layout checks below.
visible_iface = Iface()
visible_iface.window.show()
visible_plugin = GeotaroPlugin(visible_iface, Path(settings_dir.name) / "visible.sqlite3")
visible_plugin.initGui()
visible_plugin.dock.close()
assert QSettings().value("geotaro/dock_open", type=bool) is False
visible_plugin.unload()
visible_plugin.initGui()
assert visible_plugin.dock is None
visible_plugin.show()
assert QSettings().value("geotaro/dock_open", type=bool) is True
visible_plugin.unload()
assert QSettings().value("geotaro/dock_open", type=bool) is True
visible_iface.window.close()
assert default_effort("claude", "claude-opus-5-5") == "medium"
assert default_effort("claude", "claude-sonnet-5") == "high"
assert default_effort("codex", "gpt-6-astra") == "medium"
assert dock.effort_selector.findData("") == -1
assert dock.effort_selector.currentData() == "high"
assert dock.wait_indicator.isHidden() and not dock.wait_timer.isActive()
dock.show_wait_indicator(True)
first_frame = dock.wait_indicator.text()
dock.advance_wait_indicator()
assert dock.wait_indicator.text() != first_frame and dock.wait_timer.isActive()
dock.show_wait_indicator(False)
assert dock.wait_indicator.isHidden() and not dock.wait_timer.isActive()
# The new-session menu selects the provider. An untouched session can be reused.
empty_session = dock.session.session_id
empty_runtime = dock.session.runtime
empty_records = dock.session.store.list()
for _ in range(3):
    dock.session.new_chat()
assert dock.session.store.list() == empty_records
assert dock.session.session_id == empty_session and dock.session.runtime is empty_runtime
assert not dock.transcript.messages
assert [action.text() for action in dock.reset.menu().actions()] == ['Claude', 'Codex']
for provider, action in (('codex', dock.reset.menu().actions()[1]),
                         ('claude', dock.reset.menu().actions()[0])):
    action.trigger()
    assert dock.session.session_id == empty_session and len(dock.session.store.list()) == 1
    assert dock.session.options['provider'] == provider
    assert dock.effort_selector.currentData() == ("medium" if provider == "codex" else "high")
    assert dock.session.store.load(empty_session)['provider'] == provider
    assert dock.session.runtime is empty_runtime and not dock.transcript.messages
dock.input.setPlainText('未送信の下書き')
dock.reset.menu().actions()[1].trigger()
assert dock.session.session_id != empty_session and dock.session.options['provider'] == 'codex'
assert dock.session.store.load(empty_session)['draft'] == '未送信の下書き'
assert dock.input.toPlainText() == ''
dock.reset.menu().actions()[0].trigger()
dock.input.clear()
# Approval gates exercise actual arbitrary Python execution in QGIS.
assert dock.session.options["approval_mode"] == "ask"
assert [dock.approval_selector.itemText(i) for i in range(3)] == ["Ask", "Auto", "Full auto"]
# Exercise the real consent dialog, including default No, dismissal, and mode-to-mode changes.
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QMessageBox

def choose_mode(mode, answer):
    def respond():
        dialog = app.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        assert dialog.defaultButton() == dialog.button(QMessageBox.StandardButton.No)
        assert "リスクを理解" in dialog.text()
        if answer is None:
            dialog.close()
        else:
            dialog.button(answer).click()
    QTimer.singleShot(0, respond)
    dock.approval_selector.setCurrentIndex(dock.approval_selector.findData(mode))

for mode, answer, expected in (
        ("auto", QMessageBox.StandardButton.No, "ask"), ("full_auto", None, "ask"),
        ("auto", QMessageBox.StandardButton.Yes, "auto"), ("full_auto", QMessageBox.StandardButton.No, "ask"),
        ("full_auto", QMessageBox.StandardButton.Yes, "full_auto"), ("auto", QMessageBox.StandardButton.Yes, "auto")):
    choose_mode(mode, answer)
    assert dock.session.options["approval_mode"] == expected
    assert dock.approval_selector.currentData() == expected
    assert QSettings().value("geotaro/approval_mode") == expected
    assert QSettings().value("geotaro/consented_approval_mode") == (expected if expected != "ask" else "")

def approval_marker_ran():
    return any(isinstance(entry["content"], dict) and entry["content"].get("output") == "approval_marker\n"
               for entry in dock.session.history if entry["role"] == "bridge")


original_warning = QMessageBox.warning
QMessageBox.warning = lambda *args: QMessageBox.StandardButton.Yes
attention = []
dock.session.attention_needed.connect(attention.append)
for mode, assessment, should_run in (
        ("ask", False, False), ("auto", False, True), ("auto", True, False),
        ("auto", None, False), ("full_auto", True, True)):
    dock.session.new_chat()
    dock.approval_selector.setCurrentIndex(dock.approval_selector.findData(mode))
    assert QSettings().value("geotaro/approval_mode") == mode
    dock.session.set_running(True)
    assert not dock.approval_selector.isEnabled()
    response = {"message": "提案", "code": "print('approval_marker')", "title": "承認テスト"}
    if assessment is not None:
        response.update(requires_approval=assessment, approval_reason="既存データを変更します" if assessment else "")
    attention.clear()
    dock.session.on_response(response)
    assert approval_marker_ran() == should_run
    if not should_run:
        # Waiting for approval notifies with the reason.
        assert len(attention) == 1 and attention[0].startswith(tr("Waiting for execution approval") + ": "), attention
        if assessment:
            assert attention[0].endswith("既存データを変更します")
        assert dock.session.pending_code and dock.run.isEnabled()
        app.processEvents()
        for button in (dock.run, dock.run_always, dock.stop):
            assert not button.isHidden()
            assert abs(button.geometry().center().y() - dock.context_ring.geometry().center().y()) <= 2
        if assessment:
            assert "既存データを変更します" in dock.transcript.toPlainText()
        if mode == "ask":
            dock.run.click()
            assert approval_marker_ran()
    dock.session.cancel()
    assert dock.session.pending_code is None and dock.approval_selector.isEnabled()
QMessageBox.warning = original_warning
# A question notifies with the question itself rather than the message.
dock.session.new_chat()
dock.session.set_running(True)
attention.clear()
dock.session.on_response({"message": "確認です", "code": "", "title": "", "question": "どの列を使いますか？",
                          "choices": ["A", "B"]})
assert attention == ["どの列を使いますか？"], attention
dock.session.attention_needed.disconnect(attention.append)
# "今後は自動承認" runs the pending code and switches to Full auto only after consent.
for start_mode, answer, expected in (("ask", QMessageBox.StandardButton.No, "ask"),
                                     ("auto", QMessageBox.StandardButton.No, "auto"),
                                     ("ask", QMessageBox.StandardButton.Yes, "full_auto")):
    QMessageBox.warning = lambda *args: QMessageBox.StandardButton.Yes
    dock.session.new_chat()
    dock.approval_selector.setCurrentIndex(dock.approval_selector.findData(start_mode))
    dock.session.set_running(True)
    dock.session.on_response({"message": "提案", "code": "print('approval_marker')", "title": "",
                      "requires_approval": True, "approval_reason": "既存データを変更します"})
    assert dock.run_always.isEnabled() and not dock.run_always.isHidden()
    prompts = []
    QMessageBox.warning = lambda *args: prompts.append(args[2]) or answer
    dock.run_always.click()
    assert len(prompts) == 1 and "Full auto" in prompts[0]
    assert dock.session.options["approval_mode"] == expected == dock.approval_selector.currentData()
    assert QSettings().value("geotaro/consented_approval_mode") == ("" if expected == "ask" else expected)
    if expected == "full_auto":
        assert approval_marker_ran() and dock.run_always.isHidden()
        assert "Full autoに切り替えました" in dock.transcript.toPlainText()
    else:
        assert not approval_marker_ran() and dock.session.pending_code and dock.run.isEnabled()
    dock.session.cancel()
QMessageBox.warning = original_warning
dock.session.new_chat()
QMessageBox.warning = lambda *args: QMessageBox.StandardButton.Yes
dock.approval_selector.setCurrentIndex(dock.approval_selector.findData("full_auto"))
QMessageBox.warning = original_warning

with tempfile.TemporaryDirectory() as directory:
    fake = Path(directory) / "claude"
    fake.write_text('''#!/usr/bin/env python3
import json, sys
p = json.load(sys.stdin)
if not any(x["role"] == "bridge" for x in p["conversation"]):
    assert 'processing_catalog' in p and p['versions']['geos'] and 'qgis_context' not in p
    code = "from qgis.core import QgsVectorLayer\\nlayer = QgsVectorLayer('Point?crs=EPSG:4326', 'Smoke layer', 'memory')\\nproject.addMapLayer(layer)\\nprint(layer.isValid())"
else:
    assert 'processing_catalog' not in p and 'qgis_context' not in p
    assert p["conversation"][-1]["content"]["ok"]
    code = ""
print(json.dumps({"subtype":"success", "structured_output":{"message":"Done", "code":code, "title":"レイヤーの作成" if p["generate_title"] else "変更しないタイトル"}}))
''')
    fake.chmod(0o755)
    dock.session.options["executable"] = str(fake)
    dock.input.setPlainText("Create a layer")
    dock.submit()
    wait_until(lambda: not dock.session.running)
    assert len(QgsProject.instance().mapLayers()) == 1, dock.transcript.toPlainText()
    assert len(dock.session.history) == 4, dock.session.history
    assert dock.session.session_title == 'レイヤーの作成'
    assert dock.sessions.currentText() == '[Claude] レイヤーの作成'
    assert dock.session.store.load(dock.session.session_id)['title'] == 'レイヤーの作成'
    titled_session = dock.session.session_id
    assert dock.session.load(titled_session)
    assert dock.session.session_title == 'レイヤーの作成'
    assert dock.sessions.currentText() == '[Claude] レイヤーの作成'
    # A restored turn folds the run result between its first and final replies.
    steps = dock.transcript.steps
    first, result, final = (bubble.parentWidget() for bubble in dock.transcript.messages[-3:])
    assert steps is not None and steps.steps.count() == 1 and steps.body.isHidden()
    assert result.parentWidget() is steps.body
    assert first.parentWidget() is final.parentWidget() is dock.transcript.content
    assert steps.toggle.text() == "途中経過（1件）"
    steps.toggle.click()
    assert not steps.body.isHidden()
    assert dock.session.history[2]["content"]["output"] == "True\n"
    # Project state is fetched on demand through Processing instead of each request.
    import qgis.utils
    from qgis.gui import QgsMapCanvas
    state_canvas = QgsMapCanvas()
    smoke_layer = next(iter(QgsProject.instance().mapLayers().values()))
    qgis.utils.iface = type("StateIface", (), {"activeLayer": lambda self: smoke_layer,
                                               "mapCanvas": lambda self: state_canvas})()
    result = dock.session.runtime.execute(
        "import json\nstate = json.loads(processing.run('geotaro:project_state', {})['STATE'])\n"
        "print(json.dumps(state))")
    assert result["ok"], result
    state = json.loads(result["output"])
    assert state["layer_count"] == 1 and state["layers"][0]["name"] == "Smoke layer"
    assert state["layers"][0]["geometry_type"] == "Point" and state["layers"][0]["feature_count"] == 0
    assert state["layers"][0]["visible"] and state["layers"][0]["provider"] == "memory"
    assert state["active_layer_id"] == smoke_layer.id() and len(state["canvas"]["extent"]) == 4
    qgis.utils.iface = None
    result = dock.session.runtime.execute("x = 42\nprint('before failure')\nraise RuntimeError('expected')")
    assert not result["ok"] and "expected" in result["error"]
    assert result["output"] == "before failure\n"
    result = dock.session.runtime.execute("print(x)")
    assert not result["ok"] and "NameError" in result["error"]
    assert not dock.session.runtime.execute("raise SystemExit(1)")["ok"]
    assert len(dock.session.runtime.execute("print('x' * 50000)")["output"]) == 20000
    dock.session.new_chat()
    assert not dock.session.session_title
    empty_session = dock.session.session_id
    empty_records = dock.session.store.list()
    dock.session.new_chat()
    assert dock.session.session_id == empty_session and dock.session.store.list() == empty_records
    dock.session.options["approval_mode"] = "ask"
    dock.input.setPlainText("Preview only")
    dock.submit()
    wait_until(lambda: dock.session.pending_code is not None)
    assert len(QgsProject.instance().mapLayers()) == 1, dock.transcript.toPlainText()
    dock.session.cancel()
    assert not dock.session.running and dock.session.pending_code is None
    dock.session.new_chat()
    dock.session.options["executable"] = "/nonexistent/claude"
    dock.input.setPlainText("Fail to start")
    dock.submit()
    wait_until(lambda: not dock.session.running)
    assert "起動できません" in dock.transcript.toPlainText()
    fake.write_text('#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps({"is_error":True,"result":"Not logged in"}))\nsys.exit(1)\n')
    dock.session.options["executable"] = str(fake)
    dock.input.setPlainText("Auth failure")
    dock.submit()
    wait_until(lambda: not dock.session.running)
    assert "Not logged in" not in dock.transcript.toPlainText()
    assert dock.transcript.login_card is not None and not dock.transcript.login_card.login.isHidden()
    assert dock.session.history[-1]["content"] == "Interaction stopped: Not logged in"
    # Login runs the CLI's own browser flow, accepts a pasted code, then resends the stopped message.
    marker = Path(directory) / "logged-in"
    fake.write_text('''#!/usr/bin/env python3
import json, sys
from pathlib import Path
marker = Path(%r)
if sys.argv[1:3] == ["auth", "login"]:
    assert sys.argv[3:] == ["--claudeai"]
    print("Opening browser to sign in…")
    print("If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&state=x")
    print("Paste code here if prompted > ", end="", flush=True)
    code = sys.stdin.readline().strip()
    if code != "good-code":
        print("Invalid code. Please make sure the full code was copied.")
        sys.exit(1)
    marker.write_text("ok")
    print("Login successful.")
    sys.exit(0)
p = json.load(sys.stdin)
if not marker.exists():
    print(json.dumps({"type": "result", "subtype": "success", "result": "Not logged in · Please run /login"}))
    sys.exit(1)
assert any(x["role"] == "user" and x["content"] == "Login flow" for x in p["conversation"])
print(json.dumps({"subtype": "success", "structured_output": {"message": "ログイン後の応答", "code": "", "title": "ログイン"}}))
''' % str(marker))
    dock.session.new_chat()
    dock.input.setPlainText("Login flow")
    dock.submit()
    wait_until(lambda: not dock.session.running and dock.transcript.login_card is not None)
    card = dock.transcript.login_card
    card.login.click()
    wait_until(lambda: not card.link.isHidden())
    assert "https://claude.com/cai/oauth/authorize?code=true&amp;state=x" in card.link.text()
    assert card.code_row.isHidden() and not card.cancel.isHidden() and card.login.isHidden()
    # The code field appears only after opening the fallback page, which is the one that shows a code.
    from qgis.PyQt.QtGui import QDesktopServices
    opened = []
    original_open_url = QDesktopServices.openUrl
    QDesktopServices.openUrl = lambda url: opened.append(url.toString()) or True
    try:
        card.link.linkActivated.emit("https://claude.com/cai/oauth/authorize?code=true&state=x")
    finally:
        QDesktopServices.openUrl = original_open_url
    assert opened == ["https://claude.com/cai/oauth/authorize?code=true&state=x"]
    assert not card.code_row.isHidden()
    card.code.setText("good-code")
    card.send_code.click()
    wait_until(lambda: dock.transcript.messages[-1].message.text() == "ログイン後の応答")
    wait_until(lambda: not dock.session.running)
    assert dock.transcript.login_card is None and "ログインしました" in card.text.text()
    assert dock.login.process is None
    # Cancelling keeps the prompt so the user can retry.
    marker.unlink()
    dock.session.new_chat()
    dock.input.setPlainText("Login cancel")
    dock.submit()
    wait_until(lambda: not dock.session.running and dock.transcript.login_card is not None)
    card = dock.transcript.login_card
    card.login.click()
    wait_until(lambda: not card.link.isHidden())
    card.cancel.click()
    assert dock.login.process is None and not card.login.isHidden() and "中止" in card.text.text()
    # A question hands the turn to the user; a choice is sent as the user's answer.
    fake.write_text('''#!/usr/bin/env python3
import json, sys
p = json.load(sys.stdin)
answers = [x["content"] for x in p["conversation"] if x["role"] == "user"]
base = {"code": "", "title": "", "requires_approval": False, "approval_reason": "", "question": "", "choices": []}
if answers[-1] == "Both":
    out = dict(base, message="x", code="raise AssertionError('must not run')", question="どれ？")
elif answers[-1] in ("道路（2024）", "自由回答", "ツールとして保存") or answers[-1].endswith("picked.gpkg"):
    out = dict(base, message="回答: " + answers[-1])
elif answers[-1] == "Finish":
    out = dict(base, message="完了しました", suggestion="ツールとして保存")
elif answers[-1] == "Save":
    out = dict(base, message="x", question="保存先は？", choices=["/data/out.gpkg"],
               path_request="file", path_suggestion="/data/out.gpkg")
else:
    out = dict(base, message="道路レイヤーが2つあります。", question="どちらを使いますか？",
               choices=["道路（2021）", "道路（2024）"])
print(json.dumps({"subtype": "success", "structured_output": out}, ensure_ascii=False))
''')
    dock.session.new_chat()
    dock.input.setPlainText("道路をバッファして")
    dock.submit()
    wait_until(lambda: not dock.session.running)
    asked = dock.transcript.messages[-1]
    assert asked.question == "どちらを使いますか？" and [b.text() for b in asked.choice_buttons] == ["道路（2021）", "道路（2024）"]
    assert all(b.isEnabled() for b in asked.choice_buttons) and "回答を待って" in dock.status.text()
    # Restoring keeps an unanswered question answerable.
    assert dock.session.load(dock.session.session_id)
    asked = next(b for b in dock.transcript.messages if b.question)
    assert all(b.isEnabled() for b in asked.choice_buttons)
    dock.input.setPlainText("下書き")
    asked.choice_buttons[1].click()
    assert dock.input.toPlainText() == "下書き"
    wait_until(lambda: not dock.session.running)
    assert dock.session.history[-2]["content"] == "道路（2024）" and dock.transcript.messages[-1].message.text() == "回答: 道路（2024）"
    assert not any(b.isEnabled() for b in asked.choice_buttons) and asked.choice_buttons[1].text() == "✓ 道路（2024）"
    assert dock.session.load(dock.session.session_id)
    assert not any(b.isEnabled() for q in dock.transcript.messages if q.question for b in q.choice_buttons)
    # Free text answers a question too.
    dock.session.new_chat()
    dock.input.setPlainText("道路をバッファして")
    dock.submit()
    wait_until(lambda: not dock.session.running)
    asked = dock.transcript.messages[-1]
    dock.input.setPlainText("自由回答")
    dock.submit()
    wait_until(lambda: not dock.session.running)
    assert not any(b.isEnabled() for b in asked.choice_buttons)
    assert dock.transcript.messages[-1].message.text() == "回答: 自由回答"
    # A suggestion offers one optional button without waiting for an answer.
    dock.input.setPlainText("Finish")
    dock.submit()
    wait_until(lambda: not dock.session.running)
    offered = dock.transcript.messages[-1]
    assert not offered.question and [b.text() for b in offered.choice_buttons] == ["ツールとして保存"]
    assert "回答を待って" not in dock.status.text()
    offered.choice_buttons[0].click()
    wait_until(lambda: not dock.session.running)
    assert dock.session.history[-2]["content"] == "ツールとして保存" and not offered.choice_buttons[0].isEnabled()
    dock.input.setPlainText("Finish")
    dock.submit()
    wait_until(lambda: not dock.session.running)
    assert dock.session.load(dock.session.session_id)
    offered = [b for b in dock.transcript.messages if b.suggestion][-1]
    assert offered.suggestion == "ツールとして保存" and offered.choice_buttons[0].isEnabled()
    dock.input.setPlainText("自由回答")
    dock.submit()
    wait_until(lambda: not dock.session.running)
    assert not offered.choice_buttons[0].isEnabled()
    # A path request adds a button that answers with the path chosen in a file dialog.
    from geotaro_test.ui import chat as chat_ui_module
    dock.input.setPlainText("Save")
    dock.submit()
    wait_until(lambda: not dock.session.running)
    asked = dock.transcript.messages[-1]
    picker = asked.choice_buttons[-1]
    assert len(asked.choice_buttons) == 2 and picker.text() == "保存先を選択…"
    calls = []
    original = chat_ui_module.QFileDialog.getSaveFileName
    chat_ui_module.QFileDialog.getSaveFileName = staticmethod(
        lambda *args: calls.append(args) or (str(Path(directory) / "picked.gpkg"), ""))
    try:
        picker.click()
    finally:
        chat_ui_module.QFileDialog.getSaveFileName = original
    wait_until(lambda: not dock.session.running)
    assert calls[0][2] == "/data/out.gpkg" and calls[0][3].startswith("GPKG (*.gpkg)")
    assert dock.session.history[-2]["content"] == str(Path(directory) / "picked.gpkg")
    assert not picker.isEnabled()
    assert dock.session.load(dock.session.session_id)
    assert next(b for b in dock.transcript.messages if b.path_request).path_suggestion == "/data/out.gpkg"
    # Code together with a question is rejected rather than run without waiting.
    dock.input.setPlainText("Both")
    dock.submit()
    wait_until(lambda: not dock.session.running)
    assert "codeを空に" in dock.transcript.toPlainText() and dock.session.pending_code is None
    dock.input.clear()
    fake.write_text("#!/bin/sh\nsleep 30\n")
    dock.session.options["executable"] = str(fake)
    dock.input.setPlainText("Cancel")
    dock.submit()
    wait_until(lambda: dock.session.agent.process is not None and dock.session.agent.process.processId() != 0)
    dock.session.cancel()
    assert dock.session.agent.process is None and not dock.session.running
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
    dock.session.new_chat()
    dock.session.options["executable"] = str(fake)
    dock.input.setPlainText("Streaming test")
    dock.submit()
    wait_until(lambda: "ストリーム表示" in dock.transcript.toPlainText())
    assert dock.session.running and dock.session.history[-1]["role"] == "user"
    wait_until(lambda: not dock.session.running)
    assert dock.transcript.toPlainText().count("ストリーム表示") == 1
    assert dock.transcript.messages[-1].message.text() == "ストリーム表示 完了"

# Dropped files ride along with the user turn; dropped images are also shown to the agent.
with tempfile.TemporaryDirectory() as directory:
    from qgis.PyQt.QtCore import QMimeData, QPointF, Qt, QUrl
    from qgis.PyQt.QtGui import QDropEvent, QImage
    image_path = Path(directory) / "dropped.png"
    data_path = Path(directory) / "points.csv"
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    assert image.save(str(image_path))
    data_path.write_text("x,y\n1,2\n", encoding="utf-8")
    fake = Path(directory) / "attach-claude"
    fake.write_text("#!/usr/bin/env python3\n" + """
import json, sys
assert '--input-format' in sys.argv
content = json.loads(sys.stdin.readline())['message']['content']
assert content[0]['type'] == 'image'
turn = json.loads(content[-1]['text'])['conversation'][-1]
assert turn['content'] == '' and turn['attachments'][1].endswith('points.csv'), turn
print(json.dumps({'type': 'result', 'structured_output': {'message': '添付を確認', 'code': ''}}), flush=True)
""")
    fake.chmod(0o755)
    dock.session.new_chat()
    dock.session.options["executable"] = str(fake)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in (image_path, data_path)])
    drop = QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    dock.input.dropEvent(drop)
    assert dock.attachments == [str(image_path), str(data_path)] and not dock.input.toPlainText()
    assert dock.attachment_bar.isVisibleTo(dock)
    dock.input.dropEvent(drop)
    assert len(dock.attachments) == 2
    dock.submit()
    assert not dock.attachments and not dock.attachment_bar.isVisibleTo(dock)
    assert dock.session.history[-1]["attachments"] == [str(image_path), str(data_path)]
    wait_until(lambda: not dock.session.running)
    assert dock.transcript.messages[-1].message.text() == "添付を確認"

from qgis.PyQt.QtCore import QPoint, Qt, QTimer
from qgis.PyQt.QtGui import QInputMethodEvent
from qgis.PyQt.QtTest import QTest
from geotaro_test.ui.chat import ChatInput, MessageText, SettingsDialog
from geotaro_test.ui.chat import ChatTranscript

# Agent Markdown links must be clickable as well as visually marked as links.
linked_message = MessageText(True)
linked_message.resize(320, 40)
linked_message.setText("[QGIS](https://qgis.org)")
linked_message.show()
app.processEvents()
assert linked_message.openExternalLinks()
assert linked_message.textInteractionFlags() & Qt.TextInteractionFlag.LinksAccessibleByMouse
link_point = QPoint(8, 8)
assert linked_message.anchorAt(link_point) == "https://qgis.org"
clicked_links = []
linked_message.setOpenLinks(False)
linked_message.setOpenExternalLinks(False)
linked_message.anchorClicked.connect(lambda url: clicked_links.append(url.toString()))
QTest.mouseClick(linked_message.viewport(), Qt.MouseButton.LeftButton, pos=link_point)
assert clicked_links == ["https://qgis.org"]
linked_message.close()

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
QTest.keyClick(editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
assert "\n" in editor.toPlainText() and not submissions
QTest.keyClick(editor, Qt.Key.Key_Return)
assert len(submissions) == 1
editor.inputMethodEvent(QInputMethodEvent("変換中", []))
QTest.keyClick(editor, Qt.Key.Key_Return)
assert len(submissions) == 1
editor.inputMethodEvent(QInputMethodEvent())
dialog = SettingsDialog(dock.session.options)
dialog.executable.setText("/tmp/cancelled")
assert dialog.custom_prompt.height() == 96
assert dialog.provider_tabs.tabText(dialog.provider_tabs.count() - 1) == tr("About")
about_labels = [label.text() for label in dialog.provider_tabs.widget(dialog.provider_tabs.count() - 1).findChildren(QLabel)]
assert "Geotaro" in about_labels and tr("Version: {0}").format("dev") in about_labels
assert tr("QGIS AI assistant") in about_labels and tr("Developed by") in about_labels
assert dialog.mierune_link.openExternalLinks()
assert 'href="https://www.mierune.co.jp/"' in dialog.mierune_link.text()
# Syncing built-in skills overwrites edits only after confirmation.
edited_skill = Path(cli_homes.name) / "claude/skills" / bundled[0] / "SKILL.md"
edited_skill.write_text("Edited", encoding="utf-8")
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
    dialog.sync_skills.click()
assert edited_skill.read_text(encoding="utf-8") == "Edited"
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
        patch.object(QMessageBox, "information") as informed:
    dialog.sync_skills.click()
assert edited_skill.read_text(encoding="utf-8") == (ROOT / "skills" / bundled[0] / "SKILL.md").read_text(encoding="utf-8")
assert str(edited_skill.parents[1]) in informed.call_args[0][2]
dialog.reject()
assert dock.session.options["executable"] != "/tmp/cancelled"
def accept_settings():
    dialog = app.activeModalWidget()
    dialog.executable.setText("/tmp/saved-claude")
    dialog.custom_prompt.setPlainText("  Prefer GeoPackage outputs.  ")
    assert dialog.provider_tabs.tabText(0) == tr("General") and dialog.notifications.isChecked()
    dialog.notifications.setChecked(False)
    assert not hasattr(dialog, "model")
    dialog.accept()
dock.model_selector.setCurrentIndex(dock.model_selector.findData("claude-sonnet-5"))
assert not dock.model_selector.isEditable()
QTimer.singleShot(0, accept_settings)
dock.open_settings()
assert {key: dock.session.options[key] for key in ("executable", "approval_mode", "model", "enable_skills", "enable_connectors")} == {"executable": "/tmp/saved-claude", "approval_mode": "ask", "model": "claude-sonnet-5", "enable_skills": True, "enable_connectors": False}
assert QSettings().value("geotaro/executable") == "/tmp/saved-claude"
assert dock.session.options["custom_prompt"] == "Prefer GeoPackage outputs."
assert QSettings().value("geotaro/custom_prompt") == "Prefer GeoPackage outputs."
assert dock.session.options["notifications"] is False
assert QSettings().value("geotaro/notifications", True, type=bool) is False

# Older models are offered, and unchecked models leave the picker for both providers.
assert dock.model_selector.findData("claude-opus-4-5") >= 0
dock.model_selector.setCurrentIndex(dock.model_selector.findData("claude-opus-4-5"))
def hide_older_models():
    dialog = app.activeModalWidget()
    assert dialog.model_checks["claude-opus-4-5"].isChecked()
    dialog.model_checks["claude-opus-4-5"].setChecked(False)
    dialog.model_checks["gpt-5.4"].setChecked(False)
    dialog.accept()
QTimer.singleShot(0, hide_older_models)
dock.open_settings()
assert dock.session.options["disabled_models"] == ["gpt-5.4", "claude-opus-4-5"]
assert json.loads(QSettings().value("geotaro/disabled_models")) == ["gpt-5.4", "claude-opus-4-5"]
# Hiding the selected model switches to the CLI default instead of keeping it usable.
assert dock.model_selector.findData("claude-opus-4-5") < 0
assert dock.session.options["model"] == "" and dock.model_selector.currentData() == ""
assert QSettings().value("geotaro/model") == ""
assert dock.model_selector.findData("claude-sonnet-4-5") >= 0
dock.session.update_settings({"disabled_models": []})
assert dock.model_selector.findData("claude-opus-4-5") >= 0
dock.model_selector.setCurrentIndex(dock.model_selector.findData("claude-sonnet-5"))

# Inventory tabs are read-only; connection checks are asynchronous and redact URLs.
with tempfile.TemporaryDirectory() as directory:
    cli = Path(directory) / "inventory-claude"
    cli.write_text("#!/usr/bin/env python3\nimport sys\nassert sys.argv[1:] == ['mcp', 'list']\nprint('test-cloud: https://SECRET - ✓ Connected')\n")
    cli.chmod(0o755)
    inventory_dialog = SettingsDialog({"executable": str(cli), "auto_execute": True})
    inventory_dialog.capabilities.check_connections()
    wait_until(lambda: inventory_dialog.capabilities.process is None)
    rows = inventory_dialog.capabilities.connectors
    assert any(row["name"] == "test-cloud" and row["status"] == tr("Connected") for row in rows)
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
with patch('geotaro_test.core.capabilities.read_codex_inventory', return_value=inventory):
    before = dict(dock.session.options)
    settings_dialog = SettingsDialog(dock.session.options)
    settings_dialog.provider_tabs.setCurrentWidget(settings_dialog.provider_pages["codex"])
    settings_dialog.codex_capabilities.controls[('connectors', 'test_server')].setCurrentIndex(2)
    settings_dialog.codex_capabilities.controls[('skills', '/tmp/example/SKILL.md')].setCurrentIndex(1)
    choices = settings_dialog.options()['codex_capabilities']
    assert choices == {'skills': {'/tmp/example/SKILL.md': True}, 'connectors': {'test_server': False}}
    settings_dialog.provider_tabs.setCurrentWidget(settings_dialog.provider_pages["claude"])
    assert settings_dialog.options()['codex_capabilities'] == choices
    settings_dialog.reject()
    assert dock.session.options == before

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
    for model in ('claude-sonnet-5', 'claude-opus-5-5', 'claude-fable-5-1',
                  'claude-haiku-4-5-20251001', ''):
        dock.session.new_chat()
        dock.session.options['executable'] = str(cli)
        dock.model_selector.setCurrentIndex(dock.model_selector.findData(model))
        dock.input.setPlainText(model or 'default')
        dock.submit()
        wait_until(lambda: not dock.session.running)
        assert dock.session.history[-1]['content']['message'] == 'Model OK'

# Switching/restoring never replays Python or restores live QGIS objects.
dock.session.new_chat()
dock.session.options['model'] = 'claude-opus-5'
dock.session.history = [{'role': 'user', 'content': '保存テスト'},
                {'role': 'assistant', 'content': {'message': '以前のコード', 'code': "raise AssertionError('must not replay')"}}]
dock.session.log(tr('You'), '保存テスト')
dock.session.log('Claude', '以前のコード', "raise AssertionError('must not replay')")
dock.input.setPlainText('下書き')
assert dock.session.save()
first_session = dock.session.session_id
layer_count = len(QgsProject.instance().mapLayers())
dock.session.new_chat()
second_session = dock.session.session_id
assert first_session != second_session and not dock.session.history
assert not dock.transcript.messages
assert any(notice.text() == '新しいセッションを開始しました。'
           for notice in dock.transcript.findChildren(QLabel, 'systemNotice'))
assert not dock.session.store.load(second_session)['messages']
assert dock.session.load(first_session)
assert dock.session.options['model'] == 'claude-opus-5'
assert dock.input.toPlainText() == '下書き'
assert dock.session.pending_code is None and not dock.session.running
assert len(QgsProject.instance().mapLayers()) == layer_count
assert len(dock.transcript.messages) == 2
restored_code = dock.transcript.messages[1]
from qgis.gui import QgsCodeEditorPython
assert isinstance(restored_code.code, QgsCodeEditorPython) and restored_code.code.isReadOnly()
assert restored_code.code.text() == restored_code.code_text() == "raise AssertionError('must not replay')"
assert dock.transcript.messages[0].code is None
assert '以前のコード' in dock.transcript.toPlainText()
notices = [notice for notice in dock.transcript.findChildren(QLabel, 'systemNotice') if not notice.isHidden()]
assert len(notices) == 1 and '現在のQGISプロジェクトで作業を続けます' in notices[0].text()
assert '現在のQGISプロジェクトで作業を続けます' not in dock.transcript.toPlainText()
assert not any('セッションを復元しました' in str(entry['content']) for entry in dock.session.history)
assert not any('セッションを復元しました' in message['text']
               for message in dock.session.store.load(first_session)['messages'])
# An interrupted execution is reported rather than retried on startup.
payload = dock.session.store.load(first_session)
payload['interrupted'] = True
dock.session.store.save(first_session, '保存テスト', payload)
assert dock.session.load(first_session)
notices = [notice for notice in dock.transcript.findChildren(QLabel, 'systemNotice') if not notice.isHidden()]
assert len(notices) == 1 and '途中で終了' in notices[0].text()
assert not any('セッションを復元しました' in str(entry['content']) for entry in dock.session.history)
assert 'セッションを復元しました' not in dock.transcript.toPlainText()
assert '新しいセッションを開始しました' not in dock.transcript.toPlainText()
# Reasoning summaries are visible in the live transcript but absent from saved sessions.
dock.session.running = True
dock.session.on_progress({'reasoning': 'レイヤーを確認しています', 'message': '', 'code': ''})
dock.session.running = False
assert dock.reasoning_notice is not None
assert 'レイヤーを確認しています' in dock.reasoning_notice.text()
assert not any('レイヤーを確認しています' in str(entry) for entry in dock.session.history)
assert dock.session.save()
assert not any('レイヤーを確認しています' in str(message)
               for message in dock.session.store.load(first_session)['messages'])
assert dock.session.load(first_session)
assert not any('レイヤーを確認しています' in notice.text()
               for notice in dock.transcript.findChildren(QLabel, 'systemNotice') if not notice.isHidden())
# Actual dock destruction and recreation restores the last selected session.
plugin.unload()
plugin.show()
dock = plugin.dock
assert dock.session.session_id == first_session and dock.session.options['model'] == 'claude-opus-5'
assert dock.model_selector.currentData() == 'claude-opus-5'
assert dock.input.toPlainText() == '下書き'
from qgis.PyQt.QtWidgets import QMessageBox
from geotaro_test.ui.session_picker import SessionPicker
original_question = QMessageBox.question
def delete_current_from_list():
    target = dock.session.session_id
    def choose():
        dialog = next(child for child in dock.findChildren(SessionPicker) if child.isVisible())
        while True:
            item = next((dialog.results.item(i) for i in range(dialog.results.count())
                         if dialog.results.item(i).data(Qt.ItemDataRole.UserRole) == target), None)
            if item is not None:
                dialog.results.setCurrentItem(item)
                dialog.delete_button.click()
                dialog.reject()
                return
            assert dialog.more.isEnabled()
            dialog.more.click()
    QTimer.singleShot(0, choose)
    dock.open_session_picker()

from qgis.PyQt.QtCore import Qt
QMessageBox.question = lambda *args: QMessageBox.StandardButton.No
delete_current_from_list()
assert dock.session.session_id == first_session
QMessageBox.question = lambda *args: QMessageBox.StandardButton.Yes
try:
    delete_current_from_list()
    assert all(row[0] != first_session for row in dock.session.store.list())
    assert len(QgsProject.instance().mapLayers()) == layer_count
    for session_id, _, _ in dock.session.store.list():
        if session_id != dock.session.session_id:
            dock.session.store.delete(session_id)
    delete_current_from_list()
    assert len(dock.session.store.list()) == 1 and dock.session.history == []
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
    dock.session.new_chat()
    first = dock.session.session_id
    dock.session.options['executable'] = str(cli)
    for text in ['first', 'second']:
        dock.input.setPlainText(text)
        dock.submit()
        wait_until(lambda: not dock.session.running)
    calls = [json.loads(line) for line in call_log.read_text().splitlines()]
    assert [call['mode'] for call in calls] == ['--session-id', '--resume']
    assert all(call['id'] == first for call in calls)
    assert calls[-1]['prompt']['conversation'] == [{'role': 'user', 'content': 'second'}]
    dock.session.new_chat()
    second = dock.session.session_id
    dock.session.options['executable'] = str(cli)
    dock.input.setPlainText('other')
    dock.submit()
    wait_until(lambda: not dock.session.running)
    dock.sessions.setCurrentIndex(dock.sessions.findData(first))
    assert dock.session.session_id == first and dock.session.agent_started
    plugin.unload()
    plugin.show()
    dock = plugin.dock
    assert dock.session.session_id == first and dock.session.agent_started
    dock.session.options['executable'] = str(cli)
    dock.input.setPlainText('third')
    dock.submit()
    wait_until(lambda: not dock.session.running)
    calls = [json.loads(line) for line in call_log.read_text().splitlines()]
    assert calls[-2]['id'] == second and calls[-2]['mode'] == '--session-id'
    assert calls[-1]['id'] == first and calls[-1]['mode'] == '--resume'
    assert len({call['cwd'] for call in calls}) == 1
    assert all(entry['content'] not in ('first', 'second') for entry in calls[-1]['prompt']['conversation'])
    # Missing native history must remain an error, never silently create a new session.
    cli.write_text("#!/usr/bin/env python3\nimport sys\nassert '--resume' in sys.argv\nprint('No conversation found', file=sys.stderr)\nsys.exit(1)\n")
    dock.input.setPlainText('missing history')
    dock.submit()
    wait_until(lambda: not dock.session.running)
    assert dock.session.session_id == first and dock.session.agent_started
    assert 'No conversation found' in dock.transcript.toPlainText()
    assert not hasattr(dock, 'save_button')
    dock.input.setPlainText('自動保存される下書き')
    wait_until(lambda: dock.session.store.load(first)['draft'] == '自動保存される下書き')
    plugin.initGui()

# Capability switches change real CLI flags, including when resuming a session.
with tempfile.TemporaryDirectory() as directory:
    cli = Path(directory) / 'capability-claude'
    cli.write_text("#!/usr/bin/env python3\n" + r"""
import json, os, sys
from pathlib import Path
p = json.load(sys.stdin)
request = json.loads(p['conversation'][-1]['content'])
skills, connectors = request[:2]
expected_overrides = request[2] if len(request) > 2 else {}
settings = json.loads(sys.argv[sys.argv.index('--settings') + 1])
assert settings.get('skillOverrides', {}) == expected_overrides
instructions = sys.argv[sys.argv.index('--system-prompt') + 1]
with Path(__file__).with_name('prompts.jsonl').open('a') as f:
    f.write(json.dumps(instructions) + '\n')
assert os.environ['CLAUDE_CONFIG_DIR'] + '/skills' in instructions
assert 'name: qgis-cartography' not in instructions
assert ('--disable-slash-commands' not in sys.argv) == skills
assert ('--strict-mcp-config' not in sys.argv) == connectors
assert ('--mcp-config' not in sys.argv) == connectors
assert sys.argv[sys.argv.index('--tools') + 1] == ('default' if skills or connectors else '')
assert '--dangerously-skip-permissions' not in sys.argv
if skills or connectors:
    assert sys.argv[sys.argv.index('--permission-mode') + 1] == 'dontAsk'
    assert 'connector tools only within their permissions' in sys.argv[sys.argv.index('--system-prompt') + 1]
if skills:
    assert sys.argv[sys.argv.index('--allowedTools') + 1] == 'Skill'
mode = '--resume' if '--resume' in sys.argv else '--session-id'
sid = sys.argv[sys.argv.index(mode) + 1]
print(json.dumps({'type': 'result', 'session_id': sid,
                  'structured_output': {'message': 'Capabilities OK', 'code': ''}}))
""")
    cli.chmod(0o755)
    dock.session.new_chat()
    dock.session.options['executable'] = str(cli)
    for skills, connectors in [(False, False), (True, False), (False, True), (True, True)]:
        dialog = SettingsDialog(dock.session.options)
        dialog.capabilities.toggles['enable_skills'].setChecked(skills)
        dialog.capabilities.toggles['enable_connectors'].setChecked(connectors)
        options = dialog.options()
        assert options['enable_skills'] == skills and options['enable_connectors'] == connectors
        dialog.accept()
        dock.session.options.update(options)
        dock.input.setPlainText(json.dumps([skills, connectors]))
        dock.submit()
        wait_until(lambda: not dock.session.running)
        assert dock.session.history[-1]['content']['message'] == 'Capabilities OK', dock.transcript.toPlainText()
    prompts = [json.loads(line) for line in cli.with_name('prompts.jsonl').read_text().splitlines()]
    assert len(prompts) == 4 and len(set(prompts)) == 1
    enabled_session = dock.session.session_id
    assert dock.session.store.load(enabled_session)['enable_skills']
    assert dock.session.store.load(enabled_session)['enable_connectors']
    dock.session.new_chat()
    assert dock.session.options['enable_skills'] and not dock.session.options['enable_connectors']
    dock.session.load(enabled_session)
    assert dock.session.options['enable_skills'] and dock.session.options['enable_connectors']
    skill_name = bundled[0]
    dialog = SettingsDialog(dock.session.options)
    dialog.capabilities.skill_choices[skill_name].setCurrentIndex(2)
    dialog.capabilities.refresh()
    assert dialog.options()['claude_skills'] == {skill_name: 'off'}
    dock.session.update_settings(dialog.options())
    dialog.accept()
    dock.input.setPlainText(json.dumps([True, True, {skill_name: 'off'}]))
    dock.submit()
    wait_until(lambda: not dock.session.running)
    assert dock.session.history[-1]['content']['message'] == 'Capabilities OK'
    assert dock.session.store.load(enabled_session)['claude_skills'] == {skill_name: 'off'}
    dialog = SettingsDialog(dock.session.options)
    dialog.capabilities.skill_choices[skill_name].setCurrentIndex(1)
    dock.session.update_settings(dialog.options())
    dialog.accept()
    dock.input.setPlainText(json.dumps([True, True, {skill_name: 'on'}]))
    dock.submit()
    wait_until(lambda: not dock.session.running)
    assert dock.session.history[-1]['content']['message'] == 'Capabilities OK'
    dock.session.load(enabled_session)
    assert dock.session.options['claude_skills'] == {skill_name: 'on'}
    dialog = SettingsDialog(dock.session.options)
    dialog.capabilities.toggles['enable_skills'].setChecked(False)
    dialog.reject()
    assert dock.session.options['enable_skills']

# Codex emits its own native ID, then resumes it for execution feedback and new turns.
with tempfile.TemporaryDirectory() as directory:
    cli = Path(directory) / 'codex'
    cli.write_text("#!/usr/bin/env python3\n" + r"""
import json, os, sys, time
from pathlib import Path
p = json.load(sys.stdin)
assert sys.argv[1] == 'exec'
assert '--json' in sys.argv and '--output-schema' in sys.argv
assert 'sandbox_mode="read-only"' in sys.argv
assert 'forced_login_method="chatgpt"' in sys.argv
instructions = json.loads(next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('developer_instructions=')))
assert os.environ['CODEX_HOME'] + '/skills' in instructions
assert 'name: qgis-cartography' not in instructions
assert 'mcp_servers.test_server.enabled=false' in sys.argv
assert '--dangerously-bypass-approvals-and-sandbox' not in sys.argv
assert json.loads(Path(sys.argv[sys.argv.index('--output-schema') + 1]).read_text())['required'] == ['message', 'code', 'title', 'requires_approval', 'approval_reason', 'question', 'choices', 'path_request', 'path_suggestion', 'suggestion']
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
    claude_session = dock.session.session_id
    dock.reset.menu().actions()[1].trigger()
    codex_session = dock.session.session_id
    assert codex_session != claude_session and dock.session.options['provider'] == 'codex'
    assert dock.model_selector.findData('gpt-6-astra') >= 0
    assert dock.model_selector.findData('claude-opus-5') < 0
    dock.session.options['codex_capabilities'] = {'connectors': {'test_server': False}}
    dock.session.options['codex_executable'] = str(cli)
    dock.session.options["approval_mode"] = "full_auto"
    count = len(QgsProject.instance().mapLayers())
    dock.input.setPlainText('Create a layer with Codex')
    dock.submit()
    wait_until(lambda: not dock.session.running)
    assert len(QgsProject.instance().mapLayers()) == count + 1, dock.transcript.toPlainText()
    assert dock.session.native_session_id == '0199a213-81c0-7800-8aa1-bbab2a035a53'
    assert dock.session.session_title == 'Codexでレイヤー作成'
    assert dock.sessions.currentText() == '[Codex] Codexでレイヤー作成'
    native_id = dock.session.native_session_id
    assert dock.session.history[-1]['content']['message'] == 'Codex OK'
    calls = [json.loads(line) for line in cli.with_name('calls.jsonl').read_text().splitlines()]
    assert [call['resume'] for call in calls] == [False, True]
    assert calls[-1]['prompt']['conversation'][-1]['content']['output'] == 'created\n'
    dialog = SettingsDialog(dock.session.options)
    assert dialog.capabilities is not None
    assert [dialog.provider_tabs.tabText(i) for i in range(3)] == [tr('General'), 'Codex', 'Claude']
    for page in dialog.provider_pages.values():
        assert [page.tabText(i) for i in range(3)] == ['一般', 'スキル', 'コネクタ']
    assert dialog.provider_tabs.currentIndex() == 0
    dialog.provider_tabs.setCurrentWidget(dialog.provider_pages["claude"])
    assert dock.session.options['provider'] == 'codex' and dock.session.session_id == codex_session
    assert dialog.codex_executable.text() == str(cli)
    dialog.reject()
    dock.sessions.setCurrentIndex(dock.sessions.findData(claude_session))
    assert dock.session.options['provider'] == 'claude'
    assert dock.model_selector.findData('gpt-6-astra') < 0
    dock.sessions.setCurrentIndex(dock.sessions.findData(codex_session))
    plugin.unload()
    plugin.show()
    dock = plugin.dock
    assert dock.session.options['provider'] == 'codex' and dock.session.native_session_id == native_id
    assert dock.session.options['codex_capabilities'] == {'connectors': {'test_server': False}}
    dock.session.options['codex_executable'] = str(cli)
    dock.input.setPlainText('Continue Codex')
    dock.submit()
    wait_until(lambda: not dock.session.running)
    calls = [json.loads(line) for line in cli.with_name('calls.jsonl').read_text().splitlines()]
    assert calls[-1]['resume']
    assert not calls[-1]['prompt']['generate_title']
    assert dock.session.session_title == 'Codexでレイヤー作成'
    assert len(QgsProject.instance().mapLayers()) == count + 1
    plugin.initGui()
    # Failed startup and malformed final response must leave QGIS untouched.
    dock.session.options['codex_executable'] = '/missing/codex'
    dock.input.setPlainText('Failed startup')
    dock.submit()
    wait_until(lambda: not dock.session.running)
    assert 'Codexを起動できません' in dock.transcript.toPlainText()
    dock.reset.menu().actions()[0].trigger()

# view_image attaches an image to the next request only: Claude via stream-json, Codex via --image.
with tempfile.TemporaryDirectory() as directory:
    image_code = ("from qgis.PyQt.QtGui import QImage, QColor\nimage = QImage(8, 8, QImage.Format.Format_RGB32)\n"
                  "image.fill(QColor('blue'))\npath = " + repr(str(Path(directory) / 'view.png')) + "\nimage.save(path)\n"
                  "print(processing.run('geotaro:view_image', {'INPUT': path})['IMAGE'])")
    claude = Path(directory) / 'view-claude'
    claude.write_text("#!/usr/bin/env python3\n" + r"""
import base64, json, sys
from pathlib import Path
raw = sys.stdin.read()
if '--input-format' in sys.argv:
    assert sys.argv[sys.argv.index('--input-format') + 1] == 'stream-json'
    content = json.loads(raw)['message']['content']
    images = [base64.b64decode(block['source']['data']) for block in content if block['type'] == 'image']
    prompt = json.loads(content[-1]['text'])
else:
    images, prompt = [], json.loads(raw)
with Path(__file__).with_name('calls.jsonl').open('a') as f:
    f.write(json.dumps({'png': [image[:4] == b'\x89PNG' for image in images], 'prompt': prompt}) + '\n')
mode = '--resume' if '--resume' in sys.argv else '--session-id'
sid = sys.argv[sys.argv.index(mode) + 1]
last = prompt['conversation'][-1]
code = CODE if last == {'role': 'user', 'content': 'look'} else ''
print(json.dumps({'type': 'result', 'session_id': sid, 'structured_output': {'message': 'Seen', 'code': code}}))
""".replace('CODE', repr(image_code)))
    claude.chmod(0o755)
    dock.session.new_chat('claude')
    dock.session.options['executable'] = str(claude)
    dock.session.options['approval_mode'] = 'full_auto'
    for text in ['look', 'again']:
        dock.input.setPlainText(text)
        dock.submit()
        wait_until(lambda: not dock.session.running)
    calls = [json.loads(line) for line in claude.with_name('calls.jsonl').read_text().splitlines()]
    assert [call['png'] for call in calls] == [[], [True], []], dock.transcript.toPlainText()
    bridge = calls[1]['prompt']['conversation'][-1]
    assert bridge['role'] == 'bridge' and bridge['content']['ok']
    assert len(bridge['content']['attached_images']) == 1
    assert 'エージェントに見せた画像: ' + bridge['content']['attached_images'][0] in dock.transcript.toPlainText()

    codex = Path(directory) / 'view-codex'
    codex.write_text("#!/usr/bin/env python3\n" + r"""
import json, sys
from pathlib import Path
json.load(sys.stdin)
images = [sys.argv[i + 1] for i, arg in enumerate(sys.argv) if arg == '--image']
assert all(Path(image).is_file() for image in images)
assert not images or sys.argv.index('--image') < sys.argv.index('--json')
resumed = sys.argv[2] == 'resume'
sid = '0199a213-81c0-7800-8aa1-bbab2a035a54'
if resumed:
    assert sys.argv[-2] == sid
with Path(__file__).with_name('codex.jsonl').open('a') as f:
    f.write(json.dumps({'images': images, 'resume': resumed}) + '\n')
print(json.dumps({'type': 'thread.started', 'thread_id': sid}), flush=True)
code = '' if resumed else CODE
print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps({'message': 'Seen', 'code': code})}}), flush=True)
print(json.dumps({'type': 'turn.completed'}), flush=True)
""".replace('CODE', repr(image_code)))
    codex.chmod(0o755)
    dock.session.new_chat('codex')
    dock.session.options['codex_executable'] = str(codex)
    dock.session.options['approval_mode'] = 'full_auto'
    dock.input.setPlainText('look')
    dock.submit()
    wait_until(lambda: not dock.session.running)
    calls = [json.loads(line) for line in codex.with_name('codex.jsonl').read_text().splitlines()]
    assert [(call['resume'], len(call['images'])) for call in calls] == [(False, 0), (True, 1)], dock.transcript.toPlainText()
    assert calls[1]['images'][0].endswith('.png')
    dock.reset.menu().actions()[0].trigger()

if "--inventory-screenshot" in sys.argv:
    from qgis.PyQt.QtWidgets import QTabWidget
    inventory_dialog = SettingsDialog(dock.session.options)
    inventory_dialog.show()
    inventory_dialog.provider_tabs.setCurrentWidget(inventory_dialog.provider_pages["claude"])
    inventory_dialog.provider_pages["claude"].setCurrentIndex(1)
    app.processEvents()
    inventory_dialog.grab().save("/tmp/geotaro-skills.png")
    inventory_dialog.provider_pages["claude"].setCurrentIndex(2)
    app.processEvents()
    inventory_dialog.grab().save("/tmp/geotaro-connectors.png")
    inventory_dialog.provider_tabs.setCurrentWidget(inventory_dialog.provider_pages["codex"])
    inventory_dialog.provider_pages["codex"].setCurrentIndex(1)
    app.processEvents()
    inventory_dialog.grab().save("/tmp/geotaro-codex-skills.png")
    inventory_dialog.reject()

# A large archive stays searchable without filling the dock selector.
from geotaro_test.ui.session_picker import SessionPicker
archive_payload = {'version': 1, 'history': [], 'messages': [], 'model': 'claude-opus-5', 'draft': ''}
archived_id = dock.session.store.save(None, 'Archive target', archive_payload)
for index in range(60):
    dock.session.store.save(None, f'Archive {index}', archive_payload)
dock.refresh_sessions()
assert dock.sessions.count() == 25
assert dock.sessions.findData(archived_id) == -1
picker = SessionPicker(dock.session.store, dock)
assert picker.results.count() == 50 and picker.more.isEnabled()
picker.more.click()
assert picker.results.count() >= 61
picker.search.setText('Archive target')
assert picker.results.count() == 1 and picker.results.item(0).text() == 'Archive target'
picker.results.setCurrentRow(0)
picker.open_selected()
assert picker.selected_id == archived_id
# Several selected rows delete together; opening with several selected picks the last one.
picker.search.setText('Archive 5')
doomed = [picker.results.item(row).data(Qt.ItemDataRole.UserRole) for row in (0, 1)]
picker.results.item(0).setSelected(True)
picker.results.item(1).setSelected(True)
picker.open_selected()
assert picker.selected_id == picker.results.selectedItems()[-1].data(Qt.ItemDataRole.UserRole)
QMessageBox.question = lambda *args: QMessageBox.StandardButton.Yes
try:
    picker.delete_button.click()
finally:
    QMessageBox.question = original_question
assert not any(dock.session.store.exists(session_id) for session_id in doomed)
picker.deleteLater()
def select_archived():
    dialog = next(child for child in dock.findChildren(SessionPicker) if child.isVisible())
    dialog.search.setText('Archive target')
    dialog.results.setCurrentRow(0)
    dialog.open_selected()
QTimer.singleShot(0, select_archived)
dock.open_session_picker()
assert dock.session.session_id == archived_id and dock.sessions.findData(archived_id) >= 0
dock.session.on_usage_updated({'tokens': 100_000, 'model': 'claude-opus-5', 'source': 'request'})
assert '10.0%' in dock.context_ring.toolTip()
assert '100,000 / 1,000,000' in dock.context_ring.toolTip()
assert dock.context_ring.value == 100
assert dock.input.geometry().bottom() < dock.context_ring.geometry().top()
assert dock.context_ring.geometry().left() < dock.approval_selector.geometry().left()
assert dock.approval_selector.geometry().left() < dock.model_selector.geometry().left()
assert dock.model_selector.geometry().left() < dock.effort_selector.geometry().left()
assert dock.effort_selector.geometry().left() < dock.fast_mode.geometry().left()
assert dock.fast_mode.geometry().right() < dock.input.geometry().right() - 20
assert abs(dock.send.geometry().center().y() - dock.context_ring.geometry().center().y()) <= 2
dock.set_busy(True)
app.processEvents()
assert not dock.stop.isHidden() and dock.send.isHidden()
assert abs(dock.stop.geometry().center().y() - dock.context_ring.geometry().center().y()) <= 2
dock.set_busy(False)
assert dock.session.save() and dock.session.store.load(archived_id)['context_usage']['tokens'] == 100_000

# Heavy Processing runs on a QgsTask; the bridge reports it after the task finishes.
from qgis.core import (QgsFeature, QgsGeometry, QgsPointXY, QgsProcessingAlgorithm,
                       QgsProcessingProvider, QgsVectorLayer)
from qgis.analysis import QgsNativeAlgorithms
if QgsApplication.processingRegistry().providerById('native') is None:
    QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())


class WaitForCancel(QgsProcessingAlgorithm):
    def name(self): return 'wait_for_cancel'
    def displayName(self): return 'Wait for cancel'
    def createInstance(self): return WaitForCancel()
    def initAlgorithm(self, config=None): pass
    def processAlgorithm(self, parameters, context, feedback):
        while not feedback.isCanceled():
            time.sleep(0.01)
        return {}


class SmokeProvider(QgsProcessingProvider):
    def id(self): return 'smoke'
    def name(self): return 'Smoke'
    def loadAlgorithms(self): self.addAlgorithm(WaitForCancel())


smoke_provider = SmokeProvider()
QgsApplication.processingRegistry().addProvider(smoke_provider)
points = QgsVectorLayer('Point?crs=EPSG:3857', 'background input', 'memory')
feature = QgsFeature()
feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
points.dataProvider().addFeatures([feature])
QgsProject.instance().addMapLayer(points)
dock.session.new_chat()
QMessageBox.warning = lambda *args: QMessageBox.StandardButton.Yes
dock.approval_selector.setCurrentIndex(dock.approval_selector.findData("full_auto"))
QMessageBox.warning = original_warning
dock.session.continuation.timeout.disconnect()
dock.session.set_running(True)
dock.session.on_response({"message": "buffer", "title": "", "requires_approval": False, "approval_reason": "",
                  "code": "job = run_processing_in_background('native:buffer', {'INPUT': %r, "
                          "'DISTANCE': 10, 'OUTPUT': 'TEMPORARY_OUTPUT'})\nprint('started')" % points.id()})
assert dock.session.job is not None and dock.session.running and dock.session.history[-1]["content"]["output"] == "started\n"
assert not dock.wait_indicator.isHidden() and not dock.stop.isHidden()
wait_until(lambda: dock.session.job is None)
report = dock.session.history[-1]["content"]["background_processing"]
assert report["ok"] and not report["canceled"] and report["algorithm"] == "native:buffer"
assert report["results"]["OUTPUT"]["feature_count"] == 1
# Stateless code finds the result in the project, so the bridge adds it there.
output = QgsProject.instance().mapLayer(report["results"]["OUTPUT"]["id"])
assert isinstance(output, QgsVectorLayer) and output.thread() == app.thread() and output.featureCount() == 1
# The conversation resumes; the timer is disconnected so no CLI starts.
assert dock.session.running and dock.status.text().startswith("Claude")
assert tr("Background run succeeded") in [bubble.role_key.split(" · ")[-1] for bubble in dock.transcript.messages]
dock.session.cancel()
# Stop cancels the task; its late completion must not resume the conversation.
dock.session.set_running(True)
dock.session.on_response({"message": "wait", "title": "", "requires_approval": False, "approval_reason": "",
                  "code": "job = run_processing_in_background('smoke:wait_for_cancel', {})"})
waiting = dock.session.job
wait_until(lambda: waiting.progress() == 0 and dock.session.job is waiting)
dock.session.cancel()
assert dock.session.job is None and not dock.session.running
assert dock.session.history[-1]["content"].startswith("Interaction stopped:")
wait_until(lambda: waiting.done)
assert not waiting.ok and dock.session.history[-1]["content"].startswith("Interaction stopped:")
# NoThreading algorithms and a second job in one block are rejected before starting.
for code, expected in (("run_processing_in_background('geotaro:add_tool', {})", "cannot run in the background"),
                       ("run_processing_in_background('smoke:wait_for_cancel', {})\n"
                        "run_processing_in_background('smoke:wait_for_cancel', {})", "Only one background")):
    dock.session.set_running(True)
    dock.session.on_response({"message": "reject", "title": "", "requires_approval": False,
                      "approval_reason": "", "code": code})
    result = dock.session.history[-1]["content"]
    assert not result["ok"] and expected in result["error"], result
    # The first of two jobs still starts; stopping cancels it.
    dock.session.cancel()
wait_until(lambda: not QgsApplication.taskManager().activeTasks())
dock.session.continuation.timeout.connect(dock.session.request)
QgsProject.instance().removeMapLayer(points.id())
QgsProject.instance().removeMapLayer(output.id())
QgsApplication.processingRegistry().removeProvider(smoke_provider)

if "--screenshot" in sys.argv or "--codex-screenshot" in sys.argv:
    dock.session.new_chat()
    if "--codex-screenshot" in sys.argv:
        dock.session.new_chat("codex")
        dock.model_selector.setCurrentIndex(dock.model_selector.findData("gpt-6-astra"))
    dock.session.log(tr("You"), "札幌の点を地図に追加してください。")
    dock.session.log(dock.session.agent_label, "札幌の位置にポイントを追加します。メモリレイヤーを作成し、地図の表示範囲を合わせます。",
                     "from qgis.core import QgsVectorLayer\nlayer = QgsVectorLayer('Point?crs=EPSG:4326', '札幌', 'memory')")
    dock.transcript.messages[-1].toggle.setChecked(True)
    dock.session.log("QGIS · " + tr("Run succeeded"), "ポイントを1件追加しました。")
    dock.session.log(dock.session.agent_label, "札幌のポイントを追加しました。次にどのような分析を行いますか？")
    iface.window.resize(540, 780)
    iface.window.show()
    app.processEvents()
    iface.window.grab().save("/tmp/geotaro-chat.png")
    dock.session.options["approval_mode"] = "ask"
    dock.session.set_running(True)
    dock.session.on_response({"message": "既存レイヤーの属性を更新します。", "code": "layer.startEditing()",
                      "title": "", "requires_approval": True, "approval_reason": "既存データを変更します"})
    for _ in range(50):
        app.processEvents()
        time.sleep(0.01)
    iface.window.grab().save("/tmp/geotaro-approval.png")
    dock.session.cancel()

if "--live" in sys.argv or "--live-codex" in sys.argv:
    from geotaro_test.core.agent import default_executable, default_codex_executable
    QgsProject.instance().clear()
    dock.session.new_chat()
    dock.session.options["approval_mode"] = "full_auto"
    dock.session.options["executable"] = default_executable()
    if "--live-codex" in sys.argv:
        dock.session.new_chat("codex")
        dock.session.options["codex_executable"] = default_codex_executable()
        dock.session.options["model"] = ""
    dock.input.setPlainText("動作検証です。EPSG:4326のメモリポイントレイヤーを1つ作り、名前をAgent live smokeにして、札幌(141.3545, 43.0618)の点を1つ追加してください。ファイルは保存せず、他の操作は不要です。実行結果を確認したら短く完了してください。")
    dock.submit()
    wait_until(lambda: not dock.session.running, 300)
    print(dock.transcript.toPlainText(), flush=True)
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1 and layers[0].name() == "Agent live smoke"
    assert layers[0].featureCount() == 1
    point = next(layers[0].getFeatures()).geometry().asPoint()
    assert abs(point.x() - 141.3545) < 1e-6 and abs(point.y() - 43.0618) < 1e-6
    assert dock.session.history[-1]["role"] == "assistant" and not dock.session.history[-1]["content"]["code"]
    print("PASS: live " + dock.session.agent_label + " subscription -> generated Python -> QGIS point -> final response", flush=True)

# The session core runs a full turn without a dock or iface, so other front ends can share it.
from geotaro_test.core.session import AgentSession
with tempfile.TemporaryDirectory() as directory:
    cli = Path(directory) / "core-claude"
    cli.write_text("#!/usr/bin/env python3\n" + r"""
import json, sys
p = json.load(sys.stdin)
if p['conversation'][-1]['role'] == 'user':
    assert 'qgis_context' not in p
    code = ("from qgis.core import QgsVectorLayer\nprint(iface is None)\n"
            "project.addMapLayer(QgsVectorLayer('Point?crs=EPSG:4326', 'Core only', 'memory'))")
    out = {'message': 'run', 'code': code, 'title': 'Core'}
else:
    assert p['conversation'][-1]['content']['output'] == 'True\n'
    out = {'message': 'done', 'code': ''}
print(json.dumps({'type': 'result', 'structured_output': out}))
""")
    cli.chmod(0o755)
    core = AgentSession(iface=None, session_path=Path(directory) / "core.sqlite3")
    roles = []
    core.message_added.connect(lambda index: roles.append(core.messages[index]["role"]))
    finished = []
    core.attention_needed.connect(finished.append)
    core.restore()
    core.options["executable"] = str(cli)
    core.options["approval_mode"] = "full_auto"
    count = len(QgsProject.instance().mapLayers())
    assert core.submit("Add a layer without the dock")
    wait_until(lambda: not core.running)
    assert len(QgsProject.instance().mapLayers()) == count + 1, core.messages
    assert roles == [tr("You"), "Claude", "QGIS · " + tr("Run succeeded"), "Claude"], roles
    assert core.messages[-1]["text"] == "done" and core.session_title == "Core"
    # Only the final reply ends the turn; the code step in between does not.
    assert finished == ["done"], finished
    reopened = AgentSession(iface=None, session_path=Path(directory) / "core.sqlite3")
    reopened.restore()
    assert reopened.session_id == core.session_id and reopened.agent_started
    assert [message["role"] for message in reopened.messages] == roles
    core.shutdown()
    reopened.shutdown()
    for layer in QgsProject.instance().mapLayersByName("Core only"):
        QgsProject.instance().removeMapLayer(layer.id())

# API keys are stored encrypted by QGIS and reach only the selected CLI's key variable.
from unittest.mock import patch
from qgis.PyQt.QtWidgets import QMessageBox
from geotaro_test.core import credentials
from geotaro_test.ui.chat import SettingsDialog
assert QgsApplication.authManager().setMasterPassword("geotaro-smoke", True)
for provider in ("claude", "codex"):
    credentials.remove_api_key(provider)
dialog = SettingsDialog({"executable": "claude", "claude_auth": "subscription"})
accepted = []
dialog.accepted.connect(lambda: accepted.append(True))
dialog.auth["claude"].setCurrentIndex(dialog.auth["claude"].findData("api_key"))
assert dialog.api_keys["claude"][0].isEnabled() and not dialog.api_keys["codex"][0].isEnabled()
with patch.object(QMessageBox, "warning") as warned:
    dialog.accept()
assert warned.called and not accepted
dialog.api_keys["claude"][0].setText(" sk-ant-smoke\n")
dialog.accept()
assert accepted and dialog.options()["claude_auth"] == "api_key"
assert dialog.options()["codex_auth"] == "subscription"
assert credentials.api_key("claude") == "sk-ant-smoke" and not credentials.has_api_key("codex")
assert credentials.store_api_key("codex", "sk-codex-smoke")
QSettings().sync()
stored_settings = "".join(path.read_text(errors="ignore") for path in Path(settings_dir.name).rglob("*.ini"))
assert "sk-ant-smoke" not in stored_settings and "sk-codex-smoke" not in stored_settings
with tempfile.TemporaryDirectory() as directory:
    claude = Path(directory) / "key-claude"
    claude.write_text("#!/usr/bin/env python3\n" + r"""
import json, os, sys
json.load(sys.stdin)
if os.environ.get('ANTHROPIC_API_KEY') != 'sk-ant-smoke' or 'CODEX_API_KEY' in os.environ:
    print(json.dumps({'type': 'result', 'is_error': True, 'result': 'Invalid API key · Fix external API key'}))
    sys.exit(1)
mode = '--resume' if '--resume' in sys.argv else '--session-id'
print(json.dumps({'type': 'result', 'session_id': sys.argv[sys.argv.index(mode) + 1],
                  'structured_output': {'message': 'Key OK', 'code': ''}}))
""")
    claude.chmod(0o755)
    codex = Path(directory) / "key-codex"
    codex.write_text("#!/usr/bin/env python3\n" + r"""
import json, os, sys
sys.stdin.read()
assert os.environ['CODEX_API_KEY'] == 'sk-codex-smoke' and 'ANTHROPIC_API_KEY' not in os.environ
assert 'forced_login_method="api"' in sys.argv and 'forced_login_method="chatgpt"' not in sys.argv
print(json.dumps({'type': 'thread.started', 'thread_id': '0199a213-81c0-7800-8aa1-bbab2a035a54'}), flush=True)
print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps({'message': 'Codex key OK', 'code': ''})}}), flush=True)
print(json.dumps({'type': 'turn.completed'}), flush=True)
""")
    codex.chmod(0o755)
    os.environ["ANTHROPIC_API_KEY"] = "inherited"
    keyed = AgentSession(iface=None, session_path=Path(directory) / "keys.sqlite3")
    logins = []
    keyed.login_required.connect(logins.append)
    keyed.restore()
    keyed.options.update(executable=str(claude), claude_auth="api_key", codex_executable=str(codex), codex_auth="api_key")
    assert keyed.submit("Use the Claude key")
    wait_until(lambda: not keyed.running)
    assert keyed.messages[-1]["text"] == "Key OK", keyed.messages
    # A rejected key is an error to fix in settings, not a browser sign-in prompt.
    assert credentials.store_api_key("claude", "sk-ant-wrong")
    assert keyed.submit("Use a wrong key")
    wait_until(lambda: not keyed.running)
    assert not logins and "APIキー" in keyed.messages[-1]["text"], keyed.messages
    assert credentials.remove_api_key("claude") and not credentials.has_api_key("claude")
    assert keyed.submit("Use a missing key")
    wait_until(lambda: not keyed.running)
    assert "APIキーを取得できません" in keyed.messages[-1]["text"], keyed.messages
    keyed.new_chat("codex")
    assert keyed.options["provider"] == "codex"
    assert keyed.submit("Use the Codex key")
    wait_until(lambda: not keyed.running)
    assert keyed.messages[-1]["text"] == "Codex key OK", keyed.messages
    keyed.shutdown()
    del os.environ["ANTHROPIC_API_KEY"]
    credentials.remove_api_key("codex")

# Clearing past sessions keeps the one open in the dock and updates its selector.
dock.session.start()
current_id = dock.session.session_id
assert len(dock.session.store.list()) > 1
history_dialog = SettingsDialog(dock.session.options, dock, dock.session.delete_past_sessions)
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
    history_dialog.delete_past_sessions_button.click()
assert len(dock.session.store.list()) > 1
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
    history_dialog.delete_past_sessions_button.click()
assert [row[0] for row in dock.session.store.list()] == [current_id]
assert dock.sessions.count() == 1 and dock.sessions.currentData() == current_id
history_dialog.reject()

plugin.unload()
assert not iface.actions
assert QgsApplication.processingRegistry().algorithmById('geotaro:add_tool') is None
QgsProject.instance().clear()
print("PASS: plugin lifecycle, CLI round-trip, live QGIS layer, feedback, errors, persistence, output limit, preview, failed start, cancellation")
# Avoid macOS QGIS teardown ordering issues at interpreter shutdown.
os._exit(0)
