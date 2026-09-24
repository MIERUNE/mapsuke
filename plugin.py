import json
from pathlib import Path
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt, QSettings, QTimer
from qgis.PyQt.QtWidgets import (QAction, QComboBox, QDialog, QDockWidget, QHBoxLayout, QMessageBox,
                                QLabel, QPushButton, QVBoxLayout, QWidget)
from .chat_ui import ChatInput, ChatTranscript, SettingsDialog
from .agent import AgentProcess, default_executable, default_codex_executable
from .protocol import build_prompt
from .runtime import QgisRuntime
from .sessions import SessionStore


# Explicit IDs keep the advertised version stable when Claude updates its aliases.
MODEL_CHOICES = (
    ("Claude Opus 5", "claude-opus-5"),
    ("Claude Sonnet 5", "claude-sonnet-5"),
    ("Claude Haiku 4.5", "claude-haiku-4-5-20251001"),
    ("デフォルト（Claude Codeの設定）", ""),
)
CODEX_MODELS = (
    ("GPT-6 Astra", "gpt-6-astra"),
    ("GPT-5.6 Sol", "gpt-5.6-sol"),
    ("GPT-5.6 Terra", "gpt-5.6-terra"),
    ("GPT-5.6 Luna", "gpt-5.6-luna"),
    ("GPT-5.5", "gpt-5.5"),
    ("デフォルト（Codexの設定）", ""),
)
LEGACY_MODELS = {"opus": "claude-opus-5", "sonnet": "claude-sonnet-5",
                 "haiku": "claude-haiku-4-5-20251001"}


