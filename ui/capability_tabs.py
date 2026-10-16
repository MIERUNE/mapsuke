"""Per-chat capability choices with provider-specific discovery and CLI constraints."""
from ..i18n import tr
import os
import tempfile

from qgis.PyQt.QtCore import QProcess, QTimer
from qgis.PyQt.QtWidgets import (QAbstractItemView, QCheckBox, QHeaderView, QHBoxLayout, QLabel,
                                QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
                                QVBoxLayout, QWidget)
from ..core.capabilities import connection_statuses, read_inventory


class CapabilityTable(QTableWidget):
    """Keep tri-state choices across discovery, including temporarily missing items.

    Providers supply metadata and editability; this table owns selection state and
    presentation. True permits loading, while CLI configuration and permissions
    can still prevent an item from being available.
    """
    def __init__(self, columns, overrides=None):
        super().__init__(0, len(columns) + 1)
        self.columns = columns
        self.overrides = dict(overrides or {})
        self.choices = {}
        self.setHorizontalHeaderLabels([title for _, title in columns] + [tr("This chat")])
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.verticalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def selected_options(self):
        return {key: choice.currentData() for key, choice in self.choices.items()
                if choice.currentData() is not None}

    def set_rows(self, rows, enabled=True):
        if self.choices:
            self.overrides = self.selected_options()
        rows = {row.get("id", row["name"]): row for row in rows}
        for key in self.overrides:
            rows.setdefault(key, {"name": key, "description": tr("Saved setting (not in the current list)"),
                                  "source": tr("Saved setting (not in the current list)")})
        self.setRowCount(0)
        self.setRowCount(len(rows))
        self.choices = {}
        for index, (key, row) in enumerate(rows.items()):
            for column, (field, _) in enumerate(self.columns):
                item = QTableWidgetItem(str(row.get(field, "—")))
                item.setToolTip(row.get("path", str(key)))
                self.setItem(index, column, item)
            if row.get("editable", True) is False and key not in self.overrides:
                self.setItem(index, len(self.columns), QTableWidgetItem(row["note"]))
                continue
            choice = QComboBox()
            choice.addItem(tr("Follow CLI settings"), None)
            choice.addItem(tr("Enable"), True)
            choice.addItem(tr("Disable"), False)
            value = self.overrides.get(key)
            choice.setCurrentIndex(0 if value is None else 1 if value else 2)
            choice.setEnabled(enabled and row.get("editable", True))
            choice.setToolTip(row.get("note", ""))
            self.setCellWidget(index, len(self.columns), choice)
            self.choices[key] = choice
        self.resizeColumnsToContents()
        for column in range(len(self.columns)):
            self.setColumnWidth(column, min(self.columnWidth(column), 200))
        self.setColumnWidth(len(self.columns), 170)
        flexible = next((i for i, (field, _) in enumerate(self.columns)
                         if field in ("description", "source")), 0)
        self.horizontalHeader().setSectionResizeMode(flexible, QHeaderView.ResizeMode.Stretch)


