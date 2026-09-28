from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtWidgets import QAction
from .i18n import tr
from .core.session import migrate_legacy_settings
from .ui.dock import AgentDock


class QtaroPlugin:
    def __init__(self, iface, session_path=None):
        self.iface = iface
        self.session_path = session_path
        self.dock = None
        self.action = None
        self.processing_provider = None

    def initGui(self):
        from .core.processing_provider import AgentProcessingProvider
        from .core.protocol import install_bundled_skills
        try:
            migrate_legacy_settings(move_sessions=self.session_path is None)
        except OSError as exc:
            self.iface.messageBar().pushWarning("Qtaro", tr("Could not move saved sessions from QGIS Agent: ") + str(exc))
        try:
            install_bundled_skills()
        except OSError as exc:
            self.iface.messageBar().pushWarning("Qtaro", tr("Could not install the built-in skills: ") + str(exc))
        if self.processing_provider is None:
            provider = AgentProcessingProvider()
            if QgsApplication.processingRegistry().addProvider(provider):
                self.processing_provider = provider
        self.action = QAction("Qtaro", self.iface.mainWindow())
        self.action.triggered.connect(self.show)
        self.iface.addPluginToMenu("Qtaro", self.action)
        self.iface.addToolBarIcon(self.action)
        # Open on first enable, then follow whether the user left the dock open.
        if QSettings().value("qtaro/dock_open", True, type=bool):
            self.show()

    def show(self):
        if self.dock is None:
            self.dock = AgentDock(self.iface, self.session_path)
            self.iface.addTabifiedDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock,
                                             ["LayerStyling", "ProcessingToolbox"], True)
            self.dock.toggleViewAction().toggled.connect(self.remember_dock_open)
        self.dock.show()
        self.dock.raise_()
        # The toggle signal needs a visible main window, which startup does not have yet.
        self.remember_dock_open(True)

    def remember_dock_open(self, visible):
        QSettings().setValue("qtaro/dock_open", visible)

    def unload(self):
        if self.processing_provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.processing_provider)
            self.processing_provider = None
        if self.dock is not None:
            # Removing the dock hides it; that must not count as the user closing it.
            self.dock.toggleViewAction().toggled.disconnect(self.remember_dock_open)
            self.dock.shutdown()
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.action is not None:
            self.iface.removePluginMenu("Qtaro", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None
