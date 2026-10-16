"""Focused Qt and CLI check for per-chat Claude skill and connector settings."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from uuid import uuid4
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QDialog, QTabWidget, QPushButton

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mapsuke_test", ROOT / "__init__.py",
                                              submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
app = QgsApplication([], False)
app.initQgis()
sys.path.insert(0, str(Path(QgsApplication.pkgDataPath()) / "python/plugins"))

from mapsuke_test.core.agent import AgentProcess
from mapsuke_test.core.session_store import SessionStore
from mapsuke_test.i18n import tr
from mapsuke_test.ui.capability_tabs import CapabilityTabs, CodexCapabilityTabs

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    os.environ["CLAUDE_CONFIG_DIR"] = str(root / "claude")
    skill = root / "claude/skills/sample/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: sample\ndescription: Sample\n---\n", encoding="utf-8")
    plugin = root / "claude/plugins/cache/example/1.0"
    plugin_skill = plugin / "skills/plugin-sample/SKILL.md"
    plugin_skill.parent.mkdir(parents=True)
    plugin_skill.write_text("---\ndescription: Plugin sample\n---\n", encoding="utf-8")
    registry = root / "claude/plugins/installed_plugins.json"
    registry.write_text(json.dumps({"plugins": {"example@market": [
        {"installPath": str(plugin), "scope": "user"}]}}), encoding="utf-8")
    owner = QDialog()
    tabs = QTabWidget(owner)
    capabilities = CapabilityTabs(tabs, lambda: "", owner,
                                  {"enable_skills": True, "enable_connectors": False})
    assert "sample" in capabilities.skill_choices
    assert "example:plugin-sample" not in capabilities.skill_choices
    choice = capabilities.skill_choices["sample"]
    choice.setCurrentIndex(2)
    capabilities.refresh()
    assert capabilities.selected_options()["claude_skills"] == {"sample": "off"}
    capabilities.toggles["enable_skills"].setChecked(False)
    assert not capabilities.skill_choices["sample"].isEnabled()
    capabilities.toggles["enable_skills"].setChecked(True)
    assert capabilities.selected_options()["claude_skills"] == {"sample": "off"}

    capabilities.connectors = [
        {"name": name, "status": tr("Connected"), "transport": "http", "source": source, "path": ""}
        for name, source in (("claude.ai Slack", "claude.ai"), ("plugin:example:server", "example"))]
    capabilities.populate_connectors()
    capabilities.toggles["enable_connectors"].setChecked(True)
    capabilities.connector_choices["claude.ai Slack"].setCurrentIndex(2)
    capabilities.connector_choices["plugin:example:server"].setCurrentIndex(2)
    disabled = {"claude.ai Slack": False, "plugin:example:server": False}
    assert capabilities.selected_options()["claude_connectors"] == disabled
    capabilities.refresh()
    assert capabilities.selected_options()["claude_connectors"] == disabled
    capabilities.toggles["enable_connectors"].setChecked(False)
    assert not capabilities.connector_choices["claude.ai Slack"].isEnabled()
    capabilities.toggles["enable_connectors"].setChecked(True)
    assert capabilities.selected_options()["claude_connectors"] == disabled

    store = SessionStore(root / "sessions.sqlite3")
    payload = {"version": 1, "history": [], "messages": [], "claude_skills": {"sample": "off"}, "claude_connectors": disabled}
    session_id = store.save(None, "Skills", payload)
    assert store.load(session_id)["claude_skills"] == {"sample": "off"}
    assert store.load(session_id)["claude_connectors"] == disabled
    restored_owner = QDialog()
    restored = CapabilityTabs(QTabWidget(restored_owner), lambda: "", restored_owner,
                              dict(store.load(session_id), enable_connectors=True))
    assert restored.selected_connector_options() == disabled
    assert all(choice.currentData() is False for choice in restored.connector_choices.values())
    restored.close()
    store.close()

    cli = root / "fake-claude"
    cli.write_text("#!/usr/bin/env python3\n" + r'''
import json, sys
from pathlib import Path
args = sys.argv
settings = json.loads(args[args.index('--settings') + 1])
Path(__file__).with_name('seen.json').write_text(json.dumps(settings), encoding='utf-8')
sid = args[args.index('--session-id') + 1]
print(json.dumps({'type': 'result', 'session_id': sid,
                  'structured_output': {'message': 'OK', 'code': ''}}))
''', encoding="utf-8")
    cli.chmod(0o755)
    agent = AgentProcess(None, root / "workdir")
    completed, failed = [], []
    agent.completed.connect(completed.append)
    agent.failed.connect(failed.append)
    agent.request(str(cli), "hello", session_id=str(uuid4()), enable_skills=True,
                  claude_skills=capabilities.selected_skill_options(),
                  enable_connectors=True, claude_connectors=capabilities.selected_connector_options())
    deadline = time.monotonic() + 10
    while not (completed or failed) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert completed and not failed, failed
    assert json.loads(cli.with_name("seen.json").read_text())["skillOverrides"] == {"sample": "off"}
    assert json.loads(cli.with_name("seen.json").read_text())["deniedMcpServers"] == [
        {"serverName": name} for name in disabled]
    for choice in capabilities.connector_choices.values():
        choice.setCurrentIndex(0)
    for index, expected in ((1, {"sample": "on"}), (0, {})):
        capabilities.skill_choices["sample"].setCurrentIndex(index)
        completed.clear()
        agent.request(str(cli), "hello", session_id=str(uuid4()), enable_skills=True,
                      claude_skills=capabilities.selected_skill_options(),
                      enable_connectors=True, claude_connectors=capabilities.selected_connector_options())
        deadline = time.monotonic() + 10
        while not (completed or failed) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert completed and not failed, failed
        settings = json.loads(cli.with_name("seen.json").read_text())
        assert settings.get("skillOverrides", {}) == expected
        assert "deniedMcpServers" not in settings
    capabilities.refresh()
    capabilities.refresh()
    assert capabilities.selected_connector_options() == {}
    capabilities.connectors = [{"name": "claude.ai Slack", "source": "claude.ai"}]
    capabilities.populate_connectors()
    capabilities.connector_choices["claude.ai Slack"].setCurrentIndex(1)
    assert capabilities.selected_connector_options() == {"claude.ai Slack": True}
    assert not (root / "claude/settings.json").exists()

# Both providers share choice labels, ordering, column names, and refresh behavior.
    inventory = {'skills': [{'id': '/tmp/example/SKILL.md', 'name': 'Example', 'description': 'Test'}],
                 'connectors': [{'id': 'test_server', 'name': 'test_server', 'description': 'MCP'},
                                {'id': 'unsupported.name', 'name': 'unsupported.name', 'description': 'MCP'}],
                 'warnings': []}
    codex_owner = QDialog()
    with patch('mapsuke_test.core.capabilities.read_codex_inventory', return_value=inventory):
        codex = CodexCapabilityTabs(QTabWidget(codex_owner), {})
        controls = [capabilities.skill_choices['sample'], capabilities.connector_choices['claude.ai Slack'],
                    codex.controls[('skills', '/tmp/example/SKILL.md')],
                    codex.controls[('connectors', 'test_server')]]
        expected_labels = [tr('Follow CLI settings'), tr('Enable'), tr('Disable')]
        for control in controls:
            assert [control.itemText(i) for i in range(control.count())] == expected_labels
            assert [control.itemData(i) for i in range(control.count())] == [None, True, False]
        for table in (capabilities.skill_table, capabilities.connector_table, *codex.tables.values()):
            assert table.horizontalHeaderItem(table.columnCount() - 1).text() == tr('This chat')
        codex.controls[('skills', '/tmp/example/SKILL.md')].setCurrentIndex(1)
        codex.controls[('connectors', 'test_server')].setCurrentIndex(2)
        assert ('connectors', 'unsupported.name') not in codex.controls
        codex.pages['skills'].findChild(QPushButton).click()
        assert codex.selected_options() == {'skills': {'/tmp/example/SKILL.md': True},
                                            'connectors': {'test_server': False}}
        inventory['connectors'] = []
        codex.refresh()
        assert codex.selected_options()['connectors'] == {'test_server': False}
        codex.controls[('connectors', 'test_server')].setCurrentIndex(0)
        codex.refresh()
        codex.refresh()
        assert codex.selected_options()['connectors'] == {}

    # Choices belong to the saved chat, including older saved Codex overrides.
    from mapsuke_test.core.session import AgentSession
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(root / 'settings'))
    QSettings().setValue('mapsuke/codex_capabilities', json.dumps({'connectors': {'legacy_default': False}}))
    session = AgentSession(session_path=root / 'chat.sqlite3')
    assert session.options['codex_capabilities'] == {}
    choices = {'codex_capabilities': {'skills': {'/tmp/example/SKILL.md': True}},
               'claude_skills': {'sample': 'off'}, 'claude_connectors': {'claude.ai Slack': False}}
    session.update_settings(choices)
    saved_id = session.session_id
    # Global defaults must not be overwritten by changes to one chat.
    assert json.loads(QSettings().value('mapsuke/codex_capabilities')) == {'connectors': {'legacy_default': False}}
    session.start()
    for key in choices:
        assert session.options[key] == {}
    session.load(saved_id)
    for key, value in choices.items():
        assert session.options[key] == value
    session.shutdown()

print("Shared capability controls, refresh, chat persistence, and Claude CLI overrides passed")
