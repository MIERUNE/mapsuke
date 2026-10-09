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
from qgis.PyQt.QtCore import QSettings, Qt
import qgis

sys.path.insert(0, str(Path(qgis.__file__).resolve().parents[1] / "plugins"))

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mapsuke_endpoint_ui_test", root / "__init__.py",
                                              submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
app = QgsApplication([], False)
app.initQgis()
sys.path.insert(0, str(Path(QgsApplication.pkgDataPath()) / "python/plugins"))
app.setOrganizationName("MapsukeEndpointTests")
app.setApplicationName("Smoke")
settings_dir = tempfile.TemporaryDirectory()
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, settings_dir.name)
QSettings().setValue("locale/overrideFlag", True)
QSettings().setValue("locale/userLocale", "ja_JP")

from mapsuke_endpoint_ui_test.core.session import AgentSession
from mapsuke_endpoint_ui_test.ui.chat import SettingsDialog
from mapsuke_endpoint_ui_test.i18n import tr
from qgis.PyQt.QtWidgets import QFormLayout, QMainWindow

session = AgentSession(session_path=Path(settings_dir.name) / "sessions.sqlite3")
session.restore()
dialog = SettingsDialog(session.options)
for provider in ("claude", "codex"):
    form = dialog.provider_pages[provider].widget(0).layout().itemAt(0).layout()
    assert isinstance(form, QFormLayout)
    rows = [form.labelForField(widget).text() for widget in
            (dialog.endpoints[provider], dialog.auth[provider])]
    assert rows == [tr("Model service"), tr("Authentication")], rows
    assert form.getWidgetPosition(dialog.endpoints[provider])[0] < form.getWidgetPosition(dialog.auth[provider])[0]
    assert [dialog.auth[provider].itemData(i) for i in range(dialog.auth[provider].count())] == [
        "subscription", "api_key"]
    assert dialog.auth[provider].isEnabled()
    assert dialog.base_urls[provider].isHidden()
    assert dialog.api_key_rows[provider].isHidden()
    assert dialog.custom_models[provider].isHidden()
# Changing the inactive provider must clear its saved model without resetting this chat.
session.set_model("claude-sonnet-5")
QSettings().setValue("mapsuke/codex_model", "gpt-6-astra")
session.agent_started = True
session.native_session_id = "active-claude"
session.update_settings({"codex_endpoint": "amazon-bedrock-runtime"})
assert session.options["model"] == "claude-sonnet-5"
assert session.agent_started and session.native_session_id == "active-claude"
assert QSettings().value("mapsuke/codex_model") == ""
session.agent_started = False
if "--screenshot" in sys.argv:
    dialog.provider_tabs.setCurrentWidget(dialog.provider_pages["claude"])
    dialog.show()
    app.processEvents()
    dialog.grab().save("/tmp/mapsuke-endpoint-settings-default.png")
for provider, mode in (("claude", "custom"), ("codex", "amazon-bedrock-runtime")):
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
    dialog.grab().save("/tmp/mapsuke-endpoint-settings.png")
assert dialog.base_urls["claude"].isEnabled()
assert not dialog.base_urls["claude"].isHidden()
assert not dialog.custom_models["claude"].isHidden()
assert dialog.base_urls["codex"].isHidden()
assert dialog.auth["claude"].currentData() == "api_key"
assert not dialog.api_key_rows["claude"].isHidden()
assert dialog.auth["codex"].currentData() == "aws"
assert dialog.api_key_rows["codex"].isHidden()
assert dialog.auth["codex"].isEnabled()
dialog.endpoints["codex"].setCurrentIndex(dialog.endpoints["codex"].findData("custom"))
assert dialog.auth["codex"].currentData() == "api_key"
assert not dialog.base_urls["codex"].isHidden() and not dialog.api_key_rows["codex"].isHidden()
dialog.endpoints["codex"].setCurrentIndex(dialog.endpoints["codex"].findData("amazon-bedrock"))
assert dialog.auth["codex"].currentData() == "aws" and dialog.api_key_rows["codex"].isHidden()
dialog.endpoints["codex"].setCurrentIndex(dialog.endpoints["codex"].findData("amazon-bedrock-runtime"))
if "--screenshot" in sys.argv:
    dialog.provider_tabs.setCurrentWidget(dialog.provider_pages["codex"])
    app.processEvents()
    dialog.grab().save("/tmp/mapsuke-endpoint-settings-bedrock.png")
