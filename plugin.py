from .i18n import tr
import json
from pathlib import Path
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt, QSettings, QTimer
from qgis.PyQt.QtWidgets import (QAction, QCheckBox, QComboBox, QDialog, QDockWidget, QHBoxLayout, QMenu,
                                QMessageBox, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget)
from .chat_ui import ChatInput, ChatTranscript, ContextRing, SettingsDialog
from .agent import AgentProcess, default_executable, default_codex_executable
from .auth import LoginProcess
from .protocol import build_prompt
from .processing_catalog import processing_catalog
from .runtime import QgisRuntime
from .sessions import SessionStore
from .session_ui import SessionPicker
from .usage import context_meter
from .model_compat import listed_codex_models, unavailable_reason


# Explicit IDs keep the advertised version stable when Claude updates its aliases.
MODEL_CHOICES = (
    ("Claude Opus 5.5", "claude-opus-5-5"),
    ("Claude Fable 5.1", "claude-fable-5-1"),
    ("Claude Sonnet 5", "claude-sonnet-5"),
    ("Claude Haiku 4.5", "claude-haiku-4-5-20251001"),
    (tr("デフォルト（Claude Codeの設定）"), ""),
)
CODEX_MODELS = (
    ("GPT-6 Astra", "gpt-6-astra"),
    ("GPT-5.6 Sol", "gpt-5.6-sol"),
    ("GPT-5.6 Terra", "gpt-5.6-terra"),
    ("GPT-5.6 Luna", "gpt-5.6-luna"),
    ("GPT-5.5", "gpt-5.5"),
    (tr("デフォルト（Codexの設定）"), ""),
)
LEGACY_MODELS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5",
                 "haiku": "claude-haiku-4-5-20251001"}
RESTORE_NOTICE = "セッションを復元しました。Python変数はリセットされ、過去のコードは再実行していません。現在のQGISプロジェクトを参照します。"
NEW_SESSION_NOTICE = "新しいセッションを開始しました。"


def default_effort(provider, model):
    return "medium" if provider == "codex" or model == "claude-opus-5-5" else "high"