class CapabilityTabs:
    def __init__(self, tabs, executable, owner, options=None):
        self.options = options or {}
        self.toggles = {}
        self.skill_choices = {}
        self.connector_choices = {}
        self.owner = owner
        self.executable = executable
        self.process = None
        self.workdir = None
        self.timer = QTimer(owner)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.stop(tr("Connection check timed out")))
        self.skill_table, self.skill_status, self.skill_refresh = self.add_tab(
            tabs, tr("Skills"), [("name", tr("Name")), ("description", tr("Description")), ("source", tr("Source"))],
            {name: value == "on" for name, value in self.options.get("claude_skills", {}).items()})
        self.connector_table, self.connector_status, self.connector_refresh = self.add_tab(
            tabs, tr("Connectors"), [("name", tr("Name")), ("status", tr("Connection status")),
                                     ("transport", tr("Type")), ("source", tr("Source"))],
            self.options.get("claude_connectors", {}))
        self.check = self.connector_refresh
        self.check.setToolTip(tr("Check connections"))
        self.toggles["enable_skills"].toggled.connect(self.refresh_states)
        self.toggles["enable_connectors"].toggled.connect(self.refresh_states)
        self.skill_refresh.clicked.connect(self.refresh)
        self.connector_refresh.clicked.connect(self.check_connections)
        owner.finished.connect(self.close)
        self.refresh()
        self.connector_tab = tabs.count() - 1
        self.connections_checked = False
        tabs.currentChanged.connect(lambda index: self.check_connections()
                                    if index == self.connector_tab and not self.connections_checked else None)

    def add_tab(self, tabs, title, columns, overrides):
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        status = QLabel()
        row.addWidget(status, 1)
        refresh = QPushButton(tr("Refresh"))
        row.addWidget(refresh)
        layout.addLayout(row)
        key = "enable_skills" if title == tr("Skills") else "enable_connectors"
        toggle = QCheckBox(tr("Use ") + title + tr(" in this session"))
        toggle.setChecked(self.options.get(key, False))
        self.toggles[key] = toggle
        layout.addWidget(toggle)
        note = QLabel(tr("These settings apply to this chat. Click OK to save; changes take effect with the next message.\nFollow CLI settings uses the provider's configuration. Enable permits loading within the CLI's settings and permissions."))
        note.setWordWrap(True)
        layout.addWidget(note)
        table = CapabilityTable(columns, overrides)
        layout.addWidget(table)
        scope = QLabel(tr("Includes personal skills and registered plugins. Plugin skills are managed by Claude Code. Built-in, cloud-synced, and project skills are excluded.") if title == tr("Skills") else
                       tr("Includes personal, plugin, and claude.ai MCP servers. The list is checked when this tab opens.\nProject-only servers are excluded. Claude.ai connectors require a Claude Code subscription sign-in."))
        scope.setWordWrap(True)
        layout.addWidget(scope)
        tabs.addTab(page, title)
        return table, status, refresh

    def refresh(self):
        inventory = read_inventory()
        self.skills = inventory["skills"]
        self.connectors = inventory["connectors"]
        self.populate_skills()
        self.populate_connectors()
        self.skill_status.setText(str(len(inventory["skills"])) + tr(" skills"))
        self.connector_status.setText(str(len(self.connectors)) + tr(" connectors · not checked"))
        warning = "\n".join(inventory["warnings"])
        for label in (self.skill_status, self.connector_status):
            label.setToolTip(warning)
            if warning:
                label.setText(label.text() + tr(" · some items could not be loaded (hover for details)"))

    def populate_skills(self):
        rows = [{**row, "editable": row["source"] == tr("Personal"),
                 "note": tr("Manage in Claude Code") if row["source"] != tr("Personal") else ""}
                for row in self.skills]
        self.skill_table.set_rows(rows, self.toggles["enable_skills"].isChecked())
        self.skill_choices = self.skill_table.choices

    def selected_skill_options(self):
        return {name: "on" if enabled else "off"
                for name, enabled in self.skill_table.selected_options().items()}

    def selected_options(self):
        return {**{key: toggle.isChecked() for key, toggle in self.toggles.items()},
                "claude_skills": self.selected_skill_options(),
                "claude_connectors": self.selected_connector_options()}

    def refresh_states(self):
        self.populate_skills()
        self.populate_connectors()

    def selected_connector_options(self):
        return self.connector_table.selected_options()

    def populate_connectors(self):
        self.connector_table.set_rows(self.connectors, self.toggles["enable_connectors"].isChecked())
        self.connector_choices = self.connector_table.choices

    def check_connections(self):
        if self.process is not None:
            self.stop(tr("Connection check canceled"))
            return
        executable = self.executable().strip()
        if not executable:
            self.connector_status.setText(tr("Set the Claude executable in the General tab"))
            return
        self.refresh()
        self.buffer = bytearray()
        self.workdir = tempfile.TemporaryDirectory(prefix="mapsuke-inventory-")
        self.process = QProcess(self.owner)
        self.process.setWorkingDirectory(self.workdir.name)
        from ..core.agent import cli_environment
        self.process.setProcessEnvironment(cli_environment())
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.error)
        self.connections_checked = True
        self.check.setText(tr("Cancel check"))
        self.skill_refresh.setEnabled(False)
        self.connector_status.setText(tr("Checking connections…"))
        self.timer.start(60000)
        self.process.start(os.path.expanduser(executable), ["mcp", "list"])

    def read_output(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        if len(self.buffer) > 1_000_000:
            self.stop(tr("Connection check output exceeded the limit"))
            return
        self.update_connections()
        self.connector_status.setText(tr("Checking connections…") + " " + str(len(self.connectors)))

    def error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.stop(tr("Could not start Claude. Check its executable path"))

    def finished(self, exit_code, exit_status):
        if self.process is None:
            return
        self.read_output()
        if self.process is None:
            return
        success = exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit
        message = tr("Connection check complete: {0} connectors").format(len(self.connectors)) if success else tr("Connection check failed")
        if success and not self.connectors:
            output = self.buffer.decode("utf-8", errors="replace")
            message = (tr("No MCP servers found. Sign in to Claude Code for claude.ai connectors, or add user/plugin MCP servers.")
                       if "No MCP servers configured" in output else tr("Could not recognize the CLI connection list. Check or update Claude Code."))
        self.stop(message)

    def update_connections(self):
        statuses = connection_statuses(self.buffer.decode("utf-8", errors="replace"))
        for connector in self.connectors:
            connector["status"] = statuses.pop(connector["name"], connector["status"])
        # The CLI may discover account connectors absent from local config files.
        for name, status in statuses.items():
            self.connectors.append({"name": name, "status": status, "transport": "—",
                                    "source": "claude.ai" if name.startswith("claude.ai ") else "Claude CLI", "path": ""})
        self.populate_connectors()

    def stop(self, message=None):
        self.timer.stop()
        if self.process is not None:
            self.process.blockSignals(True)
            if self.process.state() != QProcess.ProcessState.NotRunning:
                self.process.kill()
                self.process.waitForFinished(1000)
            self.process.deleteLater()
            self.process = None
        if self.workdir is not None:
            self.workdir.cleanup()
            self.workdir = None
        self.buffer = bytearray()
        for button in (self.check, self.skill_refresh):
            button.setEnabled(True)
        self.check.setText(tr("Refresh"))
        if message:
            self.connector_status.setText(message)
            self.connector_status.setWordWrap(True)

    def close(self, result=0):
        self.stop()


class CodexCapabilityTabs:
    """Per-chat overrides for locally registered Codex skills and MCP servers."""
    def __init__(self, tabs, options):
        self.pages = {}
        self.tables = {}
        self.statuses = {}
        self.controls = {}
        overrides = options.get("codex_capabilities", {})
        for kind, title in (("skills", tr("Skills")), ("connectors", tr("Connectors"))):
            page = QWidget()
            layout = QVBoxLayout(page)
            row = QHBoxLayout()
            status = QLabel()
            row.addWidget(status, 1)
            refresh = QPushButton(tr("Refresh"))
            refresh.clicked.connect(self.refresh)
            row.addWidget(refresh)
            layout.addLayout(row)
            note = QLabel(tr("These settings apply to this chat. Click OK to save; changes take effect with the next message.\nFollow CLI settings uses the provider's configuration. Enable permits loading within the CLI's settings and permissions."))
            note.setWordWrap(True)
            layout.addWidget(note)
            table = CapabilityTable([("name", tr("Name")), ("description", tr("Description")),
                                     ("source", tr("Source"))], overrides.get(kind))
            layout.addWidget(table)
            scope = QLabel(tr("Includes local personal skills and MCP servers in config.toml. Manage plugin and cloud items in the CLI."))
            scope.setWordWrap(True)
            layout.addWidget(scope)
            self.pages[kind] = page
            self.tables[kind] = table
            self.statuses[kind] = status
            tabs.addTab(page, title)
        self.refresh()

    def refresh(self):
        import re
        from ..core.capabilities import read_codex_inventory
        inventory = read_codex_inventory()
        self.controls = {}
        for kind, table in self.tables.items():
            rows = []
            # Saved names need the same validation even if discovery no longer returns them.
            known = {row["id"]: row for row in inventory[kind]}
            selected = table.selected_options() if table.choices else table.overrides
            for key in selected:
                known.setdefault(key, {"id": key, "name": key,
                                       "description": tr("Saved setting (not in the current list)")})
            for key, row in known.items():
                editable = kind != "connectors" or re.fullmatch(r"[A-Za-z0-9_-]+", key) is not None
                rows.append({**row, "source": tr("Personal"), "path": key, "editable": editable,
                             "note": "" if editable else tr("Configure this MCP name in Codex CLI")})
            table.set_rows(rows)
            self.controls.update({(kind, key): choice for key, choice in table.choices.items()})
            status = self.statuses[kind]
            status.setText(str(len(inventory[kind])) + (tr(" skills") if kind == "skills" else tr(" connectors")))
            status.setToolTip("\n".join(inventory["warnings"]))
            if inventory["warnings"]:
                status.setText(status.text() + tr(" · some items could not be loaded (hover for details)"))

    def selected_options(self):
        return {kind: table.selected_options() for kind, table in self.tables.items()}
