"""Screen-anchored loupe rendered from the unchanged source pixmap."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class Magnifier(QWidget):
    def __init__(self, canvas):
        super().__init__(canvas.viewport())
        self.canvas = canvas
        self.position = None
        self.enabled = False
        self.factor = 4
        self.setFixedSize(190, 190)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        canvas.cursor_moved.connect(self.track)

    def track(self, position):
        self.position = position
        if not self.enabled:
            return
        self.move(max(8, self.parentWidget().width() - self.width() - 14), 14)
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101a24"))
        if self.position is not None and self.canvas.image_item is not None:
            size = self.width() / self.factor
            source = QRectF(self.position.x() - size / 2, self.position.y() - size / 2, size, size)
            painter.drawPixmap(QRectF(self.rect()), self.canvas.image_item.pixmap(), source)
        painter.setPen(QPen(QColor("#e04747"), 1))
        center = self.rect().center()
        painter.drawLine(center.x(), 0, center.x(), self.height())
        painter.drawLine(0, center.y(), self.width(), center.y())
        painter.setPen(QPen(QColor("#8094a7"), 2))
        painter.drawRect(self.rect().adjusted(1, 1, -1, -1))