class AgentDock(QDockWidget):
    def __init__(self, iface, session_path=None):
        super().__init__("QGIS Agent", iface.mainWindow())
        self.setObjectName("QgisAgentDock")
        self.runtime = QgisRuntime(iface)
        session_path = Path(session_path or Path(QgsApplication.qgisSettingsDirPath()) / "qgis-agent/sessions.sqlite3")
        self.agent = AgentProcess(self, workdir=session_path.parent / "claude-workspace")
        self.agent.session_opened.connect(self.on_session_opened)
        self.agent.completed.connect(self.on_response)
        self.agent.usage_updated.connect(self.on_usage_updated)
        self.agent.failed.connect(self.on_failure)
        self.agent.progress.connect(self.on_progress)
        self.agent.login_required.connect(self.on_login_required)
        self.login = LoginProcess(self)
        self.login.url_found.connect(self.on_login_url)
        self.login.finished.connect(self.on_login_finished)
        self.streaming_bubble = None
        self.reasoning_notice = None
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
        self.options["effort"] = settings.value("qgis-agent/claude_effort", "") or default_effort("claude", self.options["model"])
        self.options["fast_mode"] = settings.value("qgis-agent/claude_fast_mode", False, type=bool)
        for key in ("enable_skills", "enable_connectors"):
            self.options[key] = settings.value("qgis-agent/" + key, False, type=bool)
        self.session_id = None
        self.session_title = ""
        self.context_usage = None
        self.store = SessionStore(session_path)
        self.agent_started = False
        self.native_session_id = None
        self.sent_history = 0
        self.request_history_end = 0
        self.history = []
        self.pending_code = None
        self.running = False
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
            QLabel#agentQuestion { font-weight: 600; padding-top: 4px; }
            QPushButton#agentChoice { text-align: left; }
            QLabel#questionHint { color: palette(mid); font-size: 11px; }
            QPlainTextEdit { border: 1px solid palette(mid); border-radius: 8px; padding: 8px; }
            QPushButton { padding: 6px 10px; }
        """)
        header = QHBoxLayout()
        self.reset = QToolButton()
        self.reset.setText(tr("新しいセッション"))
        self.reset.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.reset.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        new_menu = QMenu(self.reset)
        for label, provider in (("Claude", "claude"), ("Codex", "codex")):
            new_menu.addAction(label, lambda checked=False, provider=provider: self.new_chat(provider))
        self.reset.setMenu(new_menu)
        self.sessions = QComboBox()
        self.sessions.setMinimumContentsLength(12)
        self.sessions.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.sessions.setToolTip(tr("セッションを切り替え（自動保存）"))
        self.all_sessions_button = QPushButton(tr("一覧…"))
        self.settings_button = QPushButton(tr("設定"))
        header.addWidget(self.reset)
        header.addWidget(self.sessions, 1)
        header.addWidget(self.all_sessions_button)
        header.addWidget(self.settings_button)
        layout.addLayout(header)
        self.transcript = ChatTranscript()
        layout.addWidget(self.transcript, 1)
        status_row = QHBoxLayout()
        self.status = QLabel(tr("準備完了"))
        status_row.addWidget(self.status)
        self.wait_indicator = QLabel()
        self.wait_indicator.setAccessibleName(tr("応答待ち"))
        self.wait_indicator.setFixedWidth(self.wait_indicator.fontMetrics().horizontalAdvance("◐") + 4)
        status_row.addWidget(self.wait_indicator)
        status_row.addStretch()
        layout.addLayout(status_row)
        self.wait_frames = ("◐", "◓", "◑", "◒")
        self.wait_frame = 0
        self.wait_timer = QTimer(self)
        self.wait_timer.setInterval(150)
        self.wait_timer.timeout.connect(self.advance_wait_indicator)
        self.wait_indicator.hide()
        self.input = ChatInput()
        self.input.setPlaceholderText(tr("QGISでやりたいことを入力…\nEnterで送信 · Shift+Enterで改行"))
        self.input.setFixedHeight(88)
        layout.addWidget(self.input)
        controls = QHBoxLayout()
        controls.setContentsMargins(2, 0, 2, 0)
        self.context_ring = ContextRing()
        controls.addWidget(self.context_ring)
        self.approval_selector = QComboBox()
        self.approval_selector.setAccessibleName(tr("承認モード"))
        self.approval_selector.setToolTip(tr("Ask: 毎回確認 / Auto: AIがリスクを判断 / Full auto: 確認なしで実行"))
        for label, mode in (("Ask", "ask"), ("Auto", "auto"), ("Full auto", "full_auto")):
            self.approval_selector.addItem(label, mode)
        self.approval_selector.setCurrentIndex(self.approval_selector.findData(self.options["approval_mode"]))
        self.approval_selector.currentIndexChanged.connect(self.select_approval_mode)
        controls.addWidget(self.approval_selector)
        self.model_selector = QComboBox()
        self.model_selector.setAccessibleName(tr("モデル"))
        self.model_selector.setToolTip(tr("このセッションのモデル"))
        for label, model in MODEL_CHOICES:
            self.model_selector.addItem(label, model)
        controls.addWidget(self.model_selector)
        self.effort_selector = QComboBox()
        self.effort_selector.setAccessibleName("Effort")
        self.effort_selector.setToolTip(tr("次の応答で使う推論の強さ。段階の意味と対応範囲はモデル・CLIごとに異なります。"))
        for label, effort in (("Low", "low"), ("Medium", "medium"),
                              ("High", "high"), ("Xhigh", "xhigh"), ("Max", "max")):
            self.effort_selector.addItem(label, effort)
        controls.addWidget(self.effort_selector)
        self.fast_mode = QCheckBox("Fast")
        self.fast_mode.setAccessibleName("Fast mode")
        self.fast_mode.setToolTip(tr("次の応答から高速モードを使います。利用可能なモデルとアカウントが必要です。"))
        controls.addWidget(self.fast_mode)
        controls.addStretch()
        self.run = QPushButton(tr("承認して実行"))
        self.run_always = QPushButton(tr("今後は自動承認"))
        self.run_always.setToolTip(tr("承認して実行し、以降はFull auto（確認なしで実行）に切り替えます"))
        controls.addWidget(self.run)
        controls.addWidget(self.run_always)
        self.send = QPushButton(tr("送信 ↑"))
        controls.addWidget(self.send)
        self.stop = QPushButton(tr("停止"))
        controls.addWidget(self.stop)
        layout.addLayout(controls)
        self.setWidget(body)
        self.send.clicked.connect(self.submit)
        self.input.submitted.connect(self.submit)
        self.settings_button.clicked.connect(self.open_settings)
        self.run.clicked.connect(self.execute)
        self.run_always.clicked.connect(self.approve_always)
        self.stop.clicked.connect(self.cancel)
        self.sessions.currentIndexChanged.connect(self.switch_session)
        self.all_sessions_button.clicked.connect(self.open_session_picker)
        self.model_selector.currentIndexChanged.connect(self.select_model)
        self.effort_selector.currentIndexChanged.connect(self.select_effort)
        self.fast_mode.toggled.connect(self.select_fast_mode)
        self.set_busy(False)
        last = settings.value("qgis-agent/last_session", "")
        initial = last if last and self.store.exists(last) else self.store.latest_id()
        if initial:
            self.load_session(initial)
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

    def select_model(self, index):
        if self.running or index < 0:
            return
        followed_default = self.options["effort"] == default_effort(self.options["provider"], self.options["model"])
        self.options["model"] = self.model_selector.itemData(index)
        QSettings().setValue("qgis-agent/" + ("codex_model" if self.options["provider"] == "codex" else "model"), self.options["model"])
        if followed_default:
            self.options["effort"] = default_effort(self.options["provider"], self.options["model"])
            QSettings().setValue("qgis-agent/" + self.options["provider"] + "_effort", self.options["effort"])
        if not self.fast_mode_available():
            self.options["fast_mode"] = False
        self.save_session()
        self.refresh_sessions()

    def select_effort(self, index):
        if self.running or index < 0:
            return
        self.options["effort"] = self.effort_selector.itemData(index)
        QSettings().setValue("qgis-agent/" + self.options["provider"] + "_effort", self.options["effort"])
        self.save_session()

    def select_fast_mode(self, enabled):
        if self.running or not self.fast_mode_available():
            return
        self.options["fast_mode"] = enabled
        QSettings().setValue("qgis-agent/" + self.options["provider"] + "_fast_mode", enabled)
        self.save_session()

    def fast_mode_available(self):
        model = self.options["model"]
        return (model.startswith("claude-opus-5") if self.options["provider"] == "claude"
                else model in {item[1] for item in CODEX_MODELS if item[1]})

    def effort_available(self):
        return (self.options["provider"] == "codex" or
                not self.options["model"].startswith("claude-haiku"))

    def select_approval_mode(self, index):
        if self.running or index < 0:
            return
        self.apply_approval_mode(self.approval_selector.itemData(index))

    def apply_approval_mode(self, mode, fallback="ask"):
        """Switch modes after informed consent; a declined dialog selects fallback."""
        if mode != "ask":
            description = (tr("Autoでは、AIがリスクを評価し、確認不要と判断したPythonコードを自動実行します。AIの判断は誤ることがあります。")
                           if mode == "auto" else
                           tr("Full autoでは、生成したPythonコードを実行前の確認なしで実行します。"))
            answer = QMessageBox.warning(
                self, tr("自動実行のリスクへの同意"),
                description + tr("\n\nコードはQGISと同じ権限で動作し、ファイルの変更・削除や外部へのデータ送信が可能です。"
                "変更を自動で元に戻すことはできません。\n\nリスクを理解し、このモードを有効にすることに同意しますか？"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            declined = answer != QMessageBox.StandardButton.Yes
            if declined:
                mode = fallback
        else:
            declined = False
        self.approval_selector.blockSignals(True)
        self.approval_selector.setCurrentIndex(self.approval_selector.findData(mode))
        self.approval_selector.blockSignals(False)
        self.options["approval_mode"] = mode
        settings = QSettings()
        settings.setValue("qgis-agent/approval_mode", mode)
        # A kept fallback such as Auto retains the consent it received earlier.
        if not declined or mode == "ask":
            settings.setValue("qgis-agent/consented_approval_mode", mode if mode != "ask" else "")
        return mode

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
        reasoning = preview.get("reasoning", "")
        if reasoning:
            if self.reasoning_notice is None:
                self.reasoning_notice = self.transcript.show_notice("")
                self.reasoning_notice.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.reasoning_notice.setText(tr("思考の要約\n") + reasoning)
        if preview.get("message") or preview.get("code"):
            if self.streaming_bubble is None:
                self.streaming_bubble = self.log(self.agent_label, "")
            self.streaming_bubble.update_content(preview["message"], preview["code"])
            self.show_wait_indicator(False)
            self.status.setText(self.agent_label + tr("が応答しています…"))

    def advance_wait_indicator(self):
        self.wait_frame = (self.wait_frame + 1) % len(self.wait_frames)
        self.wait_indicator.setText(self.wait_frames[self.wait_frame])

    def show_wait_indicator(self, waiting):
        if waiting:
            self.wait_frame = 0
            self.wait_indicator.setText(self.wait_frames[0])
            self.wait_indicator.show()
            self.wait_timer.start()
        else:
            self.wait_timer.stop()
            self.wait_indicator.hide()

    def set_busy(self, busy):
        self.running = busy
        if not busy:
            self.show_wait_indicator(False)
        self.send.setEnabled(not busy)
        self.input.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.model_selector.setEnabled(not busy)
        self.approval_selector.setEnabled(not busy)
        self.effort_selector.setEnabled(not busy and self.effort_available())
        self.fast_mode.setEnabled(not busy and self.fast_mode_available())
        self.reset.setEnabled(not busy)
        self.sessions.setEnabled(not busy)
        self.all_sessions_button.setEnabled(not busy)
        self.run.setEnabled(busy and self.pending_code is not None)
        self.stop.setEnabled(busy)
        self.stop.setVisible(busy)
        self.send.setVisible(not busy)
        self.run.setVisible(busy and self.pending_code is not None)
        self.run_always.setEnabled(self.run.isEnabled())
        self.run_always.setVisible(busy and self.pending_code is not None)
        if not busy:
            self.status.setText(tr("準備完了"))
            self.input.setFocus()

    def submit(self):
        message = self.input.toPlainText().strip()
        if not message or self.running:
            return
        executable_key = "codex_executable" if self.options["provider"] == "codex" else "executable"
        if not self.options[executable_key]:
            self.log(tr("エラー"), self.agent_label + tr("の実行パスを入力してください"))
            return
        issue = unavailable_reason(self.options["provider"], self.options[executable_key],
                                   self.options["model"])
        if issue:
            self.log(tr("エラー"), issue + tr("。モデルを変更するか、CLIを更新してください。"))
            return
        self.close_questions(message)
        self.history.append({"role": "user", "content": message})
        self.log("あなた", message)
        self.input.clear()
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
        self.reasoning_notice = None
        self.status.setText(self.agent_label + tr("の応答を待っています…"))
        self.show_wait_indicator(True)
        try:
            delta = self.history[self.sent_history:] if self.agent_started else self.history
            if self.agent_started:
                delta = [entry for entry in delta if entry["role"] != "assistant"]
            catalog = processing_catalog(QgsApplication.processingRegistry()) if not self.agent_started else None
            prompt = build_prompt(delta, self.runtime.context(catalog), generate_title=
                                  not self.session_title and not any(item["role"] == "assistant" for item in self.history),
                                  approval_mode=self.options["approval_mode"])
            self.request_history_end = len(self.history)
            if len(prompt.encode("utf-8")) > 500000:
                raise ValueError(tr("会話が上限に達しました。新しいセッションを開始してください"))
            executable_key = "codex_executable" if self.options["provider"] == "codex" else "executable"
            self.agent.request(self.options[executable_key], prompt, self.options["model"],
                               self.native_session_id or self.session_id, resume=self.agent_started,
                               provider=self.options["provider"],
                               enable_skills=self.options["enable_skills"],
                               enable_connectors=self.options["enable_connectors"],
                               codex_capabilities=self.options["codex_capabilities"],
                               effort=self.options["effort"] if self.effort_available() else "",
                               fast_mode=self.options["fast_mode"] and self.fast_mode_available())
        except Exception as exc:
            self.on_failure(str(exc))

    def on_session_opened(self, session_id):
        # An init event means the CLI owns this session, including interrupted turns.
        self.agent_started = True
        self.native_session_id = session_id
        self.sent_history = self.request_history_end
        if not self.save_session():
            self.agent.cancel(tr("セッション状態を保存できませんでした"))

    def on_response(self, response):
        if not self.running:
            return
        self.show_wait_indicator(False)
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
            if response.get("question", "").strip():
                self.ask_user(bubble, response["question"].strip(), response.get("choices", []))
            self.save_session()
            return
        self.pending_code = response["code"]
        if not self.save_session():
            self.on_failure(tr("保存に失敗したためコードを実行しませんでした"))
            return
        mode = self.options["approval_mode"]
        needs_approval = mode == "ask" or (mode == "auto" and response.get("requires_approval", True))
        if not needs_approval:
            self.execute()
        else:
            bubble.toggle.setChecked(True)
            for button in (self.run, self.run_always):
                button.setVisible(True)
                button.setEnabled(True)
            reason = response.get("approval_reason", "").strip()
            if not reason:
                reason = tr("Askモードのため実行前に確認します。") if mode == "ask" else tr("AIのリスク評価がないため、実行前に確認します。")
            self.log(tr("実行の確認"), reason + tr("\n承認して実行・今後は自動承認・停止のいずれかを選んでください。"))
            self.status.setText(tr("実行の承認待ち"))
            self.save_session()

    def approve_always(self):
        if self.pending_code is None or not self.running:
            return
        if self.apply_approval_mode("full_auto", fallback=self.options["approval_mode"]) == "full_auto":
            self.log("QGIS", tr("承認モードをFull autoに切り替えました。以降のPythonは確認なしで実行します。"))
            self.execute()

    def ask_user(self, bubble, question, choices):
        bubble.set_question(question, choices)
        bubble.choice_selected.connect(self.answer)
        self.status.setText(self.agent_label + tr("が回答を待っています"))

    def answer(self, text):
        if self.running:
            return
        # A pending draft would be lost otherwise; a choice replaces it only when empty.
        draft = self.input.toPlainText()
        self.input.setPlainText(text)
        self.submit()
        if draft.strip():
            self.input.setPlainText(draft)

    def close_questions(self, answer=None):
        for bubble in self.transcript.messages:
            if bubble.question:
                bubble.close_question(answer)

    def execute(self):
        if self.pending_code is None or not self.running:
            return
        self.show_wait_indicator(False)
        code, self.pending_code = self.pending_code, None
        for button in (self.run, self.run_always):
            button.setEnabled(False)
            button.hide()
        self.status.setText(tr("Pythonを実行中…"))
        result = self.runtime.execute(code)
        self.history.append({"role": "bridge", "content": result})
        self.log("QGIS · " + (tr("実行成功") if result["ok"] else tr("実行エラー")),
                 result["output"] + (result["error"] or "") or tr("（出力なし）"))
        self.status.setText(self.agent_label + tr("に実行結果を返します…"))
        # Yield to Qt so the canvas refresh and stop button can be processed.
        if self.save_session():
            self.continuation.start(0)
        else:
            self.on_failure(tr("実行結果を保存できなかったため停止しました"))

    def on_failure(self, message, show=True):
        self.continuation.stop()
        self.show_wait_indicator(False)
        self.pending_code = None
        self.history.append({"role": "bridge", "content": "Interaction stopped: " + message})
        if self.streaming_bubble is not None:
            self.streaming_bubble.role_key = self.agent_label + tr(" · 応答中断（未実行）")
            self.streaming_bubble.role.setText(self.streaming_bubble.role_key)
            self.streaming_bubble = None
        if show:
            self.log(tr("エラー / 停止"), message)
        self.set_busy(False)
        self.save_session()

    def on_login_required(self, detail):
        self.on_failure(detail, show=False)
        provider = self.options["provider"]
        card = self.transcript.show_login(self.agent_label, provider == "claude", detail)
        card.provider = provider
        card.login_clicked.connect(lambda: self.start_login(card))
        card.code_submitted.connect(self.login.submit_code)
        card.cancel_clicked.connect(self.login.cancel)
        if self.login.process is not None:
            card.set_waiting()
        self.status.setText(self.agent_label + tr("へのログインが必要です"))

    def start_login(self, card):
        if self.login.process is not None:
            return
        card.set_waiting()
        self.status.setText(tr("ブラウザでログインしてください…"))
        executable_key = "codex_executable" if card.provider == "codex" else "executable"
        self.login.start(card.provider, self.options[executable_key])

    def on_login_url(self, url):
        if self.transcript.login_card is not None:
            self.transcript.login_card.set_url(url)

    def on_login_finished(self, ok, detail):
        card = self.transcript.login_card
        if not ok:
            if card is not None:
                card.set_idle(tr("ログインできませんでした: ") + detail)
            if not self.running:
                self.status.setText(tr("ログインできませんでした"))
            return
        if card is None:
            # The prompt belonged to a session that is no longer shown.
            if not self.running:
                self.status.setText(tr("ログインしました"))
            return
        self.transcript.login_card = None
        card.set_done(card.agent + tr("にログインしました。メッセージを再送信します。"))
        if card.provider == self.options["provider"] and not self.running and self.history:
            self.set_busy(True)
            self.request()

    def cancel(self):
        self.continuation.stop()
        if self.agent.process is not None:
            self.agent.cancel()
        else:
            self.on_failure(tr("停止しました。未実行のコードは実行していません。"))

    def save_session(self):
        if self.options["provider"] == "claude":
            self.options["model"] = LEGACY_MODELS.get(self.options["model"], self.options["model"])
        title = self.session_title or next((item["content"][:50].replace("\n", " ") for item in self.history
                      if item["role"] == "user"), tr("新しいセッション"))
        payload = {"version": 1, "title": self.session_title, "history": self.history, "model": self.options["model"],
                   "effort": self.options["effort"], "fast_mode": self.options["fast_mode"],
                   "draft": self.input.toPlainText(), "interrupted": self.running,
                   "agent_started": self.agent_started, "sent_history": self.sent_history,
                   "provider": self.options["provider"], "native_session_id": self.native_session_id,
                   "context_usage": self.context_usage,
                   "codex_capabilities": self.options["codex_capabilities"],
                   "enable_skills": self.options["enable_skills"],
                   "enable_connectors": self.options["enable_connectors"],
                                "messages": [{"role": bubble.role_key, "text": bubble.message.text(),
                                 "code": bubble.code_text(), "question": bubble.question,
                                 "choices": bubble.choices} for bubble in self.transcript.messages
                                if bubble is not self.streaming_bubble]}
        try:
            self.session_id = self.store.save(self.session_id, "[" + self.agent_label + "] " + title, payload)
            index = self.sessions.findData(self.session_id)
            if index >= 0:
                self.sessions.setItemText(index, "[" + self.agent_label + "] " + title)
            QSettings().setValue("qgis-agent/last_session", self.session_id)
            return True
        except Exception as exc:
            self.log(tr("保存エラー"), str(exc))
            self.status.setText(tr("セッションを保存できませんでした"))
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
        self.model_selector.blockSignals(True)
        self.model_selector.clear()
        provider = self.options["provider"]
        executable = self.options["codex_executable" if provider == "codex" else "executable"]
        codex_listed = listed_codex_models(executable) if provider == "codex" else None
        for label, model in (CODEX_MODELS if provider == "codex" else MODEL_CHOICES):
            if ((not model or codex_listed is None or model in codex_listed) and
                    not unavailable_reason(provider, executable, model)):
                self.model_selector.addItem(label, model)
        index = self.model_selector.findData(self.options["model"])
        if index < 0:
            # Keep the saved choice visible, but prevent an incompatible request.
            issue = unavailable_reason(provider, executable, self.options["model"])
            label = tr("利用不可: ") if issue else tr("以前の設定: ")
            self.model_selector.addItem(label + self.options["model"], self.options["model"])
            if issue:
                self.model_selector.setItemData(self.model_selector.count() - 1, issue, Qt.ItemDataRole.ToolTipRole)
            index = self.model_selector.count() - 1
        self.model_selector.setCurrentIndex(index)
        self.model_selector.blockSignals(False)
        self.effort_selector.blockSignals(True)
        self.effort_selector.setCurrentIndex(max(0, self.effort_selector.findData(self.options["effort"])))
        self.effort_selector.setEnabled(not self.running and self.effort_available())
        self.effort_selector.blockSignals(False)
        self.fast_mode.blockSignals(True)
        self.fast_mode.setChecked(self.options["fast_mode"] and self.fast_mode_available())
        self.fast_mode.setEnabled(not self.running and self.fast_mode_available())
        self.fast_mode.setToolTip(
            tr("次の応答から高速モードを使います。追加の利用料金やクレジットが必要です。")
            if self.fast_mode_available() else tr("選択中のモデルでは Fast mode を指定できません。"))
        self.fast_mode.blockSignals(False)
        self.update_context_meter()

    def update_context_meter(self):
        summary, value = context_meter(self.context_usage, self.options["model"])
        self.context_ring.set_value(value)
        self.context_ring.setToolTip(summary)

    def on_usage_updated(self, usage):
        self.context_usage = usage
        self.update_context_meter()

    def open_session_picker(self):
        if self.running:
            return
        self.draft_timer.stop()
        if not self.save_session():
            return
        picker = SessionPicker(self.store, self)
        accepted = picker.exec() == QDialog.DialogCode.Accepted
        if not self.store.exists(self.session_id):
            target = picker.selected_id if accepted else self.store.latest_id()
            if target:
                self.load_session(target)
            else:
                self.start_session()
        elif accepted and picker.selected_id != self.session_id:
            self.load_session(picker.selected_id)
        else:
            self.refresh_sessions()

    def load_session(self, session_id):
        try:
            payload = self.store.load(session_id)
        except Exception as exc:
            self.log(tr("読込エラー"), str(exc))
            return False
        self.session_id = session_id
        self.session_title = payload.get("title", "")
        self.context_usage = payload.get("context_usage")
        # Earlier versions persisted this UI-only notice; remove it without changing
        # the cursor that tracks which history entries were sent to the CLI.
        old_history = payload["history"]
        self.sent_history = payload.get("sent_history", 0)
        self.sent_history -= sum(
            entry.get("role") == "bridge" and
            isinstance(entry.get("content"), str) and entry["content"].startswith(RESTORE_NOTICE)
            for entry in old_history[:self.sent_history])
        self.history = [entry for entry in old_history if not (
            entry.get("role") == "bridge" and isinstance(entry.get("content"), str) and
            entry["content"].startswith(RESTORE_NOTICE))]
        self.options["provider"] = payload.get("provider", "claude")
        self.options["codex_capabilities"] = payload.get("codex_capabilities", {})
        self.agent_started = payload.get("agent_started", payload.get("claude_started", False))
        self.native_session_id = payload.get("native_session_id") or (session_id if self.agent_started else None)
        self.options["model"] = payload.get("model", "")
        self.options["effort"] = payload.get("effort") or default_effort(self.options["provider"], self.options["model"])
        self.options["fast_mode"] = payload.get("fast_mode", False)
        for key in ("enable_skills", "enable_connectors"):
            self.options[key] = payload.get(key, False)
        self.input.setPlainText(payload.get("draft", ""))
        self.pending_code = None
        self.streaming_bubble = None
        self.reasoning_notice = None
        self.runtime = QgisRuntime(self.runtime.iface)
        self.transcript.clear()
        for message in payload["messages"]:
            if message["role"] == "QGIS" and (
                    message["text"].startswith(RESTORE_NOTICE) or
                    message["text"] == NEW_SESSION_NOTICE):
                continue
            bubble = self.log(message["role"], message["text"])
            bubble.update_content(message["text"], message["code"])
            if message.get("question"):
                bubble.set_question(message["question"], message.get("choices", []))
                bubble.choice_selected.connect(self.answer)
        # Only a question that is still the latest turn can be answered after restoring.
        answered = False
        for bubble in reversed(self.transcript.messages):
            if bubble.question and (answered or bubble.role_key != self.agent_label):
                bubble.close_question()
            answered = answered or bubble.role_key in ("あなた", self.agent_label)
        if self.history:
            note = tr(RESTORE_NOTICE)
            if payload.get("interrupted"):
                note += tr(" 前回の処理は途中で終了しています。変更が部分的に適用されている可能性があります。")
            self.transcript.show_notice(note)
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

    def new_chat(self, provider=None):
        if self.running:
            return
        provider = provider or self.options["provider"]
        if not self.history and not self.agent_started and not self.input.toPlainText().strip():
            if provider != self.options["provider"]:
                previous = {key: self.options[key] for key in ("provider", "model", "effort", "fast_mode")}
                self.options["provider"] = provider
                self.options["model"] = QSettings().value("qgis-agent/" + ("codex_model" if provider == "codex" else "model"), "")
                self.options["effort"] = (QSettings().value("qgis-agent/" + provider + "_effort", "")
                                          or default_effort(provider, self.options["model"]))
                self.options["fast_mode"] = QSettings().value("qgis-agent/" + provider + "_fast_mode", False, type=bool)
                if not self.save_session():
                    self.options.update(previous)
                self.refresh_sessions()
            return
        if self.save_session():
            self.start_session(provider)

    def start_session(self, provider=None):
        self.options["codex_capabilities"] = json.loads(QSettings().value("qgis-agent/codex_capabilities", "{}"))
        if provider is not None:
            self.options["provider"] = provider
        self.agent_started = False
        self.native_session_id = None
        self.sent_history = 0
        self.session_id = None
        self.session_title = ""
        self.context_usage = None
        self.history = []
        self.pending_code = None
        self.input.clear()
        self.runtime = QgisRuntime(self.runtime.iface)
        self.transcript.clear()
        self.streaming_bubble = None
        self.reasoning_notice = None
        self.options["model"] = QSettings().value("qgis-agent/" + ("codex_model" if self.options["provider"] == "codex" else "model"), "")
        self.options["effort"] = (QSettings().value("qgis-agent/" + self.options["provider"] + "_effort", "")
                                  or default_effort(self.options["provider"], self.options["model"]))
        self.options["fast_mode"] = QSettings().value("qgis-agent/" + self.options["provider"] + "_fast_mode", False, type=bool)
        for key in ("enable_skills", "enable_connectors"):
            self.options[key] = QSettings().value("qgis-agent/" + key, False, type=bool)
        self.transcript.show_notice(tr(NEW_SESSION_NOTICE))
        self.save_session()
        self.refresh_sessions()

    def shutdown(self):
        self.continuation.stop()
        self.draft_timer.stop()
        if self.running:
            self.cancel()
        self.save_session()
        self.login.cancel()
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
