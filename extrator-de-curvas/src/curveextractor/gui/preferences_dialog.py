"""Persistent controls for appearance, export options, and action bindings."""

import copy

from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QKeySequenceEdit,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from curveextractor.core.errors import DomainError

from .texts import T, domain_message
from .theme import configure_numeric_input


class PreferencesDialog(QDialog):
    def __init__(self, settings, actions, parent=None):
        super().__init__(parent)
        self.settings, self.actions = settings, actions
        self.setWindowTitle(T.PREFERENCES)
        self.resize(650, 720)
        self.fields = {}
        self.keys = {}
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        appearance = self.tab(tabs, T.APPEARANCE)
        output = self.tab(tabs, T.EXPORT_SETTINGS)
        shortcuts = self.tab(tabs, T.SHORTCUTS)
        specs = [
            (
                appearance,
                "theme",
                T.THEME,
                [(T.SYSTEM, "sistema"), (T.LIGHT, "claro"), (T.DARK, "escuro")],
            ),
            (appearance, "font_color", T.FONT_COLOR, "text"),
            (appearance, "canvas_color", T.CANVAS_COLOR, "text"),
            (appearance, "axis_color", T.AXIS_COLOR, "text"),
            (appearance, "axis_width", T.AXIS_WIDTH, (0.5, 10)),
            (appearance, "axis_marker_size", T.AXIS_SIZE, (2, 30)),
            (appearance, "palette", T.PALETTE, "palette"),
            (
                appearance,
                "marker",
                T.MARKER,
                [(T.CIRCLE, "circle"), (T.SQUARE, "square"), (T.TRIANGLE, "triangle")],
            ),
            (appearance, "curve_width", T.WIDTH, (0.5, 10)),
            (appearance, "curve_opacity", T.CURVE_OPACITY, (0, 1)),
            (appearance, "axis_opacity", T.AXIS_OPACITY, (0, 1)),
            (appearance, "image_opacity", T.IMAGE_OPACITY, (0, 1)),
            (appearance, "magnifier", T.MAGNIFIER, "bool"),
            (appearance, "magnifier_factor", T.MAGNIFIER_FACTOR, (2, 16)),
            (output, "raster_dpi", T.DPI, "dpi"),
            (output, "decimal", T.DECIMAL, [(".", "."), (",", ",")]),
            (output, "delimiter", T.DELIMITER, [(";", ";"), (",", ","), ("Tab", "\t")]),
            (output, "bom", T.BOM, "bool"),
            (
                output,
                "profile",
                T.PROFILE,
                [("Padrão", "Padrão"), ("SeletorBombasMK3", "SeletorBombasMK3")],
            ),
            (output, "include_raw", T.RAW, "bool"),
            (output, "tracking", T.TRACKING, "bool"),
            (output, "dataset_root", T.DATASET_ROOT, "text"),
        ]
        for form, key, label, kind in specs:
            if isinstance(kind, list):
                widget = QComboBox()
                for text, value in kind:
                    widget.addItem(text, value)
            elif isinstance(kind, tuple):
                widget = QDoubleSpinBox()
                configure_numeric_input(widget)
                widget.setRange(*kind)
                widget.setSingleStep(0.1)
            elif kind == "bool":
                widget = QCheckBox()
            elif kind == "dpi":
                widget = QSpinBox()
                configure_numeric_input(widget)
                widget.setRange(72, 600)
                widget.setToolTip(T.DPI_NOTE)
            else:
                widget = QLineEdit()
                if key == "font_color":
                    widget.setToolTip(T.FONT_COLOR_HINT)
            self.fields[key] = widget
            form.addRow(label, widget)
        for key, sequence in settings.data["shortcuts"].items():
            widget = QKeySequenceEdit(QKeySequence(sequence))
            self.keys[key] = widget
            shortcuts.addRow(actions[key].text() if key in actions else key, widget)
        restore = QPushButton(T.RESTORE)
        restore.clicked.connect(lambda: self.fill(settings.defaults))
        layout.addWidget(restore)
        buttons = QDialogButtonBox()
        buttons.addButton(T.OK, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(T.CANCEL, QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.fill(settings.data)

    def tab(self, tabs, name):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        scroll.setWidget(body)
        tabs.addTab(scroll, name)
        return form

    def fill(self, data):
        for key, widget in self.fields.items():
            value = data[key]
            if isinstance(widget, QComboBox):
                widget.setCurrentIndex(widget.findData(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(value)
            else:
                widget.setText(", ".join(value) if key == "palette" else str(value))
        for key, widget in self.keys.items():
            widget.setKeySequence(QKeySequence(data["shortcuts"].get(key, "")))

    def accept(self):
        candidate = copy.deepcopy(self.settings.data)
        for key, widget in self.fields.items():
            if isinstance(widget, QComboBox):
                value = widget.currentData()
            elif isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                value = widget.value()
            else:
                value = widget.text()
            if key == "palette":
                candidate[key] = [c.strip() for c in value.split(",")]
            elif key == "font_color":
                candidate[key] = value.strip().lower()
            else:
                candidate[key] = value
        candidate["shortcuts"] = {
            k: w.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            for k, w in self.keys.items()
        }
        colors = [candidate["canvas_color"], candidate["axis_color"], *candidate["palette"]]
        if candidate["font_color"] != "auto":
            colors.append(candidate["font_color"])
        if not all(QColor(c).isValid() for c in colors):
            QMessageBox.warning(self, T.ERROR, T.KEY_INVALID)
            return
        previous = self.settings.data
        try:
            self.settings.validate(candidate)
            self.settings.data = candidate
            self.settings.save()
        except DomainError as error:
            self.settings.data = previous
            QMessageBox.warning(self, T.ERROR, domain_message(error))
            return
        except OSError as error:
            self.settings.data = previous
            QMessageBox.warning(self, T.ERROR, T.IO_ERROR.format(detail=str(error)))
            return
        super().accept()