class AgentDock(QDockWidget):
    def __init__(self, iface, session_path=None):
        super().__init__("QGIS Agent", iface.mainWindow())
        self.setObjectName("QgisAgentDock")
        self.runtime = QgisRuntime(iface)
        session_path = Path(session_path or Path(QgsApplication.qgisSettingsDirPath()) / "qgis-agent/sessions.sqlite3")
        self.agent = AgentProcess(self, workdir=session_path.parent / "claude-workspace")
        self.agent.session_opened.connect(self.on_session_opened)
        self.agent.completed.connect(self.on_response)
        self.agent.failed.connect(self.on_failure)
        self.agent.progress.connect(self.on_progress)
        self.streaming_bubble = None
        settings = QSettings()
        self.options = {"executable": settings.value("qgis-agent/executable", default_executable()),
                        "approval_mode": settings.value("qgis-agent/approval_mode", "ask")}
        if self.options["approval_mode"] not in ("ask", "auto", "full_auto"):
            self.options["approval_mode"] = "ask"
        # Previously saved automatic modes have not necessarily received informed consent.
        if (self.options["approval_mode"] != "ask" and
                settings.value("qgis-agent/consented_approval_mode", "") != self.options["approval_mode"]):
            self.options["approval_mode"] = "ask"
        settings.setValue("qgis-agent/approval_mode", self.options["approval_mode"])
        self.options["provider"] = "claude"
        self.options["codex_capabilities"] = json.loads(settings.value("qgis-agent/codex_capabilities", "{}"))
        self.options["codex_executable"] = settings.value("qgis-agent/codex_executable", default_codex_executable())
        self.options["model"] = settings.value("qgis-agent/model", "")
        for key in ("enable_skills", "enable_connectors"):
            self.options[key] = settings.value("qgis-agent/" + key, False, type=bool)
        self.session_id = None
        self.session_title = ""
        self.store = SessionStore(session_path)
        self.agent_started = False
        self.native_session_id = None
        self.sent_history = 0
        self.request_history_end = 0
        self.history = []
        self.pending_code = None
        self.running = False
        self.steps = 0
        self.continuation = QTimer(self)
        self.continuation.setSingleShot(True)
        self.continuation.timeout.connect(self.request)
        body = QWidget()
        layout = QVBoxLayout(body)
        body.setObjectName("chatBody")
        body.setStyleSheet("""
            QWidget#chatBody { background: palette(base); }
            QFrame#agentBubble { background: palette(alternate-base); border-radius: 12px; }
            QFrame#userBubble { background: palette(highlight); color: palette(highlighted-text); border-radius: 12px; }
            QFrame#userBubble QLabel, QFrame#userBubble QTextBrowser { color: palette(highlighted-text); }
            QLabel#messageRole { font-weight: 600; font-size: 11px; }
            QPlainTextEdit { border: 1px solid palette(mid); border-radius: 8px; padding: 8px; }
            QPushButton { padding: 6px 10px; }
        """)
        header = QHBoxLayout()
        self.provider_selector = QComboBox()
        self.provider_selector.addItem("Claude Code", "claude")
        self.provider_selector.addItem("Codex", "codex")
        self.provider_selector.setToolTip("会話開始後にエージェントを変更すると新しいセッションを開始します")
        header.addWidget(self.provider_selector)
        header.addStretch()
        self.reset = QPushButton("新しいセッション")
        self.settings_button = QPushButton("設定")
        header.addWidget(self.reset)
        header.addWidget(self.settings_button)
        layout.addLayout(header)
        session_row = QHBoxLayout()
        self.sessions = QComboBox()
        self.sessions.setMinimumContentsLength(12)
        self.sessions.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.sessions.setToolTip("セッションを切り替え（自動保存）")
        self.delete_button = QPushButton("削除")
        session_row.addWidget(self.sessions, 1)
        session_row.addWidget(self.delete_button)
        layout.addLayout(session_row)
        self.transcript = ChatTranscript()
        layout.addWidget(self.transcript, 1)
        self.status = QLabel("準備完了")
        layout.addWidget(self.status)
        self.input = ChatInput()
        self.input.setPlaceholderText("QGISでやりたいことを入力…\nEnterで送信 · Shift+Enterで改行")
        self.input.setFixedHeight(88)
        layout.addWidget(self.input)
        row = QHBoxLayout()
        self.model_selector = QComboBox()
        self.model_selector.setAccessibleName("モデル")
        self.model_selector.setToolTip("このセッションのモデル")
        for label, model in MODEL_CHOICES:
            self.model_selector.addItem(label, model)
        row.addWidget(self.model_selector)
        self.approval_selector = QComboBox()
        self.approval_selector.setAccessibleName("承認モード")
        self.approval_selector.setToolTip("Ask: 毎回確認 / Auto: AIがリスクを判断 / Full auto: 確認なしで実行")
        for label, mode in (("Ask", "ask"), ("Auto", "auto"), ("Full auto", "full_auto")):
            self.approval_selector.addItem(label, mode)
        self.approval_selector.setCurrentIndex(self.approval_selector.findData(self.options["approval_mode"]))
        self.approval_selector.currentIndexChanged.connect(self.select_approval_mode)
        row.addWidget(self.approval_selector)
        row.addStretch()
        self.send = QPushButton("送信 ↑")
        self.run = QPushButton("承認して実行")
        self.stop = QPushButton("停止")
        for button in (self.run, self.stop, self.send):
            row.addWidget(button)
        layout.addLayout(row)
        self.setWidget(body)
        self.send.clicked.connect(self.submit)
        self.input.submitted.connect(self.submit)
        self.settings_button.clicked.connect(self.open_settings)
        self.run.clicked.connect(self.execute)
        self.stop.clicked.connect(self.cancel)
        self.reset.clicked.connect(self.new_chat)
        self.sessions.currentIndexChanged.connect(self.switch_session)
        self.delete_button.clicked.connect(self.delete_session)
        self.model_selector.currentIndexChanged.connect(self.select_model)
        self.provider_selector.currentIndexChanged.connect(self.select_provider)
        self.set_busy(False)
        records = self.store.list()
        last = settings.value("qgis-agent/last_session", "")
        if records:
            self.load_session(last if any(r[0] == last for r in records) else records[0][0])
        else:
            self.save_session()
        self.refresh_sessions()
        self.draft_timer = QTimer(self)
        self.draft_timer.setSingleShot(True)
        self.draft_timer.timeout.connect(self.save_session)
        self.input.textChanged.connect(lambda: self.draft_timer.start(500))

    @property
    def agent_label(self):
        return "Codex" if self.options["provider"] == "codex" else "Claude"

    def select_provider(self, index):
        provider = self.provider_selector.itemData(index)
        if self.running or not provider or provider == self.options["provider"]:
            return
        if not self.history and not self.agent_started:
            # An unsent draft belongs to the same session, regardless of provider.
            previous_provider, previous_model = self.options["provider"], self.options["model"]
            self.options["provider"] = provider
            self.options["model"] = QSettings().value("qgis-agent/" + ("codex_model" if provider == "codex" else "model"), "")
            if not self.save_session():
                self.options["provider"], self.options["model"] = previous_provider, previous_model
            self.refresh_sessions()
            return
        if self.save_session():
            self.start_session(provider)
        else:
            self.refresh_sessions()

    def select_model(self, index):
        if self.running or index < 0:
            return
        self.options["model"] = self.model_selector.itemData(index)
        QSettings().setValue("qgis-agent/" + ("codex_model" if self.options["provider"] == "codex" else "model"), self.options["model"])
        self.save_session()

    def select_approval_mode(self, index):
        if self.running or index < 0:
            return
        mode = self.approval_selector.itemData(index)
        if mode != "ask":
            description = ("Autoでは、AIがリスクを評価し、確認不要と判断したPythonコードを自動実行します。AIの判断は誤ることがあります。"
                           if mode == "auto" else
                           "Full autoでは、生成したPythonコードを実行前の確認なしで実行します。")
            answer = QMessageBox.warning(
                self, "自動実行のリスクへの同意",
                description + "\n\nコードはQGISと同じ権限で動作し、ファイルの変更・削除や外部へのデータ送信が可能です。"
                "変更を自動で元に戻すことはできません。\n\nリスクを理解し、このモードを有効にすることに同意しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                mode = "ask"
        self.approval_selector.blockSignals(True)
        self.approval_selector.setCurrentIndex(self.approval_selector.findData(mode))
        self.approval_selector.blockSignals(False)
        self.options["approval_mode"] = mode
        settings = QSettings()
        settings.setValue("qgis-agent/approval_mode", mode)
        settings.setValue("qgis-agent/consented_approval_mode", mode if mode != "ask" else "")

    def open_settings(self):
        dialog = SettingsDialog(self.options, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.options.update(dialog.options())
            for key, value in dialog.options().items():
                QSettings().setValue("qgis-agent/" + key, json.dumps(value) if key == "codex_capabilities" else value)
            self.save_session()
            self.refresh_sessions()

    def log(self, role, text):
        return self.transcript.add_message(role, text)

    def on_progress(self, preview):
        if not self.running or not any(preview.values()):
            return
        if self.streaming_bubble is None:
            self.streaming_bubble = self.log(self.agent_label, "")
        self.streaming_bubble.update_content(preview["message"], preview["code"])
        self.status.setText(self.agent_label + "が応答しています…")

    def set_busy(self, busy):
        self.running = busy
        self.send.setEnabled(not busy)
        self.input.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.provider_selector.setEnabled(not busy)
        self.model_selector.setEnabled(not busy)
        self.approval_selector.setEnabled(not busy)
        self.reset.setEnabled(not busy)
        self.sessions.setEnabled(not busy)
        self.delete_button.setEnabled(not busy)
        self.run.setEnabled(busy and self.pending_code is not None)
        self.stop.setEnabled(busy)
        self.stop.setVisible(busy)
        self.send.setVisible(not busy)
        self.run.setVisible(busy and self.pending_code is not None)
        if not busy:
            self.status.setText("準備完了")
            self.input.setFocus()

    def submit(self):
        message = self.input.toPlainText().strip()
        if not message or self.running:
            return
        executable_key = "codex_executable" if self.options["provider"] == "codex" else "executable"
        if not self.options[executable_key]:
            self.log("エラー", self.agent_label + "の実行パスを入力してください")
            return
        self.history.append({"role": "user", "content": message})
        self.log("あなた", message)
        self.input.clear()
        self.steps = 0
        self.set_busy(True)
        if not self.save_session():
            self.set_busy(False)
            return
        self.refresh_sessions()
        self.request()

    def request(self):
        if not self.running:
            return
        self.streaming_bubble = None
        self.status.setText(self.agent_label + "の応答を待っています…")
        try:
            delta = self.history[self.sent_history:] if self.agent_started else self.history
            if self.agent_started:
                delta = [entry for entry in delta if entry["role"] != "assistant"]
            prompt = build_prompt(delta, self.runtime.context(), generate_title=
                                  not self.session_title and not any(item["role"] == "assistant" for item in self.history),
                                  approval_mode=self.options["approval_mode"])
            self.request_history_end = len(self.history)
            if len(prompt.encode("utf-8")) > 500000:
                raise ValueError("会話が上限に達しました。新しいセッションを開始してください")
            executable_key = "codex_executable" if self.options["provider"] == "codex" else "executable"
            self.agent.request(self.options[executable_key], prompt, self.options["model"],
                               self.native_session_id or self.session_id, resume=self.agent_started,
                               provider=self.options["provider"],
                               enable_skills=self.options["enable_skills"],
                               enable_connectors=self.options["enable_connectors"],
                               codex_capabilities=self.options["codex_capabilities"])
        except Exception as exc:
            self.on_failure(str(exc))

    def on_session_opened(self, session_id):
        # An init event means the CLI owns this session, including interrupted turns.
        self.agent_started = True
        self.native_session_id = session_id
        self.sent_history = self.request_history_end
        if not self.save_session():
            self.agent.cancel("セッション状態を保存できませんでした")

    def on_response(self, response):
        if not self.running:
            return
        if not self.agent_started:
            self.on_session_opened(self.session_id)
        if not self.session_title and not any(item["role"] == "assistant" for item in self.history):
            self.session_title = " ".join(response.get("title", "").split())[:50]
        self.history.append({"role": "assistant", "content": response})
        bubble = self.streaming_bubble or self.log(self.agent_label, "")
        bubble.update_content(response["message"], response["code"])
        self.streaming_bubble = None
        if not response["code"].strip():
            self.set_busy(False)
            self.save_session()
            return
        self.pending_code = response["code"]
        if self.steps >= 8:
            self.history.append({"role": "bridge", "content": "Step limit reached. Last code was NOT executed."})
            self.pending_code = None
            self.log("QGIS", "自動実行の上限（8回）に達しました。続行する場合はメッセージを送信してください。")
            self.set_busy(False)
            self.save_session()
            return
        if not self.save_session():
            self.on_failure("保存に失敗したためコードを実行しませんでした")
            return
        mode = self.options["approval_mode"]
        needs_approval = mode == "ask" or (mode == "auto" and response.get("requires_approval", True))
        if not needs_approval:
            self.execute()
        else:
            bubble.toggle.setChecked(True)
            self.run.setVisible(True)
            self.run.setEnabled(True)
            reason = response.get("approval_reason", "").strip()
            if not reason:
                reason = "Askモードのため実行前に確認します。" if mode == "ask" else "AIのリスク評価がないため、実行前に確認します。"
            self.log("実行の確認", reason + "\n承認して実行、または停止を選んでください。")
            self.status.setText("実行の承認待ち")
            self.save_session()

    def execute(self):
        if self.pending_code is None or not self.running:
            return
        code, self.pending_code = self.pending_code, None
        self.run.setEnabled(False)
        self.run.hide()
        self.status.setText("Pythonを実行中…")
        self.steps += 1
        result = self.runtime.execute(code)
        self.history.append({"role": "bridge", "content": result})
        self.log("QGIS · " + ("実行成功" if result["ok"] else "実行エラー"),
                 result["output"] + (result["error"] or "") or "（出力なし）")
        self.status.setText(self.agent_label + "に実行結果を返します…")
        # Yield to Qt so the canvas refresh and stop button can be processed.
        if self.save_session():
            self.continuation.start(0)
        else:
            self.on_failure("実行結果を保存できなかったため停止しました")

    def on_failure(self, message):
        self.continuation.stop()
        self.pending_code = None
        self.history.append({"role": "bridge", "content": "Interaction stopped: " + message})
        if self.streaming_bubble is not None:
            self.streaming_bubble.role.setText(self.agent_label + " · 応答中断（未実行）")
            self.streaming_bubble = None
        self.log("エラー / 停止", message)
        self.set_busy(False)
        self.save_session()

    def cancel(self):
        self.continuation.stop()
        if self.agent.process is not None:
            self.agent.cancel()
        else:
            self.on_failure("停止しました。未実行のコードは実行していません。")

    def save_session(self):
        if self.options["provider"] == "claude":
            self.options["model"] = LEGACY_MODELS.get(self.options["model"], self.options["model"])
        title = self.session_title or next((item["content"][:50].replace("\n", " ") for item in self.history
                      if item["role"] == "user"), "新しいセッション")
        payload = {"version": 1, "title": self.session_title, "history": self.history, "model": self.options["model"],
                   "draft": self.input.toPlainText(), "interrupted": self.running,
                   "agent_started": self.agent_started, "sent_history": self.sent_history,
                   "provider": self.options["provider"], "native_session_id": self.native_session_id,
                   "codex_capabilities": self.options["codex_capabilities"],
                   "enable_skills": self.options["enable_skills"],
                   "enable_connectors": self.options["enable_connectors"],
                   "messages": [{"role": bubble.role.text(), "text": bubble.message.text(),
                                 "code": bubble.code.toPlainText()} for bubble in self.transcript.messages
                                if bubble is not self.streaming_bubble]}
        try:
            self.session_id = self.store.save(self.session_id, "[" + self.agent_label + "] " + title, payload)
            index = self.sessions.findData(self.session_id)
            if index >= 0:
                self.sessions.setItemText(index, "[" + self.agent_label + "] " + title)
            QSettings().setValue("qgis-agent/last_session", self.session_id)
            return True
        except Exception as exc:
            self.log("保存エラー", str(exc))
            self.status.setText("セッションを保存できませんでした")
            return False

    def refresh_sessions(self):
        self.sessions.blockSignals(True)
        self.sessions.clear()
        for session_id, title, updated in self.store.list():
            self.sessions.addItem(title, session_id)
        self.sessions.setCurrentIndex(self.sessions.findData(self.session_id))
        self.sessions.blockSignals(False)
        if self.options["provider"] == "claude":
            self.options["model"] = LEGACY_MODELS.get(self.options["model"], self.options["model"])
        self.provider_selector.blockSignals(True)
        self.provider_selector.setCurrentIndex(self.provider_selector.findData(self.options["provider"]))
        self.provider_selector.blockSignals(False)
        self.model_selector.blockSignals(True)
        self.model_selector.clear()
        for label, model in (CODEX_MODELS if self.options["provider"] == "codex" else MODEL_CHOICES):
            self.model_selector.addItem(label, model)
        index = self.model_selector.findData(self.options["model"])
        if index < 0:
            # Preserve existing sessions without offering arbitrary text entry.
            self.model_selector.addItem("以前の設定: " + self.options["model"], self.options["model"])
            index = self.model_selector.count() - 1
        self.model_selector.setCurrentIndex(index)
        self.model_selector.blockSignals(False)

    def load_session(self, session_id):
        try:
            payload = self.store.load(session_id)
        except Exception as exc:
            self.log("読込エラー", str(exc))
            return False
        self.session_id = session_id
        self.session_title = payload.get("title", "")
        self.history = payload["history"]
        self.options["provider"] = payload.get("provider", "claude")
        self.options["codex_capabilities"] = payload.get("codex_capabilities", {})
        self.agent_started = payload.get("agent_started", payload.get("claude_started", False))
        self.native_session_id = payload.get("native_session_id") or (session_id if self.agent_started else None)
        self.sent_history = payload.get("sent_history", 0)
        self.options["model"] = payload.get("model", "")
        for key in ("enable_skills", "enable_connectors"):
            self.options[key] = payload.get(key, False)
        self.input.setPlainText(payload.get("draft", ""))
        self.pending_code = None
        self.streaming_bubble = None
        self.runtime = QgisRuntime(self.runtime.iface)
        self.transcript.clear()
        for message in payload["messages"]:
            self.log(message["role"], message["text"]).update_content(message["text"], message["code"])
        if self.history:
            note = "セッションを復元しました。Python変数はリセットされ、過去のコードは再実行していません。現在のQGISプロジェクトを参照します。"
            if payload.get("interrupted"):
                note += " 前回の処理は途中で終了しています。変更が部分的に適用されている可能性があります。"
            self.history.append({"role": "bridge", "content": note})
            self.log("QGIS", note)
        self.save_session()
        self.refresh_sessions()
        return True

    def switch_session(self, index):
        target = self.sessions.itemData(index)
        if self.running or not target or target == self.session_id:
            return
        if self.save_session():
            self.load_session(target)
        self.refresh_sessions()

    def new_chat(self):
        if not self.history and not self.agent_started and not self.input.toPlainText().strip():
            return
        if self.running or not self.save_session():
            return
        self.start_session()

    def start_session(self, provider=None):
        self.options["codex_capabilities"] = json.loads(QSettings().value("qgis-agent/codex_capabilities", "{}"))
        if provider is not None:
            self.options["provider"] = provider
        self.agent_started = False
        self.native_session_id = None
        self.sent_history = 0
        self.session_id = None
        self.session_title = ""
        self.history = []
        self.pending_code = None
        self.input.clear()
        self.runtime = QgisRuntime(self.runtime.iface)
        self.transcript.clear()
        self.streaming_bubble = None
        self.options["model"] = QSettings().value("qgis-agent/" + ("codex_model" if self.options["provider"] == "codex" else "model"), "")
        for key in ("enable_skills", "enable_connectors"):
            self.options[key] = QSettings().value("qgis-agent/" + key, False, type=bool)
        self.log("QGIS", "新しいセッションを開始しました。")
        self.save_session()
        self.refresh_sessions()

    def delete_session(self):
        if self.running or not self.session_id:
            return
        if QMessageBox.question(self, "セッションを削除", "このセッションを一覧から削除しますか？QGISのレイヤーとエージェント側の履歴は残ります。",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete(self.session_id)
        except Exception as exc:
            self.log("削除エラー", str(exc))
            return
        self.session_id = None
        self.session_title = ""
        self.history = []
        self.transcript.clear()
        self.input.clear()
        records = self.store.list()
        if records:
            self.load_session(records[0][0])
        else:
            self.start_session()
        self.refresh_sessions()

    def shutdown(self):
        self.continuation.stop()
        self.draft_timer.stop()
        if self.running:
            self.cancel()
        self.save_session()
        self.agent.close()
        self.store.close()


class QgisAgentPlugin:
    def __init__(self, iface, session_path=None):
        self.iface = iface
        self.session_path = session_path
        self.dock = None
        self.action = None
        self.processing_provider = None

    def initGui(self):
        from .processing_provider import AgentProcessingProvider
        if self.processing_provider is None:
            provider = AgentProcessingProvider()
            if QgsApplication.processingRegistry().addProvider(provider):
                self.processing_provider = provider
        self.action = QAction("QGIS Agent", self.iface.mainWindow())
        self.action.triggered.connect(self.show)
        self.iface.addPluginToMenu("QGIS Agent", self.action)
        self.iface.addToolBarIcon(self.action)

    def show(self):
        if self.dock is None:
            self.dock = AgentDock(self.iface, self.session_path)
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.show()
        self.dock.raise_()

    def unload(self):
        if self.processing_provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.processing_provider)
            self.processing_provider = None
        if self.dock is not None:
            self.dock.shutdown()
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.action is not None:
            self.iface.removePluginMenu("QGIS Agent", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None
