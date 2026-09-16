"""Original-pixel scene; viewport-only zoom and pan."""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from .canvas_items import marker, polyline


class CanvasView(QGraphicsView):
    clicked = Signal(float, float)
    advance = Signal()
    cursor_moved = Signal(QPointF)
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setBackgroundBrush(Qt.GlobalColor.darkGray)
        self.page = None
        self.image_item = None
        self.overlays = []
        self.pan_position = None
        self.space_down = False

    def set_page(self, page):
        self.scene().clear()
        self.overlays = []
        self.page = page
        self.image_item = None
        if page is None:
            self.setSceneRect(QRectF())
            self.resetTransform()
            return
        pixmap = QPixmap()
        pixmap.loadFromData(page.png_bytes)
        self.image_item = self.scene().addPixmap(pixmap)
        self.setSceneRect(0, 0, page.width_px, page.height_px)
        self.fit()

    def dragEnterEvent(self, event):
        if any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def fit(self):
        if self.page:
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def zoom(self, factor, position=None):
        before = self.mapToScene(position) if position is not None else None
        current = self.transform().m11()
        factor = max(0.02, min(100, current * factor)) / current
        self.scale(factor, factor)
        if before is not None:
            after = self.mapToScene(position)
            delta = after - before
            self.translate(delta.x(), delta.y())

    def draw_curves(self, curves, active=None, settings=None):
        for item in self.overlays:
            self.scene().removeItem(item)
        self.overlays.clear()
        if not self.page:
            return
        config = settings or {}
        self.image_item.setOpacity(config.get("image_opacity", 1))
        for curve in curves:
            if (curve.source.document_id, curve.source.page_index) != (
                self.page.document_id,
                self.page.page_index,
            ):
                continue
            opacity = 1 if curve is active else config.get("curve_opacity", 0.6)
            items = [polyline(self.scene(), curve.points_px, curve.style.color, curve.style.width)]
            items.extend(
                marker(self.scene(), p, curve.style.color, curve.style.marker)
                for p in curve.points_px
            )
            for item in items:
                item.setOpacity(opacity)
            self.overlays.extend(items)
            axes = [(p.px, p.py) for p in curve.coordinate_system.points]
            color = config.get("axis_color", "#D55E00")
            axis_items = []
            if len(axes) == 3:
                axis_items.append(
                    polyline(
                        self.scene(),
                        [axes[1], axes[0], axes[2]],
                        color,
                        config.get("axis_width", 1.5),
                    )
                )
            axis_items.extend(
                marker(self.scene(), p, color, "square", config.get("axis_marker_size", 8))
                for p in axes
            )
            for item in axis_items:
                item.setOpacity(1 if curve is active else config.get("axis_opacity", 0.35))
            self.overlays.extend(axis_items)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.2 ** (event.angleDelta().y() / 120), event.position().toPoint())
            event.accept()
        elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - event.angleDelta().y()
            )
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self.space_down
        ):
            self.pan_position = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.RightButton:
            self.advance.emit()
        elif event.button() == Qt.MouseButton.LeftButton and self.page:
            point = self.mapToScene(event.position().toPoint())
            if self.sceneRect().contains(point):
                self.clicked.emit(point.x(), point.y())
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.pan_position is not None:
            delta = event.position() - self.pan_position
            self.pan_position = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
        self.cursor_moved.emit(self.mapToScene(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.pan_position = None
        self.unsetCursor()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.space_down = True
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.space_down = False
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self.space_down = False
        self.pan_position = None
        super().focusOutEvent(event)
