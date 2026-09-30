"""Exercise endpoint settings and model selection in the installed QGIS Qt runtime."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
auth_dir = tempfile.TemporaryDirectory()
os.environ["QGIS_AUTH_DB_DIR_PATH"] = auth_dir.name
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QSettings
import qgis

sys.path.insert(0, str(Path(qgis.__file__).resolve().parents[1] / "plugins"))

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("qtaro_endpoint_ui_test", root / "__init__.py",
                                              submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
app = QgsApplication([], False)
app.initQgis()
sys.path.insert(0, str(Path(QgsApplication.pkgDataPath()) / "python/plugins"))
app.setOrganizationName("QtaroEndpointTests")
app.setApplicationName("Smoke")
settings_dir = tempfile.TemporaryDirectory()
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, settings_dir.name)

from qtaro_endpoint_ui_test.core.session import AgentSession
from qtaro_endpoint_ui_test.ui.chat import SettingsDialog

session = AgentSession(session_path=Path(settings_dir.name) / "sessions.sqlite3")
session.restore()
dialog = SettingsDialog(session.options)
if "--screenshot" in sys.argv:
    dialog.provider_tabs.setCurrentWidget(dialog.provider_pages["claude"])
    dialog.show()
    app.processEvents()
    dialog.grab().save("/tmp/qtaro-endpoint-settings-default.png")
for provider, mode in (("claude", "custom"), ("codex", "amazon-bedrock-runtime")):
    assert not dialog.connection_toggles[provider].isChecked()
    assert dialog.connection_fields[provider].isHidden()
    dialog.connection_toggles[provider].setChecked(True)
    assert not dialog.connection_fields[provider].isHidden()
    selector = dialog.endpoints[provider]
    selector.setCurrentIndex(selector.findData(mode))
    assert selector.currentData() == mode
dialog.base_urls["claude"].setText("https://claude.example.test")
dialog.custom_models["claude"].setText("claude-test")
dialog.custom_models["codex"].setText("global.openai.gpt-6-sol")
if "--screenshot" in sys.argv:
    dialog.provider_tabs.setCurrentWidget(dialog.provider_pages["claude"])
    dialog.show()
    app.processEvents()
    dialog.grab().save("/tmp/qtaro-endpoint-settings.png")
assert dialog.base_urls["claude"].isEnabled()
assert not dialog.base_urls["codex"].isEnabled()
assert not dialog.auth["codex"].isEnabled()
values = dialog.options()
assert values["claude_endpoint"] == "custom"
assert values["codex_endpoint"] == "amazon-bedrock-runtime"
session.agent_started = True
session.native_session_id = "old-cli-session"
session.update_settings(values)
assert session.options["model"] == ""
assert not session.agent_started and session.native_session_id != "old-cli-session"
assert session.options["claude_custom_model"] == "claude-test"
assert QSettings().value("qtaro/claude_base_url") == "https://claude.example.test"
restored = SettingsDialog(session.options)
assert restored.connection_toggles["claude"].isChecked()
assert restored.connection_toggles["codex"].isChecked()
assert not restored.connection_fields["claude"].isHidden()
restored.close()
session.shutdown()
dialog.close()
print("PASS: endpoint settings UI and persistence")
os._exit(0)
