"""Focused Qt and CLI check for per-chat Claude skill settings."""
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
from qgis.PyQt.QtWidgets import QDialog, QTabWidget

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("geotaro_test", ROOT / "__init__.py",
                                              submodule_search_locations=[str(ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
app = QgsApplication([], False)
app.initQgis()

from geotaro_test.core.agent import AgentProcess
from geotaro_test.core.session_store import SessionStore
from geotaro_test.i18n import tr
from geotaro_test.ui.capability_tabs import CapabilityTabs

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

    store = SessionStore(root / "sessions.sqlite3")
    payload = {"version": 1, "history": [], "messages": [], "claude_skills": {"sample": "off"}}
    session_id = store.save(None, "Skills", payload)
    assert store.load(session_id)["claude_skills"] == {"sample": "off"}
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
                  claude_skills=capabilities.selected_skill_options())
    deadline = time.monotonic() + 10
    while not (completed or failed) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert completed and not failed, failed
    assert json.loads(cli.with_name("seen.json").read_text())["skillOverrides"] == {"sample": "off"}
    for index, expected in ((1, {"sample": "on"}), (0, {})):
        capabilities.skill_choices["sample"].setCurrentIndex(index)
        completed.clear()
        agent.request(str(cli), "hello", session_id=str(uuid4()), enable_skills=True,
                      claude_skills=capabilities.selected_skill_options())
        deadline = time.monotonic() + 10
        while not (completed or failed) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert completed and not failed, failed
        settings = json.loads(cli.with_name("seen.json").read_text())
        assert settings.get("skillOverrides", {}) == expected
    assert not (root / "claude/settings.json").exists()

print("Claude skill controls and CLI override passed")
