from .i18n import tr, tr_label
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt, QSettings, QSize, QTimer
from qgis.PyQt.QtWidgets import (QAction, QApplication, QCheckBox, QComboBox, QDialog, QDockWidget, QHBoxLayout,
                                QMenu, QMessageBox, QLabel, QPushButton, QSystemTrayIcon, QToolButton,
                                QVBoxLayout, QWidget)
from .chat_ui import ChatInput, ChatTranscript, ContextRing, SettingsDialog
from .auth import LoginProcess
from .session import CODEX_MODELS, MODEL_CHOICES, AgentSession, migrate_legacy_settings
from .session_ui import SessionPicker
from .icons import icon
from .usage import context_meter
from .model_compat import listed_codex_models, unavailable_reason


class AgentDock(QDockWidget):
    """Chat dock over one AgentSession; it renders state and forwards user actions."""

    def __init__(self, iface, session_path=None):
        super().__init__("Qtaro", iface.mainWindow())
        self.setObjectName("QtaroDock")
        self.session = session = AgentSession(self, iface, session_path)
        session.message_added.connect(self.on_message_added)
        session.message_changed.connect(self.on_message_changed)
        session.question_asked.connect(self.on_question_asked)
        session.approval_requested.connect(self.on_approval_requested)
        session.notice.connect(self.transcript_notice)
        session.reasoning.connect(self.on_reasoning)
        session.status_changed.connect(self.set_status)
        session.submitted.connect(self.on_submitted)
        session.turn_started.connect(self.on_turn_started)
        session.attention_needed.connect(self.notify)
        session.busy_changed.connect(self.set_busy)
        session.waiting_changed.connect(self.show_wait_indicator)
        session.login_required.connect(self.on_login_required)
        session.usage_changed.connect(self.update_context_meter)
        session.saved.connect(self.on_saved)
        session.reset.connect(self.on_reset)
        session.changed.connect(self.refresh_sessions)
        self.login = LoginProcess(self)
        self.login.url_found.connect(self.on_login_url)
        self.login.finished.connect(self.on_login_finished)
        self.reasoning_notice = None
        self.tray = None
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
            QToolButton#stepsToggle { border: none; font-size: 11px; }
            QWidget#stepsBody QFrame#agentBubble { background: transparent; border-left: 2px solid palette(midlight); border-radius: 0; }
            QWidget#stepsBody QTextBrowser { font-size: 11px; }
            QPlainTextEdit { border: 1px solid palette(mid); border-radius: 8px; padding: 8px; }
            QPushButton { padding: 6px 10px; }
            QToolButton#iconButton::menu-indicator { image: none; width: 0; }
        """)
        header = QHBoxLayout()
        self.reset = self.icon_button("new_session", tr("New session"))
        self.reset.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        new_menu = QMenu(self.reset)
        for label, provider in (("Claude", "claude"), ("Codex", "codex")):
            new_menu.addAction(label, lambda checked=False, provider=provider: self.session.new_chat(provider))
        self.reset.setMenu(new_menu)
        self.sessions = QComboBox()
        self.sessions.setMinimumContentsLength(12)
        self.sessions.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.sessions.setToolTip(tr("Switch sessions (autosaved)"))
        self.all_sessions_button = self.icon_button("sessions", tr("Sessions"))
        self.settings_button = self.icon_button("settings", tr("Settings"))
        header.addWidget(self.reset)
        header.addWidget(self.sessions, 1)
        header.addWidget(self.all_sessions_button)
        header.addWidget(self.settings_button)
        layout.addLayout(header)
        self.transcript = ChatTranscript()
        layout.addWidget(self.transcript, 1)
        status_row = QHBoxLayout()
        self.status = QLabel()
        self.status.hide()
        status_row.addWidget(self.status)
        self.wait_indicator = QLabel()
        self.wait_indicator.setAccessibleName(tr("Waiting for response"))
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
        self.input.setPlaceholderText(tr("Describe what you want to do in QGIS…\nEnter to send · Shift+Enter for a new line"))
        self.input.setFixedHeight(88)
        layout.addWidget(self.input)
        controls = QHBoxLayout()
        controls.setContentsMargins(2, 0, 2, 0)
        self.context_ring = ContextRing()
        controls.addWidget(self.context_ring)
        self.approval_selector = QComboBox()
        self.approval_selector.setAccessibleName(tr("Approval mode"))
        self.approval_selector.setToolTip(tr("Ask: confirm each run / Auto: AI assesses risk / Full auto: run without confirmation"))
        for label, mode in (("Ask", "ask"), ("Auto", "auto"), ("Full auto", "full_auto")):
            self.approval_selector.addItem(label, mode)
        self.approval_selector.setCurrentIndex(self.approval_selector.findData(session.options["approval_mode"]))
        self.approval_selector.currentIndexChanged.connect(self.select_approval_mode)
        controls.addWidget(self.approval_selector)
        self.model_selector = QComboBox()
        self.model_selector.setAccessibleName(tr("Model"))
        self.model_selector.setToolTip(tr("Model for this session"))
        for label, model in MODEL_CHOICES:
            self.model_selector.addItem(label, model)
        controls.addWidget(self.model_selector)
        self.effort_selector = QComboBox()
        self.effort_selector.setAccessibleName("Effort")
        self.effort_selector.setToolTip(tr("Reasoning effort for the next response. Levels and availability vary by model and CLI."))
        for label, effort in (("Low", "low"), ("Medium", "medium"),
                              ("High", "high"), ("Xhigh", "xhigh"), ("Max", "max")):
            self.effort_selector.addItem(label, effort)
        controls.addWidget(self.effort_selector)
        self.fast_mode = QCheckBox("Fast")
        self.fast_mode.setAccessibleName("Fast mode")
        self.fast_mode.setToolTip(tr("Use fast mode for the next response. Requires a supported model and account."))
        controls.addWidget(self.fast_mode)
        controls.addStretch()
        self.run = QPushButton(tr("Approve and run"))
        self.run_always = QPushButton(tr("Always approve"))
        self.run_always.setToolTip(tr("Approve and run, then switch to Full auto without further confirmation"))
        controls.addWidget(self.run)
        controls.addWidget(self.run_always)
        self.send = self.icon_button("send", tr("Send"), 26)
        controls.addWidget(self.send)
        self.stop = self.icon_button("stop", tr("Stop"), 26)
        controls.addWidget(self.stop)
        layout.addLayout(controls)
        self.setWidget(body)
        self.send.clicked.connect(self.submit)
        self.input.submitted.connect(self.submit)
        self.settings_button.clicked.connect(self.open_settings)
        self.run.clicked.connect(self.execute)
        self.run_always.clicked.connect(self.approve_always)
        self.stop.clicked.connect(session.cancel)
        self.sessions.currentIndexChanged.connect(self.switch_session)
        self.all_sessions_button.clicked.connect(self.open_session_picker)
        self.model_selector.currentIndexChanged.connect(self.select_model)
        self.effort_selector.currentIndexChanged.connect(self.select_effort)
        self.fast_mode.toggled.connect(self.select_fast_mode)
        self.set_busy(False)
        session.restore()
        self.refresh_sessions()
        self.draft_timer = QTimer(self)
        self.draft_timer.setSingleShot(True)
        self.draft_timer.timeout.connect(session.save)
        self.input.textChanged.connect(self.on_draft_changed)

    def set_status(self, text):
        # Idle needs no label; hiding it lets the status row collapse.
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def icon_button(self, name, label, size=20):
        button = QToolButton()
        button.setObjectName("iconButton")
        button.setIcon(icon(name))
        button.setIconSize(QSize(size, size))
        button.setAutoRaise(True)
        button.setToolTip(label)
        button.setAccessibleName(label)
        return button

    def on_draft_changed(self):
        self.session.draft = self.input.toPlainText()
        self.draft_timer.start(500)

    def select_model(self, index):
        if self.session.running or index < 0:
            return
        self.session.set_model(self.model_selector.itemData(index))

    def select_effort(self, index):
        if self.session.running or index < 0:
            return
        self.session.set_effort(self.effort_selector.itemData(index))

    def select_fast_mode(self, enabled):
        self.session.set_fast_mode(enabled)

    def select_approval_mode(self, index):
        if self.session.running or index < 0:
            return
        self.apply_approval_mode(self.approval_selector.itemData(index))

    def apply_approval_mode(self, mode, fallback="ask"):
        """Switch modes after informed consent; a declined dialog selects fallback."""
        if mode != "ask":
            description = (tr("In Auto mode, the AI runs Python code it considers safe without asking. Its assessment may be wrong.")
                           if mode == "auto" else
                           tr("In Full auto mode, generated Python code runs without prior confirmation."))
            answer = QMessageBox.warning(
                self, tr("Consent to automatic execution"),
                description + tr("\n\nCode runs with QGIS's permissions and can change or delete files or send data externally. "
                "Changes cannot be automatically undone.\n\n"
                "Do you understand these risks and agree to enable this mode?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            declined = answer != QMessageBox.StandardButton.Yes
            if declined:
                mode = fallback
        else:
            declined = False
        self.approval_selector.blockSignals(True)
        self.approval_selector.setCurrentIndex(self.approval_selector.findData(mode))
        self.approval_selector.blockSignals(False)
        # A kept fallback such as Auto retains the consent it received earlier.
        self.session.set_approval_mode(mode, record_consent=not declined or mode == "ask")
        return mode

    def open_settings(self):
        dialog = SettingsDialog(self.session.options, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.session.update_settings(dialog.options())

    def transcript_notice(self, text):
        self.transcript.show_notice(text)

    def on_message_added(self, index):
        message = self.session.messages[index]
        bubble = self.transcript.add_message(message["role"], message["text"])
        if message["code"]:
            bubble.update_content(message["text"], message["code"])

    def on_message_changed(self, index):
        message = self.session.messages[index]
        bubble = self.transcript.messages[index]
        if bubble.role_key != message["role"]:
            bubble.role_key = message["role"]
            bubble.role.setText(tr_label(message["role"]))
        bubble.update_content(message["text"], message["code"], animate=True)

    def on_question_asked(self, index):
        self.show_question(self.transcript.messages[index], self.session.messages[index])

    def show_question(self, bubble, message):
        if message["question"]:
            bubble.set_question(message["question"], message["choices"],
                                message["path_request"], message["path_suggestion"])
        else:
            bubble.set_suggestion(message["suggestion"])
        bubble.choice_selected.connect(self.answer)

    def on_reset(self):
        self.reasoning_notice = None
        self.input.setPlainText(self.session.draft)
        self.transcript.clear()
        for index, message in enumerate(self.session.messages):
            self.on_message_added(index)
            if message["question"] or message["suggestion"]:
                self.show_question(self.transcript.messages[index], message)
        # Only a question that is still the latest turn can be answered after restoring.
        open_index = self.session.open_question_index()
        for index, bubble in enumerate(self.transcript.messages):
            if (bubble.question or bubble.suggestion) and index != open_index:
                bubble.close_question()

    def on_turn_started(self):
        self.reasoning_notice = None

    def notify(self, message):
        """Show a desktop notification with the session title when QGIS is in the background."""
        if (not self.session.options["notifications"] or QApplication.activeWindow() is not None or
                not QSystemTrayIcon.isSystemTrayAvailable()):
            return
        if self.tray is None:
            self.tray = QSystemTrayIcon(self.parentWidget().windowIcon(), self)
            self.tray.setToolTip("Qtaro")
            self.tray.messageClicked.connect(self.on_notification_clicked)
            self.tray.activated.connect(self.on_notification_clicked)
            QApplication.instance().applicationStateChanged.connect(self.on_application_state_changed)
        body = " ".join(message.split())
        self.tray.show()
        self.tray.showMessage(self.session.listed_title, body[:120] + ("…" if len(body) > 120 else ""),
                              QSystemTrayIcon.MessageIcon.Information)

    def on_notification_clicked(self, *args):
        window = self.parentWidget()
        if window.isMinimized():
            window.showNormal()
        window.raise_()
        window.activateWindow()
        self.show()
        self.raise_()

    def on_application_state_changed(self, state):
        # The tray icon only exists to carry notifications; drop it once the user is back.
        if state == Qt.ApplicationState.ApplicationActive and self.tray is not None:
            self.tray.hide()

    def on_reasoning(self, reasoning):
        if self.reasoning_notice is None:
            self.reasoning_notice = self.transcript.show_notice("", step=True)
            self.reasoning_notice.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.reasoning_notice.setText(tr("Reasoning summary\n") + reasoning)

    def advance_wait_indicator(self):
        self.wait_frame = (self.wait_frame + 1) % len(self.wait_frames)
        self.wait_indicator.setText(self.wait_frames[self.wait_frame])
        if self.session.job is not None:
            self.set_status(tr("Running Processing in the background… ") + f"{self.session.job.progress():.0f}%")

    def show_wait_indicator(self, waiting):
        if waiting:
            self.wait_frame = 0
            self.wait_indicator.setText(self.wait_frames[0])
            self.wait_indicator.show()
            self.wait_timer.start()
            if self.session.job is not None:
                self.advance_wait_indicator()
        else:
            self.wait_timer.stop()
            self.wait_indicator.hide()

    def set_busy(self, busy):
        session = self.session
        if not busy:
            self.show_wait_indicator(False)
        self.send.setEnabled(not busy)
        self.input.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.model_selector.setEnabled(not busy)
        self.approval_selector.setEnabled(not busy)
        self.effort_selector.setEnabled(not busy and session.effort_available())
        self.fast_mode.setEnabled(not busy and session.fast_mode_available())
        self.reset.setEnabled(not busy)
        self.sessions.setEnabled(not busy)
        self.all_sessions_button.setEnabled(not busy)
        self.run.setEnabled(busy and session.pending_code is not None)
        self.stop.setEnabled(busy)
        self.stop.setVisible(busy)
        self.send.setVisible(not busy)
        self.run.setVisible(busy and session.pending_code is not None)
        self.run_always.setEnabled(self.run.isEnabled())
        self.run_always.setVisible(busy and session.pending_code is not None)
        if not busy:
            self.set_status("")
            self.input.setFocus()

    def submit(self):
        self.session.submit(self.input.toPlainText())

    def on_submitted(self, message):
        self.close_questions(message)
        self.input.clear()

    def on_approval_requested(self, index):
        self.transcript.messages[index].toggle.setChecked(True)
        for button in (self.run, self.run_always):
            button.setVisible(True)
            button.setEnabled(True)

    def execute(self):
        if self.session.pending_code is None or not self.session.running:
            return
        for button in (self.run, self.run_always):
            button.setEnabled(False)
            button.hide()
        self.session.execute()

    def approve_always(self):
        if self.session.pending_code is None or not self.session.running:
            return
        if self.apply_approval_mode("full_auto", fallback=self.session.options["approval_mode"]) == "full_auto":
            self.session.log("QGIS", tr("Switched to Full auto. Future Python code will run without confirmation."))
            self.execute()

    def answer(self, text):
        if self.session.running:
            return
        # A pending draft would be lost otherwise; a choice replaces it only when empty.
        draft = self.input.toPlainText()
        self.input.setPlainText(text)
        self.submit()
        if draft.strip():
            self.input.setPlainText(draft)

    def close_questions(self, answer=None):
        for bubble in self.transcript.messages:
            if bubble.question or bubble.suggestion:
                bubble.close_question(answer)

    def on_login_required(self, detail):
        provider = self.session.options["provider"]
        card = self.transcript.show_login(self.session.agent_label, provider == "claude", detail)
        card.provider = provider
        card.login_clicked.connect(lambda: self.start_login(card))
        card.code_submitted.connect(self.login.submit_code)
        card.cancel_clicked.connect(self.login.cancel)
        if self.login.process is not None:
            card.set_waiting()
        self.set_status(self.session.agent_label + tr(" sign-in required"))

    def start_login(self, card):
        if self.login.process is not None:
            return
        card.set_waiting()
        self.set_status(tr("Sign in in your browser…"))
        executable_key = "codex_executable" if card.provider == "codex" else "executable"
        self.login.start(card.provider, self.session.options[executable_key])

    def on_login_url(self, url):
        if self.transcript.login_card is not None:
            self.transcript.login_card.set_url(url)

    def on_login_finished(self, ok, detail):
        card = self.transcript.login_card
        if not ok:
            if card is not None:
                card.set_idle(tr("Sign-in failed: ") + detail)
            if not self.session.running:
                self.set_status(tr("Sign-in failed"))
            return
        if card is None:
            # The prompt belonged to a session that is no longer shown.
            if not self.session.running:
                self.set_status(tr("Signed in"))
            return
        self.transcript.login_card = None
        card.set_done(card.agent + tr(" signed in. Resending your message."))
        if card.provider == self.session.options["provider"]:
            self.session.resume()

    def on_saved(self):
        index = self.sessions.findData(self.session.session_id)
        if index >= 0:
            self.sessions.setItemText(index, self.session.listed_title)

    def refresh_sessions(self):
        session = self.session
        self.sessions.blockSignals(True)
        self.sessions.clear()
        for session_id, title, updated in session.store.list():
            self.sessions.addItem(title, session_id)
        self.sessions.setCurrentIndex(self.sessions.findData(session.session_id))
        self.sessions.blockSignals(False)
        session.normalize_model()
        self.model_selector.blockSignals(True)
        self.model_selector.clear()
        provider = session.options["provider"]
        executable = session.options["codex_executable" if provider == "codex" else "executable"]
        codex_listed = listed_codex_models(executable) if provider == "codex" else None
        for label, model in (CODEX_MODELS if provider == "codex" else MODEL_CHOICES):
            if ((not model or codex_listed is None or model in codex_listed) and
                    not unavailable_reason(provider, executable, model)):
                self.model_selector.addItem(label, model)
        index = self.model_selector.findData(session.options["model"])
        if index < 0:
            # Keep the saved choice visible, but prevent an incompatible request.
            issue = unavailable_reason(provider, executable, session.options["model"])
            label = tr("Unavailable: ") if issue else tr("Previous setting: ")
            self.model_selector.addItem(label + session.options["model"], session.options["model"])
            if issue:
                self.model_selector.setItemData(self.model_selector.count() - 1, issue, Qt.ItemDataRole.ToolTipRole)
            index = self.model_selector.count() - 1
        self.model_selector.setCurrentIndex(index)
        self.model_selector.blockSignals(False)
        self.effort_selector.blockSignals(True)
        self.effort_selector.setCurrentIndex(max(0, self.effort_selector.findData(session.options["effort"])))
        self.effort_selector.setEnabled(not session.running and session.effort_available())
        self.effort_selector.blockSignals(False)
        self.fast_mode.blockSignals(True)
        self.fast_mode.setChecked(session.options["fast_mode"] and session.fast_mode_available())
        self.fast_mode.setEnabled(not session.running and session.fast_mode_available())
        self.fast_mode.setToolTip(
            tr("Use fast mode for the next response. Additional charges or credits may apply.")
            if session.fast_mode_available() else tr("Fast mode is unavailable for the selected model."))
        self.fast_mode.blockSignals(False)
        self.update_context_meter()

    def update_context_meter(self):
        summary, value = context_meter(self.session.context_usage, self.session.options["model"])
        self.context_ring.set_value(value)
        self.context_ring.setToolTip(summary)

    def open_session_picker(self):
        session = self.session
        if session.running:
            return
        self.draft_timer.stop()
        if not session.save():
            return
        picker = SessionPicker(session.store, self)
        accepted = picker.exec() == QDialog.DialogCode.Accepted
        if not session.store.exists(session.session_id):
            target = picker.selected_id if accepted else session.store.latest_id()
            if target:
                session.load(target)
            else:
                session.start()
        elif accepted and picker.selected_id != session.session_id:
            session.load(picker.selected_id)
        else:
            self.refresh_sessions()

    def switch_session(self, index):
        target = self.sessions.itemData(index)
        if self.session.running or not target or target == self.session.session_id:
            return
        self.session.switch_to(target)
        self.refresh_sessions()

    def shutdown(self):
        self.draft_timer.stop()
        if self.tray is not None:
            QApplication.instance().applicationStateChanged.disconnect(self.on_application_state_changed)
            self.tray.hide()
        self.login.cancel()
        self.session.shutdown()


class QtaroPlugin:
    def __init__(self, iface, session_path=None):
        self.iface = iface
        self.session_path = session_path
        self.dock = None
        self.action = None
        self.processing_provider = None

    def initGui(self):
        from .processing_provider import AgentProcessingProvider
        from .protocol import install_bundled_skills
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
