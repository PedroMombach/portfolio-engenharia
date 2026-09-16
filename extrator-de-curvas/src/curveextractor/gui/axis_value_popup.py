"""Compact calibration-value editor positioned by the clicked point."""

import math

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox

from .texts import T


class AxisValuePopup(QDialog):
    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T.APP)
        layout = QFormLayout(self)
        self.fields = []
        self.values = None
        for label, default in labels:
            field = QLineEdit(str(default))
            layout.addRow(label, field)
            self.fields.append(field)
        buttons = QDialogButtonBox()
        buttons.addButton(T.OK, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(T.CANCEL, QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.fields[0].selectAll()

    def accept(self):
        try:
            self.values = tuple(float(f.text().replace(",", ".")) for f in self.fields)
            if not all(math.isfinite(v) for v in self.values):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, T.ERROR, T.INVALID_NUMBER)
            return
        super().accept()
