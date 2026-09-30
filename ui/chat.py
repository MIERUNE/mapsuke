"""Chat presentation and local preferences; no agent or QGIS execution knowledge."""
from ..i18n import tr
from qgis.PyQt.QtCore import QEvent, QRectF, Qt, QTimer, QUrl, pyqtSignal
from configparser import ConfigParser
from math import ceil
from pathlib import Path

from qgis.gui import QgsCodeEditorPython
from qgis.PyQt.Qsci import QsciScintilla
from qgis.PyQt.QtGui import QColor, QDesktopServices, QPainter, QPalette, QPen, QTextOption
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                                QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                                QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
                                QTabWidget, QTextBrowser, QToolButton, QVBoxLayout, QWidget)


class ChatInput(QPlainTextEdit):
    submitted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.composing = False

    def inputMethodEvent(self, event):
        self.composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            # Let the platform IME consume Enter while converting Japanese text.
            if self.composing:
                super().keyPressEvent(event)
                return
            if not event.isAutoRepeat():
                self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ContextRing(QWidget):
    """Show a context percentage without implying zero when usage is unknown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = None
        self.setFixedSize(24, 24)
        self.setAccessibleName(tr("Context usage"))

    def set_value(self, value):
        self.value = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        circle = QRectF(3.5, 3.5, 17, 17)
        painter.setPen(QPen(self.palette().midlight().color(), 3))
        painter.drawEllipse(circle)
        if self.value is not None and self.value > 0:
            progress = QPen(self.palette().highlight().color(), 3)
            progress.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(progress)
            painter.drawArc(circle, 90 * 16, -round(360 * 16 * self.value / 1000))


class MessageText(QTextBrowser):
    """Fit the transcript width and grow vertically with the rendered document."""

    def __init__(self, markdown):
        super().__init__()
        self.markdown = markdown
        self.source = ""
        self.shown = ""
        # Pipe chunks arrive in bursts; reveal streamed text at a steady pace instead.
        self.reveal = QTimer(self)
        self.reveal.setInterval(33)
        self.reveal.timeout.connect(self._reveal_step)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.setOpenExternalLinks(True)
        self.document().documentLayout().documentSizeChanged.connect(self._fit_height)
        self.horizontalScrollBar().rangeChanged.connect(self._fit_height)

    def text(self):
        # Session persistence and streaming updates use the original Markdown.
        return self.source

    def setText(self, text, animate=False):
        self.source = text
        if animate and text.startswith(self.shown) and len(text) > len(self.shown):
            if not self.reveal.isActive():
                self.reveal.start()
            return
        self.reveal.stop()
        self._render(text)

    def _reveal_step(self):
        backlog = len(self.source) - len(self.shown)
        # Speed up with the backlog so the display never lags far behind the stream.
        self._render(self.source[:len(self.shown) + max(1, ceil(backlog / 10))])
        if len(self.shown) >= len(self.source):
            self.reveal.stop()

    def _render(self, text):
        self.shown = text
        if self.markdown:
            self.setMarkdown(text)
        else:
            self.setPlainText(text)
        self._fit_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_height()

    def _fit_height(self, *args):
        height = ceil(self.document().size().height()) + 2 * self.frameWidth()
        # Wide tables can scroll locally without widening the whole transcript.
        if self.horizontalScrollBar().maximum() > 0:
            height += self.horizontalScrollBar().sizeHint().height()
        self.setFixedHeight(max(1, height))


class MessageBubble(QFrame):
    choice_selected = pyqtSignal(str)

    def __init__(self, role, text):
        super().__init__()
        self.setObjectName("userBubble" if role == tr("You") else "agentBubble")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        self.role_key = role
        self.role = QLabel(role)
        self.role.setObjectName("messageRole")
        layout.addWidget(self.role)
        # Interrupted replies retain the agent name before the status suffix.
        self.is_agent = role.split(" · ", 1)[0] in ("Claude", "Codex")
        self.message = MessageText(self.is_agent)
        layout.addWidget(self.message)
        self.toggle = QToolButton()
        self.toggle.setText(tr("Python code"))
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        layout.addWidget(self.toggle)
        # Scintilla editors are heavy; restored sessions create them only for replies with code.
        self.code = None
        self.code_source = ""
        self.question = ""
        self.choices = []
        self.choice_buttons = []
        self.path_request = ""
        self.path_suggestion = ""
        self.suggestion = ""
        self.toggle.toggled.connect(self.expand_code)
        self.toggle.hide()
        self.update_content(text)

    def _code_editor(self):
        if self.code is None:
            # Follows the QGIS Python editor color scheme, including dark themes.
            self.code = QgsCodeEditorPython()
            self.code.setReadOnly(True)
            # A viewer, not an editor: drop editing aids that read as noise in a chat bubble.
            self.code.setWhitespaceVisibility(QsciScintilla.WhitespaceVisibility.WsInvisible)
            self.code.setEdgeMode(QsciScintilla.EdgeMode.EdgeNone)
            self.code.setBraceMatching(QsciScintilla.BraceMatch.NoBraceMatch)
            self.code.setFolding(QsciScintilla.FoldStyle.NoFoldStyle)
            self.code.setCaretLineVisible(False)
            self.code.setMinimumHeight(100)
            self.code.setMaximumHeight(220)
            self.code.hide()
            self.layout().addWidget(self.code)
        return self.code

    def code_text(self):
        return self.code_source

    def set_question(self, question, choices, path_request="", path_suggestion=""):
        self.question, self.choices = question, list(choices)
        self.path_request, self.path_suggestion = path_request, path_suggestion
        prompt = QLabel(question)
        prompt.setObjectName("agentQuestion")
        prompt.setWordWrap(True)
        prompt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.layout().addWidget(prompt)
        for choice in self.choices:
            button = QPushButton(choice)
            button.setObjectName("agentChoice")
            button.clicked.connect(lambda checked=False, text=choice: self.choice_selected.emit(text))
            self.layout().addWidget(button)
            self.choice_buttons.append(button)
        if path_request:
            button = QPushButton(tr("Choose folder…") if path_request == "directory" else tr("Choose location…"))
            button.setObjectName("agentChoice")
            button.clicked.connect(self.choose_path)
            self.layout().addWidget(button)
            self.choice_buttons.append(button)
        hint = QLabel(tr("You can also answer freely in the input field.") if self.choices or path_request else tr("Answer in the input field."))
        hint.setObjectName("questionHint")
        self.layout().addWidget(hint)
        self.hint = hint

    def set_suggestion(self, suggestion):
        # An optional next step: one button, without the question prompt or answer hint.
        self.suggestion = suggestion
        button = QPushButton(suggestion)
        button.setObjectName("agentChoice")
        button.clicked.connect(lambda checked=False: self.choice_selected.emit(suggestion))
        self.layout().addWidget(button)
        self.choice_buttons.append(button)

    def choose_path(self):
        # The native save dialog confirms overwriting, so the chosen path is a deliberate answer.
        if self.path_request == "directory":
            path = QFileDialog.getExistingDirectory(self, self.question, self.path_suggestion)
        else:
            suffix = Path(self.path_suggestion).suffix
            filters = ([f"{suffix[1:].upper()} (*{suffix})"] if suffix else []) + [tr("All files (*)")]
            path, _ = QFileDialog.getSaveFileName(self, self.question, self.path_suggestion, ";;".join(filters))
        if path:
            self.choice_selected.emit(str(Path(path)))

    def close_question(self, answer=None):
        for button in self.choice_buttons:
            button.setEnabled(False)
            if button.text() == answer:
                button.setText("✓ " + answer)
        if self.question:
            self.hint.hide()

    def expand_code(self, expanded):
        if self.code is not None:
            self.code.setVisible(expanded and bool(self.code_source))
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

    def update_content(self, message, code="", animate=False):
        self.message.setText(message, animate)
        self.message.setVisible(bool(message))
        self.toggle.setVisible(bool(code))
        if code != self.code_source:
            self.code_source = code
            self._code_editor().setText(code)
        if self.code is not None:
            self.code.setVisible(bool(code) and self.toggle.isChecked())


class LoginCard(QFrame):
    """Prompt to sign in; the dock owns the login process and drives the states."""
    login_clicked = pyqtSignal()
    code_submitted = pyqtSignal(str)
    cancel_clicked = pyqtSignal()

    def __init__(self, label, accepts_code, detail=""):
        super().__init__()
        self.setObjectName("agentBubble")
        self.agent = label
        self.accepts_code = accepts_code
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        role = QLabel(label + tr(" · Sign-in required"))
        role.setObjectName("messageRole")
        layout.addWidget(role)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setToolTip(detail)
        layout.addWidget(self.text)
        self.link = QLabel()
        self.link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.link.linkActivated.connect(self._open_link)
        layout.addWidget(self.link)
        code_row = QHBoxLayout()
        self.code = QLineEdit()
        self.code.setPlaceholderText(tr("Paste the code shown in your browser"))
        self.send_code = QPushButton(tr("Submit code"))
        code_row.addWidget(self.code, 1)
        code_row.addWidget(self.send_code)
        self.code_row = QWidget()
        self.code_row.setLayout(code_row)
        code_row.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.code_row)
        buttons = QHBoxLayout()
        self.login = QPushButton(label + tr(" sign in"))
        self.cancel = QPushButton(tr("Cancel"))
        buttons.addWidget(self.login)
        buttons.addWidget(self.cancel)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.login.clicked.connect(self.login_clicked)
        self.cancel.clicked.connect(self.cancel_clicked)
        self.send_code.clicked.connect(self._submit_code)
        self.code.returnPressed.connect(self._submit_code)
        self.set_idle(label + tr(" account. When sign-in is complete, the interrupted message will be resent automatically."))

    def _open_link(self, url):
        QDesktopServices.openUrl(QUrl(url))
        # Only this fallback page shows a code; the CLI-opened page returns via localhost.
        if self.accepts_code:
            self.text.setText(tr("Sign in on the opened page and paste the displayed code."))
            self.code_row.show()
            self.code.setFocus()

    def _submit_code(self):
        code = self.code.text().strip()
        if code:
            self.code.clear()
            self.code_submitted.emit(code)
            self.text.setText(tr("Checking code…"))

    def set_idle(self, message):
        self.text.setText(message)
        self.link.hide()
        self.code_row.hide()
        self.login.show()
        self.login.setEnabled(True)
        self.cancel.hide()

    def set_waiting(self):
        self.text.setText(tr("Sign in in your browser. Return here when finished."))
        self.login.hide()
        self.cancel.show()

    def set_url(self, url):
        self.link.setText(tr('If the browser does not open, <a href="{0}">open this link</a>').format(
            url.replace("&", "&amp;").replace('"', "&quot;")))
        self.link.show()

    def set_done(self, message):
        self.text.setText(message)
        self.link.hide()
        self.code_row.hide()
        self.login.hide()
        self.cancel.hide()


def repolish(widget):
    # Descendant selectors in the dock style sheet change when a row is reparented.
    for item in [widget] + widget.findChildren(QWidget):
        item.style().unpolish(item)
        item.style().polish(item)


class StepsGroup(QWidget):
    """Collapsed, muted rows between a turn's first reply and its latest one."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setObjectName("stepsToggle")
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.toggled.connect(self.expand)
        layout.addWidget(self.toggle)
        self.body = QWidget()
        self.body.setObjectName("stepsBody")
        self.steps = QVBoxLayout(self.body)
        self.steps.setContentsMargins(12, 0, 0, 0)
        self.steps.setSpacing(6)
        self.body.hide()
        layout.addWidget(self.body)
        self.muted = None
        self._apply_muted_color()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_muted_color()

    def _apply_muted_color(self):
        # Palette roles like mid are near the background in dark themes; blend text toward it instead.
        text, base = self.palette().color(QPalette.ColorRole.Text), self.palette().color(QPalette.ColorRole.Base)
        muted = QColor(*(round(a * 0.6 + b * 0.4) for a, b in
                         zip(text.getRgb()[:3], base.getRgb()[:3]))).name()
        if muted != self.muted:
            self.muted = muted
            self.setStyleSheet(f"QToolButton#stepsToggle, QLabel#messageRole {{ color: {muted}; }}")

    def add(self, row):
        self.steps.addWidget(row)
        repolish(row)
        self.toggle.setText(tr("Intermediate steps ({0})").format(self.steps.count()))

    def expand(self, expanded):
        self.body.setVisible(expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)


