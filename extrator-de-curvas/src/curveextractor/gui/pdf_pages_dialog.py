"""Incrementally populate selectable PDF thumbnails without blocking the event loop."""

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from curveextractor.core.raster import pdf_preview

from .texts import T


class PdfPagesDialog(QDialog):
    def __init__(self, path, count, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T.PAGES)
        self.resize(740, 600)
        self.path = path
        self.next_thumbnail = 0
        layout = QVBoxLayout(self)
        self.pages = QListWidget()
        self.pages.setViewMode(QListWidget.ViewMode.IconMode)
        self.pages.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.pages.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.pages.setIconSize(QSize(125, 165))
        self.pages.setGridSize(QSize(150, 195))
        for index in range(count):
            item = QListWidgetItem(T.PAGE.format(number=index + 1))
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.pages.addItem(item)
        layout.addWidget(self.pages)
        select = QPushButton(T.SELECT_ALL)
        select.clicked.connect(self.pages.selectAll)
        layout.addWidget(select)
        buttons = QDialogButtonBox()
        self.confirm = buttons.addButton(T.OK, QDialogButtonBox.ButtonRole.AcceptRole)
        self.confirm.setEnabled(False)
        buttons.addButton(T.CANCEL, QDialogButtonBox.ButtonRole.RejectRole)
        self.pages.itemSelectionChanged.connect(
            lambda: self.confirm.setEnabled(bool(self.selected()))
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.thumbnail)
        self.timer.start(10)
        self.finished.connect(self.timer.stop)

    def selected(self):
        return sorted(item.data(Qt.ItemDataRole.UserRole) for item in self.pages.selectedItems())

    def thumbnail(self):
        if self.next_thumbnail >= self.pages.count():
            self.timer.stop()
            return
        pixmap = QPixmap()
        pixmap.loadFromData(pdf_preview(self.path, self.next_thumbnail))
        self.pages.item(self.next_thumbnail).setIcon(QIcon(pixmap))
        self.next_thumbnail += 1
