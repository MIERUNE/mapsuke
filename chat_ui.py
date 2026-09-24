"""Chat presentation and local preferences; no agent or QGIS execution knowledge."""
from qgis.PyQt.QtCore import Qt, pyqtSignal
from math import ceil

from qgis.PyQt.QtGui import QFontDatabase, QTextOption
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                                QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
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


class MessageText(QTextBrowser):
    """Fit the transcript width and grow vertically with the rendered document."""

    def __init__(self, markdown):
        super().__init__()
        self.markdown = markdown
        self.source = ""
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.document().documentLayout().documentSizeChanged.connect(self._fit_height)
        self.horizontalScrollBar().rangeChanged.connect(self._fit_height)

    def text(self):
        # Session persistence and streaming updates use the original Markdown.
        return self.source

    def setText(self, text):
        self.source = text
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
    def __init__(self, role, text):
        super().__init__()
        self.setObjectName("userBubble" if role == "あなた" else "agentBubble")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        self.role = QLabel(role)
        self.role.setObjectName("messageRole")
        layout.addWidget(self.role)
        # Interrupted replies retain the agent name before the status suffix.
        is_agent = role.split(" · ", 1)[0] in ("Claude", "Codex")
        self.message = MessageText(is_agent)
        layout.addWidget(self.message)
        self.toggle = QToolButton()
        self.toggle.setText("Pythonコード")
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        layout.addWidget(self.toggle)
        self.code = QPlainTextEdit()
        self.code.setReadOnly(True)
        self.code.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.code.setMinimumHeight(100)
        self.code.setMaximumHeight(220)
        layout.addWidget(self.code)
        self.toggle.toggled.connect(self.expand_code)
        self.toggle.hide()
        self.code.hide()
        self.update_content(text)

    def expand_code(self, expanded):
        self.code.setVisible(expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

    def update_content(self, message, code=""):
        self.message.setText(message)
        self.message.setVisible(bool(message))
        self.toggle.setVisible(bool(code))
        if self.code.toPlainText() != code:
            self.code.setPlainText(code)
        self.code.setVisible(bool(code) and self.toggle.isChecked())


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
        self.follow_tail = True
        self.verticalScrollBar().valueChanged.connect(self._scroll_changed)
        self.verticalScrollBar().rangeChanged.connect(self._range_changed)

    def _scroll_changed(self, value):
        self.follow_tail = value >= self.verticalScrollBar().maximum() - 24

    def _range_changed(self, minimum, maximum):
        if self.follow_tail:
            self.verticalScrollBar().setValue(maximum)

    def add_message(self, role, text):
        bubble = MessageBubble(role, text)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        if role == "あなた":
            layout.addSpacing(36)
        layout.addWidget(bubble)
        if role != "あなた":
            layout.addSpacing(20)
        self.rows.insertWidget(self.rows.count() - 1, row)
        self.messages.append(bubble)
        return bubble

    def clear(self):
        self.messages.clear()
        while self.rows.count() > 1:
            widget = self.rows.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()
        self.follow_tail = True

    def toPlainText(self):
        return "\n".join(b.role.text() + "\n" + b.message.text() for b in self.messages)


class SettingsDialog(QDialog):
    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QGIS Agent の設定")
        self.provider = options.get("provider", "claude")
        self.resize(820, 520)
        layout = QVBoxLayout(self)
        self.provider_tabs = QTabWidget()
        layout.addWidget(self.provider_tabs)
        from .agent import default_codex_executable
        from .capability_ui import CapabilityTabs, CodexCapabilityTabs
        self.executable = QLineEdit(options["executable"])
        self.codex_executable = QLineEdit(options.get("codex_executable", default_codex_executable()))
        self.provider_pages = {}
        for provider, label, editor, browse_slot in (
                ("codex", "Codex", self.codex_executable, self.browse_codex),
                ("claude", "Claude", self.executable, self.browse)):
            tabs = QTabWidget()
            self.provider_pages[provider] = tabs
            self.provider_tabs.addTab(tabs, label)
            general = QWidget()
            general_layout = QVBoxLayout(general)
            tabs.addTab(general, "一般")
            form = QFormLayout()
            path_row = QHBoxLayout()
            browse = QPushButton("参照…")
            browse.clicked.connect(browse_slot)
            path_row.addWidget(editor)
            path_row.addWidget(browse)
            form.addRow("実行ファイル", path_row)
            general_layout.addLayout(form)
            help_text = QLabel(label + "のログイン情報を使用します。\n" +
                               ("ターミナルで codex login を実行してください。" if provider == "codex" else
                                "ターミナルで claude を実行してください。"))
            help_text.setWordWrap(True)
            general_layout.addWidget(help_text)
            general_layout.addStretch()
        self.capabilities = CapabilityTabs(self.provider_pages["claude"], self.executable.text, self, options)
        self.codex_capabilities = CodexCapabilityTabs(self.provider_pages["codex"], options)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        active_path = self.codex_executable if self.provider == "codex" else self.executable
        active_path.textChanged.connect(lambda text: buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(text.strip())))
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(active_path.text().strip()))
        layout.addWidget(buttons)

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Claude Code実行ファイル")
        if path:
            self.executable.setText(path)

    def browse_codex(self):
        path, _ = QFileDialog.getOpenFileName(self, "Codex実行ファイル")
        if path:
            self.codex_executable.setText(path)

    def options(self):
        return {"executable": self.executable.text().strip(),
                "codex_executable": self.codex_executable.text().strip(),
                **self.capabilities.selected_options(),
                "codex_capabilities": self.codex_capabilities.selected_options()}