class ChatTranscript(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.rows = QVBoxLayout(self.content)
        self.rows.setContentsMargins(8, 12, 8, 12)
        self.rows.setSpacing(12)
        self.rows.addStretch()
        self.setWidget(self.content)
        self.messages = []
        self.login_card = None
        self.follow_tail = True
        self.reset_turn()
        self.verticalScrollBar().valueChanged.connect(self._scroll_changed)
        self.verticalScrollBar().rangeChanged.connect(self._range_changed)

    def _scroll_changed(self, value):
        self.follow_tail = value >= self.verticalScrollBar().maximum() - 24

    def _range_changed(self, minimum, maximum):
        if self.follow_tail:
            self.verticalScrollBar().setValue(maximum)

    def reset_turn(self, open_turn=False):
        # tail holds the rows after the first reply that are still shown; None outside a turn.
        self.first_reply = None
        self.steps = None
        self.tail = [] if open_turn else None

    def add_message(self, role, text):
        bubble = MessageBubble(role, text)
        row = self._add_row(bubble, role)
        self.messages.append(bubble)
        if role == tr("You"):
            self.reset_turn(open_turn=True)
        elif self.tail is not None:
            if self.first_reply is None:
                if bubble.is_agent:
                    self.first_reply = row
            else:
                if bubble.is_agent:
                    self._collapse_tail()
                self.tail.append(row)
        return bubble

    def _collapse_tail(self):
        """Fold earlier steps away; reasoning shown for the incoming reply stays with it."""
        end = max((index + 1 for index, row in enumerate(self.tail)
                   if row.objectName() != "systemNotice"), default=0)
        if not end:
            return
        if self.steps is None:
            self.steps = StepsGroup()
            self.rows.insertWidget(self.rows.indexOf(self.first_reply) + 1, self.steps)
        for row in self.tail[:end]:
            self.rows.removeWidget(row)
            self.steps.add(row)
        del self.tail[:end]

    def show_notice(self, text, step=False):
        """Display transient session information outside saved chat bubbles.

        A step notice belongs to the running turn and is folded away with its steps.
        """
        notice = QLabel(text)
        notice.setObjectName("systemNotice")
        notice.setTextFormat(Qt.TextFormat.PlainText)
        notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        notice.setWordWrap(True)
        notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        notice.setStyleSheet("color: palette(text); font-size: 11px;")
        self.rows.insertWidget(self.rows.count() - 1, notice)
        if step and self.first_reply is not None:
            self.tail.append(notice)
        return notice

    def show_login(self, label, accepts_code, detail=""):
        # A single prompt at the tail; earlier ones would offer a stale flow.
        if self.login_card is not None:
            self.login_card.parentWidget().hide()
            self.login_card.parentWidget().deleteLater()
        self.login_card = LoginCard(label, accepts_code, detail)
        self._add_row(self.login_card, label)
        return self.login_card

    def _add_row(self, bubble, role):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        if role == tr("You"):
            layout.addSpacing(36)
        layout.addWidget(bubble)
        if role != tr("You"):
            layout.addSpacing(20)
        self.rows.insertWidget(self.rows.count() - 1, row)
        return row

    def clear(self):
        self.messages.clear()
        self.login_card = None
        while self.rows.count() > 1:
            widget = self.rows.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()
        self.reset_turn()
        self.follow_tail = True

    def toPlainText(self):
        return "\n".join(b.role.text() + "\n" + b.message.text() for b in self.messages)


class SettingsDialog(QDialog):
    def __init__(self, options, parent=None, delete_past_sessions=None):
        super().__init__(parent)
        self.delete_past_sessions_callback = delete_past_sessions
        self.setWindowTitle(tr("Qtaro settings"))
        self.provider = options.get("provider", "claude")
        self.resize(820, 520)
        layout = QVBoxLayout(self)
        self.provider_tabs = QTabWidget()
        layout.addWidget(self.provider_tabs)
        from ..core.agent import default_codex_executable
        from ..core.credentials import has_api_key
        from ..core.session import CODEX_MODELS, MODEL_CHOICES
        from .capability_tabs import CapabilityTabs, CodexCapabilityTabs
        self.executable = QLineEdit(options["executable"])
        self.codex_executable = QLineEdit(options.get("codex_executable", default_codex_executable()))
        self.provider_pages = {}
        self.model_checks = {}
        self.auth = {}
        self.api_keys = {}
        self.auth_help = {}
        self.endpoints = {}
        self.base_urls = {}
        self.custom_models = {}
        self.connection_toggles = {}
        self.connection_fields = {}
        for provider, label, editor, browse_slot in (
                ("codex", "Codex", self.codex_executable, self.browse_codex),
                ("claude", "Claude", self.executable, self.browse)):
            tabs = QTabWidget()
            self.provider_pages[provider] = tabs
            self.provider_tabs.addTab(tabs, label)
            general = QWidget()
            general_layout = QVBoxLayout(general)
            tabs.addTab(general, tr("General"))
            form = QFormLayout()
            path_row = QHBoxLayout()
            browse = QPushButton(tr("Browse…"))
            browse.clicked.connect(browse_slot)
            path_row.addWidget(editor)
            path_row.addWidget(browse)
            form.addRow(tr("Executable"), path_row)
            auth = QComboBox()
            auth.addItem(tr("Subscription (CLI sign-in)"), "subscription")
            auth.addItem(tr("API key"), "api_key")
            auth.setCurrentIndex(max(0, auth.findData(options.get(provider + "_auth", "subscription"))))
            form.addRow(tr("Authentication"), auth)
            key = QLineEdit()
            key.setEchoMode(QLineEdit.EchoMode.Password)
            key.setAccessibleName(label + tr(" API key"))
            # The stored key is not decrypted here, so opening settings never prompts for the master password.
            key.setPlaceholderText(tr("Saved. Enter a new key to replace it.") if has_api_key(provider) else
                                   ("sk-ant-…" if provider == "claude" else "sk-…"))
            forget = QPushButton(tr("Delete saved key"))
            forget.setEnabled(has_api_key(provider))
            forget.clicked.connect(lambda checked=False, provider=provider: self.forget_api_key(provider))
            key_row = QHBoxLayout()
            key_row.addWidget(key)
            key_row.addWidget(forget)
            form.addRow(tr("API key"), key_row)
            self.auth[provider] = auth
            self.api_keys[provider] = (key, forget)
            connection_toggle = QCheckBox(tr("Show advanced connection settings"))
            connection_toggle.setChecked(options.get(provider + "_endpoint", "default") != "default" or
                                         bool(options.get(provider + "_custom_model", "")))
            form.addRow(connection_toggle)
            connection_panel = QWidget()
            connection_form = QFormLayout(connection_panel)
            connection_form.setContentsMargins(0, 0, 0, 0)
            endpoint = QComboBox()
            endpoint.addItem(tr("Default"), "default")
            endpoint.addItem(tr("Custom endpoint"), "custom")
            if provider == "claude":
                endpoint.addItem("Amazon Bedrock", "bedrock")
            else:
                endpoint.addItem("Amazon Bedrock Runtime", "amazon-bedrock-runtime")
                endpoint.addItem("Amazon Bedrock Mantle", "amazon-bedrock")
            endpoint.setCurrentIndex(max(0, endpoint.findData(options.get(provider + "_endpoint", "default"))))
            connection_form.addRow(tr("Model service"), endpoint)
            base_url = QLineEdit(options.get(provider + "_base_url", ""))
            base_url.setPlaceholderText("https://…/v1" if provider == "codex" else "https://…")
            connection_form.addRow(tr("Base URL"), base_url)
            custom_model = QLineEdit(options.get(provider + "_custom_model", ""))
            custom_model.setPlaceholderText(tr("Optional model ID for the model picker"))
            connection_form.addRow(tr("Custom model ID"), custom_model)
            form.addRow(connection_panel)
            self.endpoints[provider] = endpoint
            self.base_urls[provider] = base_url
            self.custom_models[provider] = custom_model
            self.connection_toggles[provider] = connection_toggle
            self.connection_fields[provider] = connection_panel
            connection_toggle.toggled.connect(
                lambda checked, provider=provider: self.show_connection_fields(provider, checked))
            self.show_connection_fields(provider, connection_toggle.isChecked())
            general_layout.addLayout(form)
            help_text = QLabel()
            help_text.setWordWrap(True)
            general_layout.addWidget(help_text)
            self.auth_help[provider] = help_text
            auth.currentIndexChanged.connect(lambda index, provider=provider: self.update_auth_fields(provider))
            endpoint.currentIndexChanged.connect(lambda index, provider=provider: self.update_auth_fields(provider))
            self.update_auth_fields(provider)
            models_title = QLabel(tr("Models in the picker"))
            models_title.setStyleSheet("font-weight: 600; padding-top: 8px;")
            general_layout.addWidget(models_title)
            models_help = QLabel(tr("Uncheck models you do not use. Models the configured CLI cannot use stay hidden."))
            models_help.setWordWrap(True)
            general_layout.addWidget(models_help)
            models = QGridLayout()
            choices = [item for item in (CODEX_MODELS if provider == "codex" else MODEL_CHOICES) if item[1]]
            for index, (model_label, model) in enumerate(choices):
                check = QCheckBox(model_label)
                check.setChecked(model not in options.get("disabled_models", []))
                self.model_checks[model] = check
                models.addWidget(check, index // 2, index % 2)
            general_layout.addLayout(models)
            general_layout.addStretch()
        general_page = QWidget()
        general_layout = QVBoxLayout(general_page)
        self.notifications = QCheckBox(tr("Notify when the agent finishes or needs your input while QGIS is in the background"))
        self.notifications.setChecked(options.get("notifications", True))
        general_layout.addWidget(self.notifications)
        prompt_title = QLabel(tr("Custom prompt"))
        prompt_title.setStyleSheet("font-weight: 600; padding-top: 8px;")
        general_layout.addWidget(prompt_title)
        prompt_help = QLabel(tr("These instructions are added to the system prompt for every session and provider. "
                                "Changes take effect with the next message."))
        prompt_help.setWordWrap(True)
        general_layout.addWidget(prompt_help)
        self.custom_prompt = QPlainTextEdit(options.get("custom_prompt", ""))
        self.custom_prompt.setPlaceholderText(tr("Example: Reply in Japanese. Save outputs as GeoPackage in ~/gis/output."))
        self.custom_prompt.setFixedHeight(96)
        general_layout.addWidget(self.custom_prompt)
        skills_title = QLabel(tr("Built-in skills"))
        skills_title.setStyleSheet("font-weight: 600; padding-top: 8px;")
        general_layout.addWidget(skills_title)
        skills_row = QHBoxLayout()
        self.sync_skills = QPushButton(tr("Sync built-in skills"))
        self.sync_skills.clicked.connect(self.sync_bundled_skills)
        skills_row.addWidget(self.sync_skills)
        skills_help = QLabel(tr("Copied only after the first-launch prompt. Sync replaces any edits to the built-in skills."))
        skills_help.setWordWrap(True)
        skills_row.addWidget(skills_help, 1)
        general_layout.addLayout(skills_row)
        general_layout.addStretch()
        delete_row = QHBoxLayout()
        self.delete_past_sessions_button = QPushButton(tr("Delete all past sessions"))
        self.delete_past_sessions_button.setEnabled(delete_past_sessions is not None)
        self.delete_past_sessions_button.clicked.connect(self.confirm_delete_past_sessions)
        delete_row.addWidget(self.delete_past_sessions_button)
        delete_row.addStretch()
        general_layout.addLayout(delete_row)
        self.provider_tabs.insertTab(0, general_page, tr("General"))
        self.provider_tabs.setCurrentIndex(0)
        about_page = QWidget()
        about_layout = QVBoxLayout(about_page)
        metadata = ConfigParser(interpolation=None)
        metadata.read(Path(__file__).resolve().parents[1] / "metadata.txt", encoding="utf-8")
        name = metadata.get("general", "name", fallback="Qtaro")
        version = metadata.get("general", "version", fallback="dev")
        about_layout.addStretch()
        about_content = QFrame()
        about_content.setFrameShape(QFrame.Shape.StyledPanel)
        about_content.setMinimumWidth(340)
        about_content.setMaximumWidth(440)
        about_content_layout = QVBoxLayout(about_content)
        about_content_layout.setContentsMargins(36, 28, 36, 28)
        about_content_layout.setSpacing(14)
        title = QLabel(name)
        title_font = title.font()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_content_layout.addWidget(title)
        description = QLabel(tr("QGIS AI assistant"))
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_content_layout.addWidget(description)
        version_label = QLabel(tr("Version: {0}").format(version))
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_content_layout.addWidget(version_label)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setMaximumWidth(240)
        about_content_layout.addWidget(divider, alignment=Qt.AlignmentFlag.AlignHCenter)
        developer_row = QHBoxLayout()
        developer_row.addStretch()
        developer_row.addWidget(QLabel(tr("Developed by")))
        self.mierune_link = QLabel('<a href="https://www.mierune.co.jp/">MIERUNE ↗</a>')
        self.mierune_link.setOpenExternalLinks(True)
        developer_row.addWidget(self.mierune_link)
        developer_row.addStretch()
        about_content_layout.addLayout(developer_row)
        about_layout.addWidget(about_content, alignment=Qt.AlignmentFlag.AlignHCenter)
        about_layout.addStretch()
        self.provider_tabs.addTab(about_page, tr("About"))
        self.capabilities = CapabilityTabs(self.provider_pages["claude"], self.executable.text, self, options)
        self.codex_capabilities = CodexCapabilityTabs(self.provider_pages["codex"], options)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        active_path = self.codex_executable if self.provider == "codex" else self.executable
        active_path.textChanged.connect(lambda text: buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(text.strip())))
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(active_path.text().strip()))
        layout.addWidget(buttons)

    def show_connection_fields(self, provider, visible):
        self.connection_fields[provider].setVisible(visible)

    def update_auth_fields(self, provider):
        endpoint = self.endpoints[provider].currentData()
        self.base_urls[provider].setEnabled(endpoint == "custom")
        if endpoint == "custom" and self.auth[provider].currentData() != "api_key":
            self.auth[provider].blockSignals(True)
            self.auth[provider].setCurrentIndex(self.auth[provider].findData("api_key"))
            self.auth[provider].blockSignals(False)
        self.auth[provider].setEnabled(endpoint == "default")
        self.api_keys[provider][0].setEnabled(endpoint == "custom" or
                                               (endpoint == "default" and self.auth[provider].currentData() == "api_key"))
        if endpoint == "custom":
            self.auth_help[provider].setText(tr(
                "The endpoint must support the CLI's API protocol. The saved API key is sent to that URL. "
                "Select its model ID below."))
        elif endpoint != "default":
            self.auth_help[provider].setText(tr(
                "Amazon Bedrock uses the AWS credentials and Region configured for QGIS. "
                "Select an available Bedrock model ID below."))
        else:
            self.auth_help[provider].setText(tr(
                "Subscription uses the CLI sign-in. API keys are stored encrypted in the QGIS authentication database."))

    def forget_api_key(self, provider):
        from ..core.credentials import remove_api_key
        key, forget = self.api_keys[provider]
        if not remove_api_key(provider):
            QMessageBox.warning(self, tr("API key"), tr("Could not delete the saved API key."))
            return
        key.clear()
        key.setPlaceholderText("sk-ant-…" if provider == "claude" else "sk-…")
        forget.setEnabled(False)

    def accept(self):
        from ..core.agent import valid_endpoint
        from ..core.credentials import has_api_key, store_api_key
        for provider, (key, forget) in self.api_keys.items():
            endpoint = self.endpoints[provider].currentData()
            if endpoint == "custom" and not valid_endpoint(self.base_urls[provider].text()):
                QMessageBox.warning(self, tr("Base URL"), tr("Enter a valid HTTP or HTTPS endpoint URL."))
                self.base_urls[provider].setFocus()
                return
            needs_key = endpoint == "custom" or (endpoint == "default" and
                                                  self.auth[provider].currentData() == "api_key")
            if needs_key and not key.text().strip() and not has_api_key(provider):
                QMessageBox.warning(self, tr("API key"), tr("Enter an API key for this model service."))
                key.setFocus()
                return
        for provider, (key, forget) in self.api_keys.items():
            endpoint = self.endpoints[provider].currentData()
            if (endpoint != "custom" and
                    (endpoint != "default" or self.auth[provider].currentData() != "api_key")) or not key.text().strip():
                continue
            if not store_api_key(provider, key.text()):
                QMessageBox.warning(self, tr("API key"), tr("Could not save the API key. "
                                                            "Check the QGIS master password and try again."))
                return
            key.clear()
            key.setPlaceholderText(tr("Saved. Enter a new key to replace it."))
            forget.setEnabled(True)
        super().accept()

    def sync_bundled_skills(self):
        from ..core.protocol import install_bundled_skills
        if QMessageBox.question(self, tr("Sync built-in skills"),
                                tr("Sync the built-in skills from this plugin? "
                                   "Your edits to them will be overwritten.")) != QMessageBox.StandardButton.Yes:
            return
        try:
            written = install_bundled_skills(overwrite=True)
        except OSError as exc:
            QMessageBox.warning(self, tr("Sync built-in skills"), tr("Could not install the built-in skills: ") + str(exc))
            return
        folders = sorted({str(path.parent) for path in written})
        QMessageBox.information(self, tr("Sync built-in skills"),
                                tr("Synced the built-in skills in:\n") + "\n".join(folders) if folders else
                                tr("No Claude Code or Codex skills folder was found."))

    def confirm_delete_past_sessions(self):
        if self.delete_past_sessions_callback is None:
            return
        if QMessageBox.question(
                self, tr("Delete all past sessions"),
                tr("Delete all past sessions? The current session, QGIS layers, and agent history will remain."),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            if not self.delete_past_sessions_callback():
                QMessageBox.warning(self, tr("Delete error"), tr("Could not save the current session."))
        except Exception as exc:
            QMessageBox.warning(self, tr("Delete error"), str(exc))

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Claude Code executable"))
        if path:
            self.executable.setText(path)

    def browse_codex(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Codex executable"))
        if path:
            self.codex_executable.setText(path)

    def options(self):
        return {"executable": self.executable.text().strip(),
                "codex_executable": self.codex_executable.text().strip(),
                "custom_prompt": self.custom_prompt.toPlainText().strip(),
                "notifications": self.notifications.isChecked(),
                **{provider + "_auth": auth.currentData() for provider, auth in self.auth.items()},
                **{provider + "_endpoint": choice.currentData() for provider, choice in self.endpoints.items()},
                **{provider + "_base_url": editor.text().strip() for provider, editor in self.base_urls.items()},
                **{provider + "_custom_model": editor.text().strip() for provider, editor in self.custom_models.items()},
                "disabled_models": [model for model, check in self.model_checks.items() if not check.isChecked()],
                **self.capabilities.selected_options(),
                "codex_capabilities": self.codex_capabilities.selected_options()}
