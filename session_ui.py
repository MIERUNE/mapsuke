"""Search older sessions without populating the dock's compact selector."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QDialog, QHBoxLayout, QLineEdit, QListWidget,
                                QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)


class SessionPicker(QDialog):
    PAGE_SIZE = 50

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.selected_id = None
        self.offset = 0
        self.setWindowTitle("セッション一覧")
        self.resize(520, 440)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("タイトルで検索")
        layout.addWidget(self.search)
        self.results = QListWidget()
        layout.addWidget(self.results)
        footer = QHBoxLayout()
        self.more = QPushButton("さらに表示")
        self.open_button = QPushButton("開く")
        self.delete_button = QPushButton("削除")
        self.open_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        footer.addWidget(self.more)
        footer.addStretch()
        footer.addWidget(self.delete_button)
        footer.addWidget(self.open_button)
        layout.addLayout(footer)
        self.search.textChanged.connect(self.refresh)
        self.results.itemSelectionChanged.connect(self.update_actions)
        self.results.itemDoubleClicked.connect(self.open_selected)
        self.open_button.clicked.connect(self.open_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.more.clicked.connect(self.load_more)
        self.refresh()

    def refresh(self):
        self.offset = 0
        self.results.clear()
        self.load_more()

    def load_more(self):
        rows = self.store.list(self.PAGE_SIZE + 1, self.offset, self.search.text().strip())
        for session_id, title, updated in rows[:self.PAGE_SIZE]:
            item = self._add_result(title, updated)
            item.setData(Qt.ItemDataRole.UserRole, session_id)
        self.offset += min(len(rows), self.PAGE_SIZE)
        self.more.setEnabled(len(rows) > self.PAGE_SIZE)

    def _add_result(self, title, updated):
        return QListWidgetItem(title + "  ·  " + updated[:16].replace("T", " ") + " UTC", self.results)

    def update_actions(self):
        selected = bool(self.results.selectedItems())
        self.open_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)

    def delete_selected(self):
        item = self.results.currentItem()
        if item is None:
            return
        if QMessageBox.question(
                self, "セッションを削除",
                "このセッションを一覧から削除しますか？QGISのレイヤーとエージェント側の履歴は残ります。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete(item.data(Qt.ItemDataRole.UserRole))
        except Exception as exc:
            QMessageBox.warning(self, "削除エラー", str(exc))
            return
        self.refresh()

    def open_selected(self, *args):
        item = self.results.currentItem()
        if item is not None:
            self.selected_id = item.data(Qt.ItemDataRole.UserRole)
            self.accept()
