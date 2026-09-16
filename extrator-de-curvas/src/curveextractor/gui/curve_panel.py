"""Collapsed-by-default curve rows with editable metadata and read-only geometry."""

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from .texts import T
from .theme import configure_numeric_input


class CurvePanel(QTreeWidget):
    changed = Signal()
    delete_requested = Signal(str)
    main_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(4)
        self.setHeaderLabels([T.NAME, T.POINTS_HEADER, T.MAIN, ""])
        self.setColumnWidth(0, 145)
        self.setColumnWidth(1, 68)
        self.setColumnWidth(2, 82)
        self.setMinimumWidth(390)
        self.group = QButtonGroup(self)
        self.project = None
        self.itemChanged.connect(self.rename)

    def rebuild(self, project):
        expanded = {
            self.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
            for i in range(self.topLevelItemCount())
            if self.topLevelItem(i).isExpanded()
        }
        self.blockSignals(True)
        self.clear()
        self.group.deleteLater()
        self.group = QButtonGroup(self)
        self.project = project
        for curve in project.curves:
            row = QTreeWidgetItem([curve.name, str(len(curve.points_px)), "", ""])
            row.setData(0, Qt.ItemDataRole.UserRole, curve.id)
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsEditable)
            self.addTopLevelItem(row)
            main = QRadioButton()
            self.group.addButton(main)
            main.setChecked(curve.id == project.main_curve_id)
            main.setEnabled(curve.locked)
            main.clicked.connect(lambda checked=False, cid=curve.id: self.main_requested.emit(cid))
            self.setItemWidget(row, 2, main)
            delete = QPushButton("×")
            delete.setToolTip(T.DELETE)
            delete.setMaximumWidth(28)
            delete.clicked.connect(
                lambda checked=False, cid=curve.id: self.delete_requested.emit(cid)
            )
            self.setItemWidget(row, 3, delete)
            child = QTreeWidgetItem(row)
            child.setFirstColumnSpanned(True)
            details = QWidget()
            form = QFormLayout(details)
            for index, point in enumerate(curve.coordinate_system.points, 1):
                form.addRow(
                    QLabel(
                        T.AXIS_RECORD.format(
                            number=index, px=point.px, py=point.py, vx=point.vx, vy=point.vy
                        )
                    )
                )
            form.addRow(
                T.X_SCALE, QLabel(T.LOG if curve.coordinate_system.x_scale == "log" else T.LINEAR)
            )
            form.addRow(
                T.Y_SCALE, QLabel(T.LOG if curve.coordinate_system.y_scale == "log" else T.LINEAR)
            )
            color = QPushButton(curve.style.color)
            color.setStyleSheet(f"color: {curve.style.color};")
            color.clicked.connect(lambda checked=False, c=curve: self.color(c))
            form.addRow(T.COLOR, color)
            width = QDoubleSpinBox()
            configure_numeric_input(width)
            width.setRange(0.5, 10)
            width.setValue(curve.style.width)
            width.valueChanged.connect(lambda value, c=curve: self.style(c, width=value))
            form.addRow(T.WIDTH, width)
            shape = QComboBox()
            for label, value in [
                (T.CIRCLE, "circle"),
                (T.SQUARE, "square"),
                (T.TRIANGLE, "triangle"),
            ]:
                shape.addItem(label, value)
            shape.setCurrentIndex(shape.findData(curve.style.marker))
            shape.currentIndexChanged.connect(
                lambda _, c=curve, w=shape: self.style(c, marker=w.currentData())
            )
            form.addRow(T.MARKER, shape)
            if curve.locked:
                form.addRow(QLabel(T.GEOMETRY_LOCKED))
            self.setItemWidget(child, 0, details)
            row.setExpanded(curve.id in expanded)
        self.blockSignals(False)

    def rename(self, item, column):
        if column == 0 and item.parent() is None:
            curve = next(
                c for c in self.project.curves if c.id == item.data(0, Qt.ItemDataRole.UserRole)
            )
            curve.name = item.text(0)
            self.changed.emit()

    def style(self, curve, **values):
        curve.style = replace(curve.style, **values)
        self.changed.emit()

    def color(self, curve):
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.style(curve, color=color.name())