values = dialog.options()
assert values["claude_endpoint"] == "custom"
assert values["codex_endpoint"] == "amazon-bedrock-runtime"
assert values["claude_auth"] == "subscription" and values["codex_auth"] == "subscription"
dialog.endpoints["claude"].setCurrentIndex(dialog.endpoints["claude"].findData("default"))
dialog.auth["claude"].setCurrentIndex(dialog.auth["claude"].findData("api_key"))
dialog.endpoints["claude"].setCurrentIndex(dialog.endpoints["claude"].findData("custom"))
assert dialog.options()["claude_auth"] == "api_key"
dialog.endpoints["claude"].setCurrentIndex(dialog.endpoints["claude"].findData("default"))
assert dialog.auth["claude"].currentData() == "api_key"
dialog.endpoints["claude"].setCurrentIndex(dialog.endpoints["claude"].findData("custom"))
values = dialog.options()
session.agent_started = True
session.native_session_id = "old-cli-session"
session.update_settings(values)
assert session.options["model"] == ""
assert not session.agent_started and session.native_session_id != "old-cli-session"
assert session.options["claude_custom_model"] == "claude-test"
assert session.options["claude_auth"] == "api_key"
assert QSettings().value("mapsuke/claude_base_url") == "https://claude.example.test"
restored = SettingsDialog(session.options)
assert restored.endpoints["claude"].currentData() == "custom"
assert restored.endpoints["codex"].currentData() == "amazon-bedrock-runtime"
assert restored.auth["claude"].currentData() == "api_key"
assert restored.auth["codex"].currentData() == "aws"
assert restored.mierune_link.textInteractionFlags() & Qt.TextInteractionFlag.LinksAccessibleByKeyboard
restored.endpoints["claude"].setCurrentIndex(restored.endpoints["claude"].findData("default"))
assert restored.auth["claude"].currentData() == "api_key"
restored.close()
from mapsuke_endpoint_ui_test.core import credentials
assert QgsApplication.authManager().setMasterPassword("mapsuke-endpoint-smoke", True)
key_dialog = SettingsDialog(session.options)
key_dialog.api_keys["claude"][0].setText("endpoint-smoke-key")
key_dialog.accept()
assert credentials.api_key("claude") == "endpoint-smoke-key"
assert credentials.remove_api_key("claude")
session.shutdown()
dialog.close()
from mapsuke_endpoint_ui_test.ui.dock import AgentDock
class DockIface:
    def __init__(self):
        self.window = QMainWindow()
    def mainWindow(self):
        return self.window
iface = DockIface()
dock = AgentDock(iface, Path(settings_dir.name) / "dock.sqlite3")
def picker_models():
    return {dock.model_selector.itemData(index) for index in range(dock.model_selector.count())}
assert picker_models() == {"claude-test", ""}, picker_models()
dock.session.update_settings({"claude_endpoint": "default"})
assert "claude-test" not in picker_models()
dock.session.update_settings({"claude_endpoint": "bedrock"})
assert picker_models() == {"claude-test", ""}, picker_models()
dock.session.new_chat("codex")
assert dock.session.options["provider"] == "codex"
assert picker_models() == {"global.openai.gpt-6-sol", ""}, picker_models()
dock.session.update_settings({"codex_endpoint": "amazon-bedrock"})
assert picker_models() == {"global.openai.gpt-6-sol", ""}, picker_models()
dock.session.update_settings({"codex_endpoint": "default"})
assert "global.openai.gpt-6-sol" not in picker_models()
dock.session.shutdown()
dock.close()
print("PASS: endpoint settings UI and persistence")
os._exit(0)
