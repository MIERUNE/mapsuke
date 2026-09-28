"""Search older sessions without populating the dock's compact selector."""
from ..core.i18n import tr
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QLineEdit, QListWidget,
                                QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)


class SessionPicker(QDialog):
    PAGE_SIZE = 50

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.selected_id = None
        self.offset = 0
        self.setWindowTitle(tr("Sessions"))
        self.resize(520, 440)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search by title"))
        layout.addWidget(self.search)
        self.results = QListWidget()
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.results)
        footer = QHBoxLayout()
        self.more = QPushButton(tr("Show more"))
        self.open_button = QPushButton(tr("Open"))
        self.delete_button = QPushButton(tr("Delete"))
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
        self.open_button.clicked.connect(lambda: self.open_selected())
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
        items = self.results.selectedItems()
        if not items:
            return
        message = (tr("Delete this session from the list? QGIS layers and the agent's history will remain.")
                   if len(items) == 1 else
                   tr("Delete {0} sessions from the list? QGIS layers and the agent's history will remain.")
                   .format(len(items)))
        if QMessageBox.question(
                self, tr("Delete session"), message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            for item in items:
                self.store.delete(item.data(Qt.ItemDataRole.UserRole))
        except Exception as exc:
            QMessageBox.warning(self, tr("Delete error"), str(exc))
        self.refresh()

    def open_selected(self, item=None):
        # Opening needs one session; with several selected, the last one wins.
        if item is None:
            items = self.results.selectedItems()
            item = items[-1] if items else None
        if item is not None:
            self.selected_id = item.data(Qt.ItemDataRole.UserRole)
            self.accept()
