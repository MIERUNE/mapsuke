"""Each chat refreshes existing bundled skills and asks before creating missing ones."""
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
os.environ["CLAUDE_CONFIG_DIR"] = str(claude)
os.environ["CODEX_HOME"] = str(codex)

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QMainWindow, QMessageBox

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mapsuke_skill_optin_test", root / "__init__.py",
                                              submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
app = QgsApplication([], False)
app.initQgis()
import qgis
sys.path.insert(0, str(Path(qgis.__file__).resolve().parents[1] / "plugins"))
sys.path.insert(0, str(Path(QgsApplication.pkgDataPath()) / "python/plugins"))
app.setOrganizationName("MapsukeSkillOptinTests")
app.setApplicationName("Smoke")
settings_dir = tempfile.TemporaryDirectory()
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, settings_dir.name)
QSettings().setValue("mapsuke/executable", "")
QSettings().setValue("mapsuke/codex_executable", "")
# The old first-open answer must no longer suppress per-session offers.
QSettings().setValue("mapsuke/bundled_skills_prompted", True)

from mapsuke_skill_optin_test.plugin import MapsukePlugin
from mapsuke_skill_optin_test.ui.chat import SettingsDialog
from mapsuke_skill_optin_test.core.protocol import sync_bundled_skills


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


plugin = MapsukePlugin(Iface(), Path(settings_dir.name) / "sessions.sqlite3")
QSettings().setValue("mapsuke/dock_open", False)
with patch.object(QMessageBox, "question") as question:
    plugin.initGui()
assert question.call_count == 0
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as question:
    plugin.show()
    plugin.show()
assert question.call_count == 0  # No CLI: do not offer skills or create its configuration.
assert not claude.exists() and not codex.exists()
session = plugin.dock.session
session.options.update(executable=sys.executable, codex_executable=sys.executable)
QSettings().setValue("mapsuke/executable", sys.executable)
QSettings().setValue("mapsuke/codex_executable", sys.executable)
# An executable alone does not establish a user configuration directory.
with patch.object(QMessageBox, "question") as question:
    session.start("claude")
assert question.call_count == 0 and not claude.exists()
claude.mkdir()

# Explicitly starting a fresh chat offers again after declining or dismissing.
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as question:
    session.new_chat("claude")
    session.start("claude")
assert question.call_count == 2
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as question:
    session.start("claude")
assert question.call_count == 1
names = sorted(path.parent.name for path in (root / "skills").glob("*/SKILL.md"))
body = question.call_args.args[2]
assert "Claude" in body and str(claude / "skills") in body
assert all(name in body for name in names)
assert sorted(path.name for path in (claude / "skills").iterdir()) == names
assert not codex.exists()

edited = claude / "skills" / names[0] / "SKILL.md"
edited.write_text("Local edit", encoding="utf-8")
session.options["executable"] = "/missing/claude"
with patch.object(QMessageBox, "question") as question:
    session.start("claude")
assert question.call_count == 0 and edited.read_text() == "Local edit"
session.options["executable"] = sys.executable
with patch.object(QMessageBox, "question") as question:
    session.start("claude")
assert question.call_count == 0
assert edited.read_bytes() == (root / "skills" / names[0] / "SKILL.md").read_bytes()

# Existing copies are refreshed even when creation of missing skills is declined.
missing = claude / "skills" / names[1]
shutil.rmtree(missing)
edited.write_text("Another edit", encoding="utf-8")
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as question:
    session.new_chat("claude")
assert question.call_count == 1 and not missing.exists()
assert edited.read_bytes() == (root / "skills" / names[0] / "SKILL.md").read_bytes()
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as question:
    session.new_chat("claude")
assert question.call_count == 1
body = question.call_args.args[2]
assert names[1] in body and names[0] not in body
assert edited.read_bytes() == (root / "skills" / names[0] / "SKILL.md").read_bytes()
assert (missing / "SKILL.md").read_text(encoding="utf-8") == (root / "skills" / names[1] / "SKILL.md").read_text(encoding="utf-8")

with patch.object(QMessageBox, "question") as question:
    session.new_chat("codex")
assert question.call_count == 0 and not codex.exists()
codex.mkdir()
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as question:
    session.new_chat("codex")
assert question.call_count == 1 and "Codex" in question.call_args.args[2]
assert not (codex / "skills").exists()
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
    session.start("codex")
codex_id = session.session_id
assert sorted(path.name for path in (codex / "skills").iterdir()) == names
assert edited.read_bytes() == (root / "skills" / names[0] / "SKILL.md").read_bytes()

# Restoring a saved chat, including reopening QGIS, checks its provider again.
shutil.rmtree(codex / "skills" / names[0])
with patch.object(QMessageBox, "question") as question:
    session.start("claude")
assert question.call_count == 0
codex_edited = codex / "skills" / names[1] / "SKILL.md"
codex_edited.write_text("Local edit", encoding="utf-8")
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as question:
    session.load(codex_id)
assert question.call_count == 1
assert codex_edited.read_bytes() == (root / "skills" / names[1] / "SKILL.md").read_bytes()
plugin.unload()
codex_edited.write_text("Changed while closed", encoding="utf-8")
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as question:
    plugin.initGui()
assert question.call_count == 1
session = plugin.dock.session
assert session.options["provider"] == "codex"
assert codex_edited.read_bytes() == (root / "skills" / names[1] / "SKILL.md").read_bytes()

# An installation failure leaves the chat usable and missing skills can be retried.
with patch("mapsuke_skill_optin_test.core.protocol.sync_bundled_skills", side_effect=PermissionError("read only")), \
        patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
        patch.object(QMessageBox, "warning") as warning:
    session.start("codex")
assert warning.call_count == 1 and "read only" in warning.call_args.args[2]
assert session.session_id and sync_bundled_skills("codex", sys.executable)
with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as question:
    session.start("codex")
assert question.call_count == 1 and not sync_bundled_skills("codex", sys.executable)
with patch.object(QMessageBox, "question") as question:
    session.start("codex")
assert question.call_count == 0

dialog = SettingsDialog(session.options)
assert not hasattr(dialog, "sync_skills")
dialog.close()
plugin.unload()
print("PASS: CLI/config checks, per-session consent, provider isolation, restore, automatic refresh, and retry")
os._exit(0)
