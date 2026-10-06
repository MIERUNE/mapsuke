"""First-open skill consent is one-time; later syncing stays explicit."""
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
auth_dir = tempfile.TemporaryDirectory()
os.environ["QGIS_AUTH_DB_DIR_PATH"] = auth_dir.name
cli_dir = tempfile.TemporaryDirectory()
claude = Path(cli_dir.name) / "claude"
codex = Path(cli_dir.name) / "codex"
claude.mkdir()
codex.mkdir()
os.environ["CLAUDE_CONFIG_DIR"] = str(claude)
os.environ["CODEX_HOME"] = str(codex)

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QDockWidget, QMainWindow, QMessageBox

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("geotaro_skill_optin_test", root / "__init__.py",
                                              submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
app = QgsApplication([], False)
app.initQgis()
app.setOrganizationName("GeotaroSkillOptinTests")
app.setApplicationName("Smoke")
settings_dir = tempfile.TemporaryDirectory()
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, settings_dir.name)

from geotaro_skill_optin_test.plugin import GeotaroPlugin
from geotaro_skill_optin_test.ui.chat import SettingsDialog


class Iface:
    def __init__(self):
        self.window = QMainWindow()

    def mainWindow(self):
        return self.window

    def addPluginToMenu(self, menu, action):
        pass

    def addToolBarIcon(self, action):
        pass

    def removePluginMenu(self, menu, action):
        pass

    def removeToolBarIcon(self, action):
        pass

    def addTabifiedDockWidget(self, area, dock, tabify_with, raise_tab):
        self.window.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        self.window.removeDockWidget(dock)


class Dock(QDockWidget):
    def __init__(self, iface, session_path):
        super().__init__()

    def shutdown(self):
        pass


def open_geotaro():
    plugin.initGui()
    plugin.action.trigger()
    plugin.unload()


patch("geotaro_skill_optin_test.plugin.AgentDock", Dock).start()
plugin = GeotaroPlugin(Iface())
QSettings().setValue("geotaro/dock_open", False)
# Loading the plugin with the dock closed must not ask; opening Geotaro does.
with patch.object(QMessageBox, "question") as question:
    plugin.initGui()
    plugin.unload()
assert question.call_count == 0
assert not QSettings().value("geotaro/bundled_skills_prompted", False, type=bool)
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as question:
    open_geotaro()
    open_geotaro()
assert question.call_count == 1
assert QSettings().value("geotaro/bundled_skills_prompted", False, type=bool)
assert not (claude / "skills").exists() and not (codex / "skills").exists()

# Simulate another first open with a fresh QGIS settings profile.
QSettings().remove("geotaro/bundled_skills_prompted")
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as question:
    open_geotaro()
    open_geotaro()
assert question.call_count == 1
names = sorted(path.parent.name for path in (root / "skills").glob("*/SKILL.md"))
assert sorted(path.name for path in (claude / "skills").iterdir()) == names
assert sorted(path.name for path in (codex / "skills").iterdir()) == names

edited = claude / "skills" / names[0] / "SKILL.md"
edited.write_text("Local edit", encoding="utf-8")
missing = claude / "skills" / names[1]
shutil.rmtree(missing)
open_geotaro()
assert edited.read_text(encoding="utf-8") == "Local edit"
assert not missing.exists()

dialog = SettingsDialog({"executable": "claude"})
assert dialog.sync_skills.text() == "Sync built-in skills"
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
    dialog.sync_skills.click()
assert edited.read_text(encoding="utf-8") == "Local edit"
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
        patch.object(QMessageBox, "information"):
    dialog.sync_skills.click()
assert edited.read_text(encoding="utf-8") == (root / "skills" / names[0] / "SKILL.md").read_text(encoding="utf-8")
assert (missing / "SKILL.md").exists()

print("PASS: one-time skill consent and explicit sync")
os._exit(0)
