"""Constant screen-size markers and cosmetic polylines."""

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsPolygonItem


def pen(color, width=1.5):
    result = QPen(QColor(color), width)
    result.setCosmetic(True)
    return result


def marker(scene, point, color, shape="circle", size=6):
    radius = size / 2
    if shape == "circle":
        item = scene.addEllipse(-radius, -radius, size, size, pen(color), QColor(color))
    elif shape == "square":
        item = scene.addRect(-radius, -radius, size, size, pen(color), QColor(color))
    else:
        polygon = QPolygonF(
            [QPointF(0, -radius), QPointF(radius, radius), QPointF(-radius, radius)]
        )
        item = QGraphicsPolygonItem(polygon)
        item.setPen(pen(color))
        item.setBrush(QColor(color))
        scene.addItem(item)
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
    item.setPos(*point)
    return item


def polyline(scene, points, color, width=2):
    path = QPainterPath()
    if points:
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
    item = QGraphicsPathItem(path)
    item.setPen(pen(color, width))
    scene.addItem(item)
    return item
