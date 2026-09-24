"""Inventory tabs with an explicit, asynchronous Claude MCP health check."""
from .i18n import tr, tr_inventory
import os
import tempfile

from qgis.PyQt.QtCore import QProcess, QProcessEnvironment, QTimer
from qgis.PyQt.QtWidgets import (QAbstractItemView, QCheckBox, QHeaderView, QHBoxLayout, QLabel,
                                QPushButton, QTableWidget, QTableWidgetItem,
                                QVBoxLayout, QWidget)
from .capabilities import connection_statuses, read_inventory


class CapabilityTabs:
    def __init__(self, tabs, executable, owner, options=None):
        self.options = options or {}
        self.toggles = {}
        self.owner = owner
        self.executable = executable
        self.process = None
        self.workdir = None
        self.timer = QTimer(owner)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.stop(tr("接続確認がタイムアウトしました")))
        self.skill_table, self.skill_status, self.skill_refresh = self.add_tab(tabs, tr("スキル"), [tr("名前"), tr("説明"), tr("読み込み元"), tr("このチャット")])
        self.connector_table, self.connector_status, self.connector_refresh = self.add_tab(tabs, tr("コネクタ"), [tr("名前"), tr("接続状態"), tr("種類"), tr("登録元"), tr("このチャット")])
        self.check = QPushButton(tr("接続確認"))
        self.connector_refresh.parentWidget().layout().itemAt(0).layout().addWidget(self.check)
        self.check.clicked.connect(self.check_connections)
        self.toggles["enable_skills"].toggled.connect(self.refresh_states)
        self.toggles["enable_connectors"].toggled.connect(self.refresh_states)
        self.skill_refresh.clicked.connect(self.refresh)
        self.connector_refresh.clicked.connect(self.refresh)
        owner.finished.connect(self.close)
        self.refresh()

    def add_tab(self, tabs, title, columns):
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        status = QLabel()
        row.addWidget(status, 1)
        refresh = QPushButton(tr("再読み込み"))
        row.addWidget(refresh)
        layout.addLayout(row)
        key = "enable_skills" if title == tr("スキル") else "enable_connectors"
        toggle = QCheckBox(tr("このセッションで") + title + tr("を使用する"))
        toggle.setChecked(self.options.get(key, False))
        self.toggles[key] = toggle
        layout.addWidget(toggle)
        note = QLabel(tr("OKで適用し、次の送信から反映します。読み込み対象はClaude Code側の設定に従います。\nツール実行はClaude側で許可済みの操作に限ります。追加の許可はターミナルの /permissions で設定できます。"))
        note.setWordWrap(True)
        layout.addWidget(note)
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(False)
        layout.addWidget(table)
        scope = QLabel(tr("対象：個人スキル・登録済みプラグイン。組み込み・クラウド同期・プロジェクト直下のスキルは対象外。") if title == tr("スキル") else
                       tr("対象：個人・プラグインのMCP。接続確認には現在のClaude実行パスを使います。\n提供ツール：未取得（CLIの一覧機能では取得できません）。"))
        scope.setWordWrap(True)
        layout.addWidget(scope)
        tabs.addTab(page, title)
        return table, status, refresh

    def refresh(self):
        inventory = read_inventory()
        self.skills = inventory["skills"]
        self.connectors = inventory["connectors"]
        self.populate(self.skill_table, inventory["skills"], ("name", "description", "source"))
        self.populate_connectors()
        self.skill_status.setText(str(len(inventory["skills"])) + tr(" スキル"))
        self.connector_status.setText(str(len(self.connectors)) + tr(" コネクタ · 接続未確認"))
        warning = "\n".join(tr_inventory(item) for item in inventory["warnings"])
        for label in (self.skill_status, self.connector_status):
            label.setToolTip(warning)
            if warning:
                label.setText(label.text() + tr(" · 一部読込失敗（詳細はホバー）"))

    def populate(self, table, rows, keys):
        table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for column, key in enumerate(keys):
                label = tr_inventory(row[key]) if key in ("status", "source") else tr(row[key])
                item = QTableWidgetItem(label)
                item.setToolTip(label + "\n" + row["path"])
                table.setItem(index, column, item)
            enabled = self.toggles["enable_skills" if table is self.skill_table else "enable_connectors"].isChecked()
            state = tr("使用しない")
            if enabled:
                source = row["source"]
                state = (tr("Claude側で無効") if " · 無効設定" in source else
                         tr("対象外（別スコープ）") if " · project · " in source or " · local · " in source else
                         tr("読み込み許可"))
            table.setItem(index, len(keys), QTableWidgetItem(state))
        table.resizeColumnsToContents()
        for column in range(table.columnCount()):
            table.setColumnWidth(column, min(table.columnWidth(column), 200))
        flexible = keys.index("description") if "description" in keys else keys.index("source")
        table.horizontalHeader().setSectionResizeMode(flexible, QHeaderView.ResizeMode.Stretch)

    def selected_options(self):
        return {key: toggle.isChecked() for key, toggle in self.toggles.items()}

    def refresh_states(self):
        self.populate(self.skill_table, self.skills, ("name", "description", "source"))
        self.populate_connectors()

    def populate_connectors(self):
        self.populate(self.connector_table, self.connectors, ("name", "status", "transport", "source"))

    def check_connections(self):
        if self.process is not None:
            return
        executable = self.executable().strip()
        if not executable:
            self.connector_status.setText(tr("一般タブでClaudeの実行パスを指定してください"))
            return
        self.refresh()
        self.buffer = bytearray()
        self.workdir = tempfile.TemporaryDirectory(prefix="qgis-agent-inventory-")
        self.process = QProcess(self.owner)
        self.process.setWorkingDirectory(self.workdir.name)
        env = QProcessEnvironment.systemEnvironment()
        for key in ("PYTHONHOME", "PYTHONPATH", "CLAUDECODE"):
            env.remove(key)
        self.process.setProcessEnvironment(env)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.error)
        for button in (self.check, self.skill_refresh, self.connector_refresh):
            button.setEnabled(False)
        self.connector_status.setText(tr("接続を確認しています…"))
        self.timer.start(30000)
        self.process.start(os.path.expanduser(executable), ["mcp", "list"])

    def read_output(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        if len(self.buffer) > 1_000_000:
            self.stop(tr("接続確認の出力が上限を超えました"))

    def error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.stop(tr("Claudeを起動できません。実行パスを確認してください"))

    def finished(self, exit_code, exit_status):
        if self.process is None:
            return
        self.read_output()
        if self.process is None:
            return
        statuses = connection_statuses(self.buffer.decode("utf-8", errors="replace"))
        for connector in self.connectors:
            connector["status"] = statuses.pop(connector["name"], tr("未確認"))
        # The CLI may discover account connectors absent from local config files.
        for name, status in statuses.items():
            self.connectors.append({"name": name, "status": status, "transport": "—",
                                    "source": "Claude CLI", "path": ""})
        self.populate_connectors()
        message = tr("接続確認完了") if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit else tr("接続確認に失敗しました")
        if not self.connectors and exit_code == 0:
            message += tr(" · コネクタなし、またはCLI出力形式が未対応")
        self.stop(message)

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
        for button in (self.check, self.skill_refresh, self.connector_refresh):
            button.setEnabled(True)
        if message:
            self.connector_status.setText(message)

    def close(self, result=0):
        self.stop()


class CodexCapabilityTabs:
    """Session overrides for locally registered Codex skills and MCP servers."""
    def __init__(self, tabs, options):
        from qgis.PyQt.QtWidgets import QComboBox
        from .capabilities import read_codex_inventory
        self.overrides = options.get('codex_capabilities', {})
        self.controls = {}
        inventory = read_codex_inventory()
        for kind, title in (('skills', tr('スキル')), ('connectors', tr('コネクタ'))):
            page = QWidget()
            layout = QVBoxLayout(page)
            note = QLabel(tr('このセッションでの使用設定です。OKで保存し、次の送信から反映します。\n'
                          '「CLIの設定に従う」はCodex側の設定を使用します。'))
            note.setWordWrap(True)
            layout.addWidget(note)
            table = QTableWidget(0, 3)
            table.setHorizontalHeaderLabels([tr('名前'), tr('説明'), tr('このセッション')])
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            table.verticalHeader().hide()
            rows = {row['id']: row for row in inventory[kind]}
            for key in self.overrides.get(kind, {}):
                rows.setdefault(key, {'name': key, 'description': tr('保存済みの設定（現在の一覧にはありません）')})
            table.setRowCount(len(rows))
            for index, (key, row) in enumerate(rows.items()):
                name = QTableWidgetItem(row['name'])
                name.setToolTip(key)
                table.setItem(index, 0, name)
                table.setItem(index, 1, QTableWidgetItem(tr(row['description'])))
                choice = QComboBox()
                choice.addItem(tr('CLIの設定に従う'), None)
                choice.addItem(tr('使用する'), True)
                choice.addItem(tr('使用しない'), False)
                value = self.overrides.get(kind, {}).get(key)
                choice.setCurrentIndex(0 if value is None else 1 if value else 2)
                if kind == 'connectors':
                    import re
                    if not re.fullmatch(r'[A-Za-z0-9_-]+', key):
                        choice.setEnabled(False)
                        choice.setToolTip(tr('この名前のMCPはCodex CLI側で設定してください'))
                table.setCellWidget(index, 2, choice)
                self.controls[(kind, key)] = choice
            table.setColumnWidth(2, 170)
            layout.addWidget(table)
            scope = QLabel(tr('対象：個人のローカルスキルとconfig.tomlのMCP。プラグイン・クラウドの項目はCLI側で管理します。\n')
                           + '\n'.join(tr_inventory(item) for item in inventory['warnings']))
            scope.setWordWrap(True)
            layout.addWidget(scope)
            tabs.addTab(page, title)

    def selected_options(self):
        result = {'skills': {}, 'connectors': {}}
        for (kind, key), choice in self.controls.items():
            if choice.currentIndex() != 0:
                result[kind][key] = choice.currentIndex() == 1
        return result
