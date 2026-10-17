"""Focused Qt and CLI check for per-chat Claude skill and connector settings."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QDialog, QTabWidget

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
from mapsuke_test.ui.capability_tabs import CapabilityTabs

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
    assert not hasattr(capabilities, 'toggles')
    choice = capabilities.skill_choices["sample"]
    choice.setCurrentIndex(2)
    capabilities.refresh()
    assert capabilities.selected_options()["claude_skills"] == {"sample": "off"}
    assert capabilities.skill_choices["sample"].isEnabled()
    assert capabilities.selected_options()["claude_skills"] == {"sample": "off"}

    capabilities.connectors = [
        {"name": name, "status": tr("Connected"), "transport": "http", "source": source, "path": ""}
        for name, source in (("claude.ai Slack", "claude.ai"), ("plugin:example:server", "example"))]
    capabilities.populate_connectors()
    assert not capabilities.connector_choices["claude.ai Slack"].isChecked()
    capabilities.connector_choices["claude.ai Slack"].setChecked(False)
    capabilities.connector_choices["plugin:example:server"].setChecked(False)
    disabled = {"claude.ai Slack": False, "plugin:example:server": False}
    assert capabilities.selected_options()["claude_connectors"] == disabled
    capabilities.refresh()
    assert capabilities.selected_options()["claude_connectors"] == disabled
    assert capabilities.connector_choices["claude.ai Slack"].isEnabled()
    assert capabilities.selected_options()["claude_connectors"] == disabled

    # Old all-off chats start with individual exclusions, which can now be edited directly.
    legacy_owner = QDialog()
    legacy = CapabilityTabs(QTabWidget(legacy_owner), lambda: "", legacy_owner,
                            {"enable_skills": False, "enable_connectors": False,
                             "claude_skills": {"sample": "on"}})
    assert legacy.selected_skill_options()["sample"] == "off"
    assert legacy.skill_choices["sample"].isEnabled()
    legacy.skill_choices["sample"].setCurrentIndex(0)
    legacy.refresh()
    legacy.refresh()
    assert legacy.selected_skill_options() == {}
    legacy.connectors = [{"name": "claude.ai Slack", "status": tr("Not checked"),
                          "transport": "http", "source": "claude.ai", "path": ""}]
    legacy.populate_connectors()
    assert legacy.selected_connector_options() == {"claude.ai Slack": False}
    legacy.connector_choices["claude.ai Slack"].setChecked(True)
    legacy.populate_connectors()
    assert legacy.selected_connector_options() == {}
    assert legacy.selected_options()['enable_skills'] and legacy.selected_options()['enable_connectors']
    legacy.close()

    store = SessionStore(root / "sessions.sqlite3")
    payload = {"version": 1, "history": [], "messages": [], "claude_skills": {"sample": "off"}, "claude_connectors": disabled}
    session_id = store.save(None, "Skills", payload)
    assert store.load(session_id)["claude_skills"] == {"sample": "off"}
    assert store.load(session_id)["claude_connectors"] == disabled
    restored_owner = QDialog()
    restored = CapabilityTabs(QTabWidget(restored_owner), lambda: "", restored_owner,
                              dict(store.load(session_id), enable_connectors=True))
    assert restored.selected_connector_options() == disabled
    assert all(not choice.isChecked() for choice in restored.connector_choices.values())
    restored.close()
    store.close()

    cli = root / "fake-claude"
    cli.write_text("#!/usr/bin/env python3\n" + r'''
import json, sys
from pathlib import Path
args = sys.argv
settings = json.loads(args[args.index('--settings') + 1])
Path(__file__).with_name('seen.json').write_text(json.dumps(settings), encoding='utf-8')
Path(__file__).with_name('seen-args.json').write_text(json.dumps(args), encoding='utf-8')
mode = '--resume' if '--resume' in args else '--session-id'
sid = args[args.index(mode) + 1]
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
        choice.setChecked(True)
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
    # Search alone must work independently of the legacy skill/connector gates.
    search_session = str(uuid4())
    for enabled in (False, True):
        completed.clear()
        agent.request(str(cli), "search", session_id=search_session, resume=enabled, web_search=enabled)
        deadline = time.monotonic() + 10
        while not (completed or failed) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert completed and not failed, failed
        args = json.loads(cli.with_name('seen-args.json').read_text())
        assert args[args.index('--tools') + 1] == ('default' if enabled else '')
        if enabled:
            assert args[args.index('--allowedTools') + 1] == 'WebSearch'
            assert args[args.index('--permission-mode') + 1] == 'dontAsk'
            assert '--disallowedTools' not in args
        else:
            assert args[args.index('--disallowedTools') + 1] == 'WebSearch'
            assert '--allowedTools' not in args
        assert '--dangerously-skip-permissions' not in args

    capabilities.refresh()
    capabilities.refresh()
    assert capabilities.selected_connector_options() == {}
    assert not (root / "claude/settings.json").exists()

    # Removing Claude master switches must not change Codex global defaults.
    from mapsuke_test.core.session import AgentSession
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(root / 'settings'))
    defaults = {'connectors': {'test_server': False}}
    QSettings().setValue('mapsuke/codex_capabilities', json.dumps(defaults))
    QSettings().setValue('mapsuke/enable_skills', False)
    QSettings().setValue('mapsuke/enable_connectors', False)
    session = AgentSession(session_path=root / 'chat.sqlite3')
    assert session.options['enable_skills'] and session.options['enable_connectors']
    assert session.options['codex_capabilities'] == defaults
    session.update_settings(capabilities.selected_options())
    assert not QSettings().value('mapsuke/enable_skills', True, type=bool)
    assert not QSettings().value('mapsuke/enable_connectors', True, type=bool)
    session.start()
    assert session.options['enable_skills'] and session.options['enable_connectors']
    assert session.options['codex_capabilities'] == defaults
    session.shutdown()

print("Claude individual controls, legacy flags, Codex defaults, persistence and CLI overrides passed")
